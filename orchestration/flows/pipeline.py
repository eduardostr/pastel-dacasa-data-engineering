from contextlib import ExitStack
from datetime import datetime, timezone
from time import perf_counter

from prefect import flow
from prefect.context import get_run_context

from etl.control.lock import writer_lock
from warehouse.config import Settings as DWSettings
from orchestration.config import Settings, identifiers, plan
from orchestration.tasks import pipeline as tasks


def execute(cfg, specification, ids, invoke, prefect_run_id=None):
    """Sequência síncrona testável; todos os passos de dados passam pelas tasks."""
    if specification["dry_run"]:
        return {**specification, **ids, "status": "PLAN_ONLY"}
    start = perf_counter()
    report = {**ids, "prefect_run_id": prefect_run_id, **specification,
              "started_at": datetime.now(timezone.utc).isoformat(), "steps": {}, "status": "RUNNING"}
    report.pop("steps")
    report["results"] = {}
    dw = DWSettings(cfg.data_dir, cfg.database)
    try:
        with ExitStack() as locks:
            # Locks por recurso, e não por par: destinos compartilhados se excluem.
            # Não conflitam com locks internos do Pipeline/Warehouse.
            if not specification["validate_only"]:
                for directory in sorted([cfg.data_dir / "orchestration/guard",
                                         dw.control_dir / "orchestration/guard"], key=str):
                    locks.enter_context(writer_lock(directory))
            report["results"]["source"] = invoke(tasks.check_source, cfg)
            if not specification["validate_only"]:
                etl = invoke(tasks.run_etl, cfg, specification["mode"], ids["etl_run_id"])
                report["results"]["etl"] = {"run_id": etl["run_id"], "version": etl["version"], "metrics": etl["metrics"]}
            # Impede CLI ETL independente de trocar Silver entre validação e carga.
            # validate_only não cria arquivo de lock e confere versões dentro das validações.
            if not specification["validate_only"]:
                locks.enter_context(writer_lock(cfg.data_dir))
            etl = report["results"].get("etl", {})
            silver = invoke(tasks.validate_silver, cfg, etl.get("version"), etl.get("run_id"))
            report["silver_version"] = silver["version"]
            report["results"]["silver"] = silver
            if not specification["validate_only"]:
                dw_result = invoke(tasks.run_warehouse, cfg, specification["mode"], ids["dw_run_id"], silver)
                report["results"]["warehouse"] = dw_result
                locks.enter_context(writer_lock(dw.control_dir))
            report["results"]["gold"] = invoke(tasks.validate_gold, cfg, silver)
            if specification["validate_only"]:
                report["etl_run_id"] = silver["etl_run_id"]
                report["dw_run_id"] = report["results"]["gold"]["dw_run_id"]
            report["status"] = "VALIDATED" if specification["validate_only"] else "COMPLETED"
    except Exception as error:
        report["status"] = "FAILED"
        report["error_type"] = type(error).__name__
        report["error_message"] = (str(error) if isinstance(error, (tasks.TransientFailure, tasks.PermanentFailure))
                                   else "Execução interrompida; consulte o estado da etapa no Prefect.")
        # Nunca replica mensagens de exceções arbitrárias.
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["duration_seconds"] = round(perf_counter()-start, 3)
        if not specification["validate_only"]:
            # Falha de auditoria não mascara a causa original; Prefect mantém estado Failed.
            try:
                invoke(tasks.finalize, cfg, report)
            except Exception:
                if report["status"] != "FAILED":
                    raise
    return report


def operational_run_name():
    import os
    import re
    from prefect.runtime import flow_run
    parameters=flow_run.parameters
    environment=re.sub(r"[^A-Za-z0-9_-]","_",os.getenv("PASTEL_ENVIRONMENT","local"))[:20]
    mode=re.sub(r"[^A-Za-z0-9_-]","_",str(parameters.get("mode","incremental")))[:15]
    logical=str(parameters.get("run_id") or flow_run.id)[:8]
    return f"pastel-{environment}-{mode}-{logical}"


@flow(name="pastel-da-casa-data-pipeline", flow_run_name=operational_run_name,
      retries=0, persist_result=False, log_prints=False)
def data_pipeline(mode="incremental", validate_only=False, dry_run=False,
                  allow_persistent=False, allow_full=False, run_id=None):
    spec = plan(mode, validate_only, dry_run, allow_persistent, allow_full)
    cfg = Settings.environment()
    ids = identifiers(run_id)
    prefect_id = str(get_run_context().flow_run.id)
    def invoke(task, *args):
        return task.with_options(retries=0 if task is tasks.finalize else cfg.attempts-1,
                                 retry_delay_seconds=cfg.retry_seconds)(*args)
    return execute(cfg, spec, ids, invoke, prefect_id)
