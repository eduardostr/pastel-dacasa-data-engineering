from datetime import datetime
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

from etl.config import Settings, default_engine
from etl.config.schema import COLUMNS, KEYS, QUARANTINE, SCHEMAS
from etl.control.audit import Audit
from etl.control.lock import writer_lock
from etl.extract.postgres import extract
from etl.load.files import (as_table, atomic_json, checksum, current_manifest, inventory,
                            read_json, read_table, utcnow, verify, write_table)
from etl.quality import clean_snapshot
from etl.quality.rules import plain
from etl.transform.snapshot import merge_source, mutation_counts, sales_snapshot


def source_signature(engine, settings):
    url = engine.url
    origin = f"postgresql://{url.host}:{url.port or 5432}/{url.database}/{settings.schema}"
    return {"origin": origin, "quality_version": 1, "lookback_seconds": settings.lookback_seconds,
            "contract": {t: str(schema) for t, schema in SCHEMAS.items()}}


class Pipeline:
    def __init__(self, engine=None, settings=None):
        self.engine = engine if engine is not None else default_engine()
        self.settings = settings or Settings()

    def run(self, mode="full", run_id=None, reprocess=False, fault=None):
        if mode not in {"full", "incremental"}:
            raise ValueError("Modo deve ser full ou incremental")
        run_id = str(UUID(run_id)) if run_id else str(uuid4())
        root = self.settings.data_dir
        signature = source_signature(self.engine, self.settings)
        hook = fault or (lambda stage: None)
        started = perf_counter()
        with writer_lock(root):
            audit = Audit(root)
            attempt = str(uuid4())
            logpath = root / "control/logs" / (attempt + ".log")
            logpath.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(logpath, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger = logging.getLogger("etl." + attempt)
            logger.setLevel(logging.INFO)
            logger.addHandler(handler)
            audit.start(attempt, run_id, mode)
            logger.info("inicio run_id=%s attempt_id=%s mode=%s", run_id, attempt, mode)
            published = False
            try:
                current = current_manifest(root)
                checkpoint_path = root / "control/runs" / run_id / "extraction.json"
                checkpoint = read_json(checkpoint_path)
                if current and current["source"] != signature:
                    raise RuntimeError("A origem/contrato da raiz de dados é diferente")
                if checkpoint and (checkpoint["source"] != signature or checkpoint["mode"] != mode):
                    raise RuntimeError("run_id já utilizado com outro modo/origem/configuração")
                if current and current["run_id"] == run_id and not reprocess:
                    audit.reconcile(current)
                    audit.finish(attempt, "REUSED", perf_counter() - started, current["metrics"])
                    logger.info("reutilizada publicação=%s sem extração", current["version"])
                    return current
                if reprocess and (not checkpoint or not current or current["run_id"] != run_id):
                    raise RuntimeError("Reprocessamento só pode republicar a execução atualmente ativa; não retroceder versões posteriores")
                if not checkpoint:
                    if mode == "incremental" and not current:
                        raise RuntimeError("Incremental exige uma FULL publicada previamente")
                    checkpoint = extract(self.engine, self.settings, run_id, mode, current, signature)
                    atomic_json(checkpoint_path, checkpoint)
                else:
                    expected = checkpoint["parent"]["version"] if checkpoint["parent"] else None
                    actual = current["version"] if current else None
                    if not reprocess and expected != actual:
                        raise RuntimeError("A base mudou desde a extração; preservar Bronze e iniciar outro run_id")
                    verify(root, checkpoint["files"])
                    if checkpoint["parent"]:
                        verify(root, checkpoint["parent"]["files"])
                hook("after_extract")
                frames = merge_source(root, checkpoint)
                valid, quarantine = clean_snapshot(frames)
                fence = datetime.fromisoformat(checkpoint["snapshot_at"])
                sales = sales_snapshot(valid, run_id, fence, signature["origin"])

                staging = root / ".staging" / attempt
                silver_stage = staging / "silver"
                quarantine_stage = staging / "quarantine"
                source_stage = staging / "source"
                metrics = {}
                # A base usada na transformação é a da extração, não o estado
                # operacional de hoje. Permite retomar/reprocessar o mesmo Bronze.
                parent = checkpoint["parent"]
                for table in COLUMNS:
                    write_table(silver_stage / (table + ".parquet"), as_table(valid[table], SCHEMAS[table]))
                    write_table(quarantine_stage / (table + ".parquet"), as_table(quarantine[table], QUARANTINE[table]))
                    raw = [{k: plain(v) for k, v in row.items()} for row in frames[table].to_dict("records")]
                    write_table(source_stage / (table + ".parquet"), as_table(raw, SCHEMAS[table]))
                    old = read_table(root / parent["silver"] / (table + ".parquet")).to_pylist() if parent else []
                    metrics[table] = {**checkpoint["stats"][table], "candidate_rows": len(raw),
                        "valid": len(valid[table]), "rejected": len(quarantine[table]),
                        **mutation_counts(old, valid[table], KEYS[table])}
                write_table(silver_stage / "vendas_detalhadas.parquet", sales)
                old_sales = read_table(root / parent["silver"] / "vendas_detalhadas.parquet").to_pylist() if parent else []
                metrics["vendas_detalhadas"] = {"valid": sales.num_rows,
                    **mutation_counts(old_sales, sales.to_pylist(), "id_item"),
                    "financial_total": str(sum((r["subtotal"] for r in sales.to_pylist()), __import__("decimal").Decimal("0.00")))}
                hook("after_build")
                version = attempt
                destinations = {
                    "silver": root / "silver" / run_id / version,
                    "quarantine": root / "quarantine" / run_id / version,
                    "source_state": root / "control/versions" / version / "source",
                }
                for kind, source in (("silver", silver_stage), ("quarantine", quarantine_stage), ("source_state", source_stage)):
                    destinations[kind].parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, destinations[kind])
                files = {**checkpoint["files"], **inventory(root, destinations.values())}
                cp_relative = str(checkpoint_path.relative_to(root)).replace("\\", "/")
                files[cp_relative] = {"sha256": checksum(checkpoint_path), "bytes": checkpoint_path.stat().st_size}
                verify(root, files)
                manifest = {
                    "run_id": run_id, "attempt_id": attempt, "version": version, "mode": mode,
                    "published_at": utcnow().isoformat(), "snapshot_at": checkpoint["snapshot_at"],
                    "previous_version": current["version"] if current else None,
                    "source": signature, "bronze": checkpoint["bronze"],
                    "fingerprints": checkpoint["fingerprints"], "extraction": cp_relative,
                    "watermarks": checkpoint["watermarks"], "metrics": metrics, "files": files,
                    **{key: str(value.relative_to(root)).replace("\\", "/") for key, value in destinations.items()},
                }
                atomic_json(root / "control/manifests" / (version + ".json"), manifest)
                hook("before_publish")
                # Único ponto de commit lógico de todas as camadas e watermarks.
                atomic_json(root / "control/current.json", manifest)
                published = True
                hook("after_publish")
                audit.finish(attempt, "COMPLETED", perf_counter() - started, metrics)
                logger.info("fim run_id=%s status=COMPLETED duração=%.3f métricas=%s", run_id, perf_counter() - started, metrics)
                return manifest
            except Exception as error:
                audit.finish(attempt, "PUBLISHED_AUDIT_PENDING" if published else "FAILED",
                             perf_counter() - started, error=type(error).__name__ + ": " + str(error))
                logger.exception("erro run_id=%s publicação_concluída=%s", run_id, published)
                raise
            finally:
                logger.removeHandler(handler)
                handler.close()
                audit.close()
