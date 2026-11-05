"""Prova de scheduling em deployment separado, somente validate-only."""
import argparse
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4

import requests
from orchestration.operations import ROOT,api_url,worker_command,worker_environment
from orchestration.tests.prepare_snapshot import prepare
from etl.config import default_engine
from sqlalchemy import text


def fingerprint(path):
    with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def protected():
    return {str(p.relative_to(ROOT)):fingerprint(p) for p in (ROOT/"data").rglob("*")
            if p.is_file() and not p.name.endswith(".lock")}


def source_state():
    engine=default_engine();result={}
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ",postgresql_readonly=True) as c:
            with c.begin():
                for table,key in [("clientes","id_cliente"),("produtos","id_produto"),("vendedores","id_vendedor"),
                                  ("pedidos","id_pedido"),("itens_pedido","id_item"),("movimentacoes_estoque","id_movimentacao")]:
                    result[table]=list(c.execute(text("SELECT count(*),md5(coalesce(string_agg(to_jsonb(r)::text,'' ORDER BY "+key+"),'')) FROM public."+table+" r")).fetchone())
                result["sequences"]=[list(r) for r in c.execute(text(
                    "SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename"))]
    finally:engine.dispose()
    return result


def run_probe(delay_seconds=45,timeout_seconds=240):
    if delay_seconds<30 or timeout_seconds<delay_seconds+60:
        raise ValueError("Delay mínimo de 30s e timeout pelo menos delay+60.")
    api=api_url()
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import WorkPoolCreate,WorkPoolUpdate,DeploymentUpdate,DeploymentScheduleCreate
    from prefect.client.schemas.schedules import IntervalSchedule
    from prefect.client.schemas.filters import FlowRunFilter,FlowRunFilterDeploymentId
    from prefect.workers.process import ProcessWorker
    from orchestration.flows.pipeline import data_pipeline
    job=str(uuid4())
    prefix="pastel-scheduling-probe-"+job[:8]
    session=Path(tempfile.mkdtemp(prefix="pastel_stage114_"))
    deadline=time.monotonic()+timeout_seconds
    report={"probe_id":job,"started_at":datetime.now(timezone.utc).isoformat(),"status":"PREPARING",
            "test_pool":prefix,"test_deployment":prefix}
    with get_client(sync_client=True) as client:
        main=client.read_deployment_by_name("pastel-da-casa-data-pipeline/pastel-da-casa-incremental-daily")
        main_pool=client.read_work_pool("pastel-da-casa-local-pool")
        if not main.paused or not main_pool.is_paused or any(s.active for s in client.read_deployment_schedules(main.id)):
            raise ValueError("Deployment, cron e pool principais devem estar pausados antes do teste.")
    before=protected();business=source_state()
    snapshot=prepare(session/"snapshot")
    backup=ROOT/"backups/etapa11_4"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+job)
    required=sum(p.stat().st_size for p in snapshot.rglob("*") if p.is_file())
    if shutil.disk_usage(ROOT).free<required+100*1024**2:raise RuntimeError("Espaço insuficiente para backup.")
    backup.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(snapshot,backup)
    if any(fingerprint(p)!=fingerprint(backup/p.relative_to(snapshot)) for p in snapshot.rglob("*") if p.is_file()):
        raise RuntimeError("Backup divergiu do snapshot.")
    report["backup"]=str(backup.relative_to(ROOT)).replace("\\","/")
    report["baseline"]=json.loads((ROOT/"data/control/current.json").read_text(encoding="utf-8"))
    anchor=datetime.now(timezone.utc)+timedelta(seconds=delay_seconds)
    report["test_anchor"]=anchor.isoformat()
    d_id=None;pool_created=False;executed=None
    try:
        with get_client(sync_client=True) as client:
            client.create_work_pool(WorkPoolCreate(name=prefix,type="process",
                concurrency_limit=1,base_job_template=ProcessWorker.get_default_base_job_template()))
            pool_created=True
        env=worker_environment()
        env.update(PASTEL_DATA_DIR=str(snapshot/"data"),PASTEL_DW_PATH=str(snapshot/"model.duckdb"),
                   PREFECT_HOME=str(session/"worker-home"),PASTEL_SOURCE_SCHEMA="public")
        schedule=DeploymentScheduleCreate(schedule=IntervalSchedule(interval=timedelta(days=1),
            anchor_date=anchor,timezone="America/Sao_Paulo"),active=True,slug="temporary-safe-probe")
        deployment=data_pipeline.to_deployment(name=prefix,work_pool_name=prefix,paused=False,
            schedules=[schedule],concurrency_limit=1,
            parameters={"mode":"incremental","dry_run":False,"validate_only":True,
                        "allow_persistent":False,"allow_full":False,"run_id":job},
            tags=["pastel-da-casa","safe-scheduler-probe"],
            job_variables={"working_dir":str(ROOT),"stream_output":True,"env":env})
        d_id=deployment.apply()
        report["test_deployment_id"]=str(d_id)
        print(json.dumps({"session":str(session),"backup":report["backup"],"test_deployment_id":str(d_id),
                          "anchor":anchor.isoformat(),"status":"WAITING_FOR_SCHEDULER"}),flush=True)
        while time.monotonic()<deadline:
            with get_client(sync_client=True) as client:
                runs=client.read_flow_runs(flow_run_filter=FlowRunFilter(
                    deployment_id=FlowRunFilterDeploymentId(any_=[d_id])),limit=20)
            candidates=[r for r in runs if r.auto_scheduled and r.expected_start_time<=datetime.now(timezone.utc)]
            if candidates:
                executed=min(candidates,key=lambda r:r.expected_start_time)
                break
            time.sleep(2)
        if executed is None:raise TimeoutError("Scheduler não criou run automático devido dentro do limite.")
        report["flow_run_id"]=str(executed.id)
        command=worker_command(True)
        command[command.index("--pool")+1]=prefix
        command[command.index("--name")+1]=prefix+"-worker"
        command+=["--prefetch-seconds","0"]
        child_env=dict(__import__("os").environ);child_env.update(env)
        with (session/"worker.log").open("w",encoding="utf-8") as log:
            child=subprocess.run(command,cwd=ROOT,env=child_env,stdout=log,stderr=subprocess.STDOUT,
                                 timeout=max(30,deadline-time.monotonic()))
        report["worker_exit_code"]=child.returncode
        with get_client(sync_client=True) as client:r=client.read_flow_run(executed.id)
        report["flow"]={key:getattr(r,key) for key in (
            "id","name","auto_scheduled","expected_start_time","start_time","end_time","total_run_time","infrastructure_pid")}
        report["flow"]["state"]=r.state.type.value
        for label,endpoint,body in [
            ("tasks","task_runs/filter",{"flow_runs":{"id":{"any_":[str(r.id)]}},"limit":100}),
            ("logs","logs/filter",{"logs":{"flow_run_id":{"any_":[str(r.id)]}},"limit":200})]:
            response=requests.post(api+"/"+endpoint,json=body,timeout=15);response.raise_for_status()
            records=response.json()
            report[label]=([{key:t.get(key) for key in ("id","name","state_type","run_count","total_run_time")} for t in records]
                           if label=="tasks" else {"count":len(records),"all_messages_private":True})
        if child.returncode or not r.state.is_completed():raise RuntimeError("Flow automático seguro não concluiu.")
        if len(report["tasks"])!=3 or any(t["state_type"]!="COMPLETED" for t in report["tasks"]):
            raise RuntimeError("Tasks de validação não concluíram.")
        if not report["logs"]["count"]:raise RuntimeError("Logs não encontrados.")
        report["status"]="COMPLETED"
    except Exception as error:
        report["status"]="FAILED"
        report["error_type"]=type(error).__name__
        raise
    finally:
        with get_client(sync_client=True) as client:
            if pool_created:client.update_work_pool(prefix,WorkPoolUpdate(is_paused=True))
            if d_id:
                client.update_deployment(d_id,DeploymentUpdate(paused=True))
                for s in client.read_deployment_schedules(d_id):
                    client.update_deployment_schedule(d_id,s.id,active=False)
        report["cleanup"]={"test_pool_paused":pool_created,"test_deployment_paused":bool(d_id),
                           "test_schedule_active":False,"main_remains_paused":True}
        report["data_files_unchanged"]=protected()==before
        report["operational_and_sequences_unchanged"]=source_state()==business
        report["finished_at"]=datetime.now(timezone.utc).isoformat()
        (session/"result.json").write_text(json.dumps(report,default=str,ensure_ascii=False,indent=2),encoding="utf-8")
        (Path(tempfile.gettempdir())/"pastel_stage114_session.txt").write_text(str(session),encoding="utf-8")
    if not report["data_files_unchanged"] or not report["operational_and_sequences_unchanged"]:
        raise RuntimeError("Estado principal mudou durante o teste.")
    print(json.dumps({"session":str(session),"status":report["status"],"flow_run_id":report["flow_run_id"],
                     "auto_scheduled":report["flow"]["auto_scheduled"],"seconds":str(report["flow"]["total_run_time"]),
                     "data_files_unchanged":report["data_files_unchanged"],
                     "operational_and_sequences_unchanged":report["operational_and_sequences_unchanged"]},indent=2),flush=True)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay-seconds",type=int,default=45)
    parser.add_argument("--timeout-seconds",type=int,default=240)
    args=parser.parse_args()
    run_probe(args.delay_seconds,args.timeout_seconds)
