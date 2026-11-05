"""Operação local Prefect Process; registro sempre pausado, sem cargas."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault("PREFECT_HOME",str(ROOT/".prefect"))
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED","false")


def api_url():
    value=os.getenv("PREFECT_API_URL","").rstrip("/")
    url=urlparse(value)
    if (url.scheme!="http" or url.hostname not in ("localhost","127.0.0.1","::1")
        or url.username or url.password or url.query or url.fragment or url.path!="/api"):
        raise ValueError("Configure PREFECT_API_URL=http://127.0.0.1:4200/api para o servidor local.")
    return value


def specification():
    from orchestration.deployment import specification as legacy
    old=legacy()
    return {**old,"name":"pastel-da-casa-incremental-daily",
            "pool":os.getenv("PASTEL_WORK_POOL","pastel-da-casa-local-pool"),
            "schedule_slug":"daily-incremental",
            "parameters":{"mode":"incremental","dry_run":False,"validate_only":False,
                          "allow_persistent":True,"allow_full":False}}


def worker_environment():
    env={"PYTHONPATH":str(ROOT),"PREFECT_API_URL":api_url(),
         "PREFECT_HOME":os.environ["PREFECT_HOME"],"PREFECT_SERVER_ANALYTICS_ENABLED":"false",
         "PASTEL_ENVIRONMENT":"local","PYTHONIOENCODING":"utf-8"}
    for key in ("PASTEL_DATA_DIR","PASTEL_DW_PATH","PASTEL_SOURCE_SCHEMA",
                "PASTEL_MAX_ATTEMPTS","PASTEL_RETRY_SECONDS"):
        if key in os.environ:env[key]=os.environ[key]
    return env


def build_deployment():
    from prefect.schedules import Cron
    from orchestration.flows.pipeline import data_pipeline
    spec=specification()
    return data_pipeline.to_deployment(
        name=spec["name"],work_pool_name=spec["pool"],paused=True,
        schedules=[Cron(spec["cron"],timezone=spec["timezone"],active=False,slug=spec["schedule_slug"])],
        concurrency_limit=1,parameters=spec["parameters"],tags=["pastel-da-casa","local","incremental"],
        description="Process local; cron registrado inativo. Cargas exigem autorização.",
        job_variables={"working_dir":str(ROOT),"stream_output":True,"env":worker_environment()})


def register():
    api_url()
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import WorkPoolCreate,WorkPoolUpdate
    from prefect.exceptions import ObjectNotFound
    from prefect.workers.process import ProcessWorker
    spec=specification()
    deployment=build_deployment()  # Valida cron/timezone antes de escrever metadados.
    with get_client(sync_client=True) as client:
        try:
            pool=client.read_work_pool(spec["pool"])
            if pool.type!="process":raise ValueError("Pool existente possui outro tipo; não será substituído.")
        except ObjectNotFound:
            pool=client.create_work_pool(WorkPoolCreate(name=spec["pool"],type="process",
                base_job_template=ProcessWorker.get_default_base_job_template(),concurrency_limit=1))
        if pool.concurrency_limit!=1:
            client.update_work_pool(spec["pool"],WorkPoolUpdate(concurrency_limit=1))
        try:
            existing=client.read_deployment_by_name("pastel-da-casa-data-pipeline/"+spec["name"])
            if existing.work_pool_name!=spec["pool"]:
                raise ValueError("Deployment existente pertence a outro pool; revisão manual necessária.")
        except ObjectNotFound:pass
    deployment_id=deployment.apply()
    return {"deployment_id":str(deployment_id),"pool":spec["pool"],"name":spec["name"],"paused":True,
            "schedule_active":False,"cron":spec["cron"],"timezone":spec["timezone"]}


def deployment(client):
    spec=specification()
    return client.read_deployment_by_name("pastel-da-casa-data-pipeline/"+spec["name"])


def safe_run(kind="validate-only"):
    if kind not in ("dry-run","validate-only"):raise ValueError("Modo de teste inválido.")
    api_url()
    from prefect.client.orchestration import get_client
    spec=specification()
    with get_client(sync_client=True) as client:
        d=deployment(client)
        if d.work_pool_name!=spec["pool"]:raise ValueError("Deployment associado a outro pool.")
        job=str(uuid4())
        run=client.create_flow_run_from_deployment(d.id,
            name="pastel-local-safe-"+kind+"-"+job[:8],
            parameters={"mode":"incremental","dry_run":kind=="dry-run","validate_only":kind=="validate-only",
                        "allow_persistent":False,"allow_full":False,"run_id":job},
            tags=["pastel-da-casa","safe-test",kind],idempotency_key="safe-"+job)
        return {"flow_run_id":str(run.id),"logical_run_id":job,"kind":kind,"state":run.state.type.value}


def schedule(action,authorized=False):
    if action not in ("pause","resume"):raise ValueError("Ação inválida.")
    if action=="resume" and not authorized:
        raise ValueError("Ativação exige autorização explícita e --authorize-recurring.")
    api_url()
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import DeploymentUpdate
    with get_client(sync_client=True) as client:
        d=deployment(client)
        schedules=client.read_deployment_schedules(d.id)
        spec=specification()
        if len(schedules)!=1 or schedules[0].slug!=spec["schedule_slug"]:
            raise ValueError("Agendamentos divergentes; revisão manual necessária.")
        if action=="pause":
            client.update_deployment(d.id,DeploymentUpdate(paused=True))
            client.update_deployment_schedule(d.id,schedules[0].id,active=False)
        else:
            if d.work_pool_name!=spec["pool"]:raise ValueError("Pool divergente.")
            client.update_deployment_schedule(d.id,schedules[0].id,active=True)
            client.update_deployment(d.id,DeploymentUpdate(paused=False))
    return {"paused":action=="pause","schedule_active":action=="resume"}


def worker_command(run_once=False):
    spec=specification()
    command=[sys.executable,"-m","prefect","worker","start","--pool",spec["pool"],
             "--type","process","--name",os.getenv("PASTEL_WORKER_NAME","pastel-local-worker"),
             "--limit","1","--install-policy","never","--no-create-pool-if-not-found"]
    if run_once:command.append("--run-once")
    return command


def start_worker(run_once=False):
    env=os.environ.copy();env.update(worker_environment())
    # Foreground: Ctrl+C é tratado pelo CLI Prefect; nenhum serviço Windows é instalado.
    return subprocess.call(worker_command(run_once),env=env,cwd=ROOT)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("plan")
    sub.add_parser("register")
    worker=sub.add_parser("worker");worker.add_argument("--run-once",action="store_true")
    safe=sub.add_parser("safe-run");safe.add_argument("--kind",choices=["dry-run","validate-only"],default="validate-only")
    sched=sub.add_parser("schedule");sched.add_argument("state",choices=["pause","resume"])
    sched.add_argument("--authorize-recurring",action="store_true")
    args=p.parse_args()
    if args.action=="plan":result=specification()
    elif args.action=="register":result=register()
    elif args.action=="safe-run":result=safe_run(args.kind)
    elif args.action=="schedule":result=schedule(args.state,args.authorize_recurring)
    else:raise SystemExit(start_worker(args.run_once))
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=="__main__":main()
