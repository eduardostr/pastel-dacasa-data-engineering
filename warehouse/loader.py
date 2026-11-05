from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from time import perf_counter, gmtime
from uuid import UUID, uuid4

import duckdb

from etl.control.lock import writer_lock
from warehouse.config import Settings
from warehouse.model import prepare_dimensions, prepare_fact, sync_dimensions, sync_fact
from warehouse.quality import validate_source, validate_target
from warehouse.source import load_publication, stage, verify_unchanged

SQL = Path(__file__).resolve().parent / "sql"


def utcnow():
    return datetime.now(timezone.utc)


class Warehouse:
    def __init__(self, settings=None):
        self.settings = settings or Settings()

    def run(self, mode="full", run_id=None, fault=None):
        if mode not in {"full", "incremental"}:
            raise ValueError("Modo inválido")
        run_id = str(UUID(run_id)) if run_id else str(uuid4())
        attempt = str(uuid4())
        hook = fault or (lambda point: None)
        cfg = self.settings
        started = perf_counter()
        with writer_lock(cfg.control_dir):
            cfg.database.parent.mkdir(parents=True, exist_ok=True)
            c = duckdb.connect(str(cfg.database))
            logger = logging.getLogger("warehouse." + attempt)
            log_dir = cfg.control_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(log_dir / (attempt + ".log"), encoding="utf-8")
            formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s")
            formatter.converter = gmtime
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            transaction = False
            committed = False
            publication = None
            metrics = {}
            validations = {}
            try:
                c.execute("SET TimeZone='UTC'")
                c.execute((SQL / "001_schema.sql").read_text(encoding="utf-8"))
                c.execute("INSERT INTO dw_runs(attempt_id,run_id,mode,started_at,status) VALUES(?,?,?,?,?)",
                          [attempt, run_id, mode, utcnow(), "RUNNING"])
                logger.info("inicio run_id=%s attempt=%s mode=%s", run_id, attempt, mode)
                publication = load_publication(cfg.silver_root)
                manifest = publication["manifest"]
                state = c.execute("SELECT schema_version,silver_version,silver_fingerprint,silver_published_at,silver_snapshot_at,source_origin,attempt_id FROM dw_state WHERE singleton=1").fetchone()
                if state and state[0] != 1:
                    raise RuntimeError("Versão do modelo DW incompatível")
                if mode == "incremental" and not state:
                    raise RuntimeError("INCREMENTAL exige uma carga FULL anterior")
                origin = json.dumps(manifest["source"], sort_keys=True)
                if state and state[5] != origin:
                    raise RuntimeError("Origem da Silver diferente do DW existente")
                if state and state[1] == manifest["version"] and state[2] != publication["fingerprint"]:
                    raise RuntimeError("Versão Silver repetida com conteúdo/metadados diferentes")
                if state and state[1] != manifest["version"] and (
                    datetime.fromisoformat(manifest["snapshot_at"]) < state[4] or
                    datetime.fromisoformat(manifest["published_at"]) <= state[3]):
                    raise RuntimeError("Não é permitido retroceder para publicação Silver antiga")
                c.execute("BEGIN TRANSACTION")
                transaction = True
                stage(c, publication)
                validations.update(validate_source(c))
                prepare_dimensions(c)
                reused = bool(state and state[1] == manifest["version"])
                if reused:
                    prepare_fact(c)
                    validations.update(validate_target(c))
                    c.execute((SQL / "003_dashboard.sql").read_text(encoding="utf-8"))
                    verify_unchanged(publication)
                    c.execute("COMMIT")
                    transaction = False
                    # Recupera auditoria se o commit anterior precedeu uma falha do log.
                    c.execute("UPDATE dw_runs SET status='COMPLETED',message=NULL WHERE attempt_id=? AND status IN ('RUNNING','PUBLISHED_AUDIT_PENDING')", [state[6]])
                    status = "REUSED"
                else:
                    metrics.update(sync_dimensions(c, manifest["version"]))
                    hook("after_dimensions")
                    prepare_fact(c)
                    metrics["fato_vendas"] = sync_fact(c, manifest["version"])
                    hook("after_fact")
                    validations.update(validate_target(c))
                    c.execute((SQL / "002_gold.sql").read_text(encoding="utf-8"))
                    c.execute((SQL / "003_dashboard.sql").read_text(encoding="utf-8"))
                    verify_unchanged(publication)
                    hook("before_commit")
                    c.execute("""INSERT INTO dw_state VALUES(1,1,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(singleton) DO UPDATE SET
                        schema_version=excluded.schema_version,silver_version=excluded.silver_version,
                        silver_run_id=excluded.silver_run_id,silver_fingerprint=excluded.silver_fingerprint,
                        silver_published_at=excluded.silver_published_at,silver_snapshot_at=excluded.silver_snapshot_at,
                        source_origin=excluded.source_origin,dw_run_id=excluded.dw_run_id,
                        attempt_id=excluded.attempt_id,committed_at=excluded.committed_at""",
                        [manifest["version"], manifest["run_id"], publication["fingerprint"],
                         datetime.fromisoformat(manifest["published_at"]), datetime.fromisoformat(manifest["snapshot_at"]),
                         origin, run_id, attempt, utcnow()])
                    c.execute("COMMIT")
                    transaction = False
                    committed = True
                    hook("after_commit")
                    status = "COMPLETED"
                gold = c.execute("SELECT faturamento_total,pedidos_faturados,itens_faturados,unidades_vendidas,ticket_medio FROM gold_kpis").fetchone()
                result = {"run_id": run_id, "attempt_id": attempt, "mode": mode, "status": status,
                          "silver_version": manifest["version"], "silver_run_id": manifest["run_id"],
                          "duration_seconds": round(perf_counter()-started, 3), "metrics": metrics, "validations": validations,
                          "gold": {"faturamento_total": str(gold[0]), "pedidos_faturados": gold[1],
                                   "itens_faturados": gold[2], "unidades_vendidas": gold[3], "ticket_medio": str(gold[4])}}
                c.execute("""UPDATE dw_runs SET status=?,silver_version=?,finished_at=?,duration_seconds=?,
                    metrics_json=?,validations_json=? WHERE attempt_id=?""",
                    [status, manifest["version"], utcnow(), result["duration_seconds"],
                     json.dumps(metrics), json.dumps(validations), attempt])
                logger.info("fim %s", result)
                return result
            except Exception as error:
                if transaction:
                    c.execute("ROLLBACK")
                # A auditoria de falha fica fora da transação de dados.
                try:
                    c.execute("""UPDATE dw_runs SET status=?,silver_version=?,finished_at=?,duration_seconds=?,
                        message=?,metrics_json=? WHERE attempt_id=?""",
                        ["PUBLISHED_AUDIT_PENDING" if committed else "FAILED",
                         publication["manifest"]["version"] if publication else None, utcnow(),
                         perf_counter()-started, type(error).__name__ + ": " + str(error), json.dumps(metrics), attempt])
                finally:
                    logger.exception("falha run_id=%s committed=%s", run_id, committed)
                raise
            finally:
                c.close()
                logger.removeHandler(handler)
                handler.close()
