"""Adaptadores Prefect: lógica de dados continua nos módulos existentes."""
from functools import wraps
import errno
import json
from time import perf_counter

import duckdb
from prefect import task, get_run_logger
from prefect.cache_policies import NONE
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from etl.config import Settings as ETLSettings, default_engine
from etl.config.schema import COLUMNS
from etl.pipeline import Pipeline
from etl.load.files import atomic_json
from warehouse.config import Settings as DWSettings
from warehouse.loader import Warehouse
from warehouse.source import load_publication, stage
from warehouse.quality import validate_source, validate_target
from warehouse.model import prepare_dimensions, prepare_fact


class TransientFailure(RuntimeError):
    pass


class PermanentFailure(RuntimeError):
    pass


def transient(error):
    if isinstance(error, TransientFailure):
        return True
    if isinstance(error, OperationalError):
        code = getattr(error.orig, "pgcode", None)
        return bool(code and (code.startswith("08") or code in ("40001", "40P01", "57P03"))) or (
            code is None and "connection" in str(error.orig).lower() and
            "password" not in str(error.orig).lower())
    if isinstance(error, duckdb.IOException):
        return any(s in str(error).lower() for s in ("lock", "being used", "sharing violation"))
    return isinstance(error, OSError) and error.errno in (errno.EAGAIN, errno.EBUSY, errno.ETIMEDOUT)


def retry_transient(task, task_run, state):
    try:
        state.result()
    except Exception as error:
        return isinstance(error, TransientFailure)
    return False


def safe_operation(fn):
    @wraps(fn)
    def safe(*args, **kwargs):
        started = perf_counter()
        logger = get_run_logger()
        logger.info(json.dumps({"event": "task_start", "task": fn.__name__}))
        try:
            result = fn(*args, **kwargs)
        except Exception as error:
            # Não encaminha mensagens/tracebacks de drivers com dados ou credenciais ao Prefect.
            kind = TransientFailure if transient(error) else PermanentFailure
            logger.error(json.dumps({"event": "task_failed", "task": fn.__name__,
                                     "error_type": type(error).__name__,
                                     "transient": kind is TransientFailure}))
            raise kind(f"{fn.__name__}: {type(error).__name__}; consulte os controles locais.") from None
        logger.info(json.dumps({"event": "task_complete", "task": fn.__name__,
                                "seconds": round(perf_counter()-started, 3)}))
        return result
    return safe


def operation(fn):
    return task(name=fn.__name__, cache_policy=NONE, persist_result=False,
                retry_condition_fn=retry_transient)(safe_operation(fn))


@operation
def check_source(cfg):
    engine = default_engine()
    try:
        with engine.connect().execution_options(postgresql_readonly=True) as c:
            with c.begin():
                c.execute(text("SELECT 1"))
                if c.execute(text("SHOW transaction_read_only")).scalar_one() != "on":
                    raise ValueError("Origem não é somente leitura.")
                tables = set(inspect(c).get_table_names(schema=cfg.schema))
                if not set(COLUMNS) <= tables:
                    raise ValueError("Tabelas obrigatórias indisponíveis.")
        return {"connected": True, "tables": len(COLUMNS)}
    finally:
        engine.dispose()


@operation
def run_etl(cfg, mode, run_id):
    engine = default_engine()
    try:
        return Pipeline(engine, ETLSettings(cfg.data_dir, cfg.schema)).run(mode, run_id)
    finally:
        engine.dispose()


@operation
def validate_silver(cfg, expected_version=None, expected_run=None):
    publication = load_publication(cfg.data_dir)
    manifest = publication["manifest"]
    if expected_version and manifest["version"] != expected_version:
        raise ValueError("Silver mudou; carga DW bloqueada.")
    if expected_run and manifest["run_id"] != expected_run:
        raise ValueError("Execução Silver inesperada.")
    c = duckdb.connect(":memory:")
    try:
        stage(c, publication)
        checks = validate_source(c)
    finally:
        c.close()
    return {"version": manifest["version"], "etl_run_id": manifest["run_id"],
            "fingerprint": publication["fingerprint"], "checks": checks}


@operation
def run_warehouse(cfg, mode, run_id, silver):
    pub = load_publication(cfg.data_dir)
    if pub["manifest"]["version"] != silver["version"] or pub["fingerprint"] != silver["fingerprint"]:
        raise ValueError("Publicação diverge da Silver validada.")
    return Warehouse(DWSettings(cfg.data_dir, cfg.database)).run(mode, run_id)


@operation
def validate_gold(cfg, silver):
    if not cfg.database.is_file():
        raise ValueError("DW ausente: FULL inicial autorizada necessária.")
    c = duckdb.connect(str(cfg.database), read_only=True)
    try:
        c.execute("SET TimeZone='UTC'")
        c.execute("BEGIN")
        state = c.execute("SELECT silver_version,silver_fingerprint,dw_run_id FROM dw_state WHERE singleton=1").fetchone()
        if not state or state[:2] != (silver["version"], silver["fingerprint"]):
            raise ValueError("DW e Silver não reconciliados.")
        pub = load_publication(cfg.data_dir)
        if pub["fingerprint"] != silver["fingerprint"]:
            raise ValueError("Silver alterada após validação.")
        stage(c, pub)  # Somente tabelas TEMP na conexão read_only.
        validate_source(c)
        prepare_dimensions(c)
        prepare_fact(c)
        checks = validate_target(c)
        for view in ("gold_kpis","gold_faturamento_mensal","gold_produtos_mais_vendidos",
                     "gold_ranking_vendedores","gold_faturamento_uf","gold_clientes_recorrentes",
                     "gold_vendas_detalhadas","gold_status_carga"):
            c.execute("SELECT * FROM " + view + " LIMIT 0")
        revenue, orders, items = c.execute("SELECT faturamento_total,pedidos_faturados,itens_faturados FROM gold_kpis").fetchone()
        if (str(revenue), orders, items) != (checks["net_value"], checks["billed_orders"], checks["fact_items"]):
            raise ValueError("Gold diverge da fato validada.")
        return {"dw_run_id": state[2], "checks": checks, "faturamento_total": str(revenue),
                "pedidos_faturados": orders, "itens_faturados": items}
    finally:
        c.close()


@operation
def finalize(cfg, report):
    from uuid import uuid4
    attempt = report.get("prefect_run_id") or str(uuid4())
    atomic_json(cfg.data_dir / "orchestration/runs" / report["run_id"] / (attempt + ".json"), report)
    atomic_json(cfg.data_dir / "orchestration/runs" / (report["run_id"] + ".json"), report)
    return report
