import os
from pathlib import Path
import subprocess
import sys
import json
from unittest.mock import Mock,patch

import pytest
from prefect import get_client
from prefect.settings import get_current_settings
from prefect.testing.utilities import prefect_test_harness
from prefect.client.schemas.actions import WorkPoolCreate
from orchestration import operations as ops
from orchestration.monitor import summarize


@pytest.fixture
def local_env(monkeypatch,tmp_path):
    monkeypatch.setenv("PREFECT_API_URL","http://127.0.0.1:4200/api")
    monkeypatch.setenv("PREFECT_HOME",str(tmp_path/"prefect"))
    monkeypatch.delenv("PASTEL_WORK_POOL",raising=False)
    return tmp_path


def test_deployment_contract(local_env):
    s=ops.specification()
    assert s["name"]=="pastel-da-casa-incremental-daily"
    assert s["pool"]=="pastel-da-casa-local-pool"
    assert s["parameters"]=={"mode":"incremental","dry_run":False,"validate_only":False,"allow_persistent":True,"allow_full":False}
    assert s["paused"] and not s["active"]
    assert s["cron"]=="10 15 * * *" and s["timezone"]=="America/Sao_Paulo"


@pytest.mark.parametrize("value",["","https://api.prefect.cloud/api","http://user:password@localhost:4200/api","http://localhost:4200/api?token=example"])
def test_reject_nonlocal_or_credential_urls(local_env,monkeypatch,value):
    monkeypatch.setenv("PREFECT_API_URL",value)
    with pytest.raises(ValueError):ops.api_url()


def test_worker_virtualenv_and_limits(local_env):
    command=ops.worker_command(True)
    assert command[0]==sys.executable
    assert "--run-once" in command
    assert command[command.index("--limit")+1]=="1"
    assert command[command.index("--install-policy")+1]=="never"
    assert "--no-create-pool-if-not-found" in command


def test_worker_environment_excludes_credentials(local_env,monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD","example-do-not-copy")
    env=ops.worker_environment()
    assert "POSTGRES_PASSWORD" not in env
    assert env["PYTHONPATH"]==str(ops.ROOT)


def test_schedule_activation_guard(local_env):
    with pytest.raises(ValueError,match="autorização"):
        ops.schedule("resume")


def test_alert_sanitization_and_attempts(local_env):
    result=summarize({"id":"id","name":"run","state_type":"FAILED","state":{"message":"sensitive-value"},
                      "parameters":{"run_id":"job"},"auto_scheduled":True,"expected_start_time":"2026-11-05T18:10:00Z"},[{"name":"etl","state_type":"FAILED","run_count":3}])
    assert result["tasks"][0]["attempts"]==3
    assert result["tasks"][0]["error"]
    assert "sensitive-value" not in json.dumps(result)
    assert result["logical_run_id"]=="job"
    assert result["auto_scheduled"] is True
    assert result["expected_start_time"]=="2026-11-05T18:10:00Z"


def test_offline_deployment_build(local_env):
    d=ops.build_deployment()
    assert d.paused and len(d.schedules)==1
    assert not d.schedules[0].active
    assert d.schedules[0].schedule.timezone=="America/Sao_Paulo"
    assert d.job_variables["working_dir"]==str(ops.ROOT)
    assert d.concurrency_limit==1


def test_safe_kind_guard(local_env):
    with pytest.raises(ValueError):ops.safe_run("incremental")


@pytest.fixture(scope="module")
def isolated_server():
    previous=os.environ.get("PREFECT_API_URL")
    with prefect_test_harness():
        os.environ["PREFECT_API_URL"]=str(get_current_settings().api.url)
        yield
    if previous is None:os.environ.pop("PREFECT_API_URL",None)
    else:os.environ["PREFECT_API_URL"]=previous


def test_registration_idempotent_no_schedule_dispatched(isolated_server):
    first=ops.register();second=ops.register()
    assert first["deployment_id"]==second["deployment_id"]
    with get_client(sync_client=True) as c:
        p=c.read_work_pool(ops.specification()["pool"])
        d=ops.deployment(c)
        schedules=c.read_deployment_schedules(d.id)
        assert p.type=="process" and p.concurrency_limit==1
        assert d.work_pool_name==p.name and d.paused
        assert len(schedules)==1 and not schedules[0].active
        assert schedules[0].schedule.cron=="10 15 * * *"
        assert schedules[0].schedule.timezone=="America/Sao_Paulo"
        # Nenhum run foi criado apenas por registrar.
        from prefect.client.schemas.filters import FlowRunFilter,FlowRunFilterDeploymentId
        assert not c.read_flow_runs(flow_run_filter=FlowRunFilter(
            deployment_id=FlowRunFilterDeploymentId(any_=[d.id])))


def test_existing_pool_type_not_replaced(isolated_server,monkeypatch):
    monkeypatch.setenv("PASTEL_WORK_POOL","foreign-type-test")
    with get_client(sync_client=True) as c:
        c.create_work_pool(WorkPoolCreate(name="foreign-type-test",type="docker"))
    with pytest.raises(ValueError,match="outro tipo"):ops.register()
    with get_client(sync_client=True) as c:assert c.read_work_pool("foreign-type-test").type=="docker"


def test_worker_restart_pending_run_and_history(isolated_server,tmp_path):
    ops.register()
    env=os.environ.copy();env.update(ops.worker_environment())
    env["PREFECT_WORKER_QUERY_SECONDS"]="1"
    first=ops.safe_run("dry-run")
    def process(label):
        with (tmp_path/(label+".log")).open("w",encoding="utf-8") as log:
            p=subprocess.run(ops.worker_command(True),env=env,cwd=ops.ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=150)
        assert p.returncode==0,(tmp_path/(label+".log")).read_text(encoding="utf-8",errors="replace")[-2000:]
    process("worker-first")
    with get_client(sync_client=True) as c:
        a=c.read_flow_run(first["flow_run_id"])
        assert a.state.is_completed() and a.infrastructure_pid
    # Sem worker rodando: run permanece pendente de processamento, sem começar.
    second=ops.safe_run("dry-run")
    with get_client(sync_client=True) as c:
        pending=c.read_flow_run(second["flow_run_id"])
        assert pending.state.is_scheduled() and pending.start_time is None
    process("worker-restarted")
    with get_client(sync_client=True) as c:
        a=c.read_flow_run(first["flow_run_id"]);b=c.read_flow_run(second["flow_run_id"])
        assert a.state.is_completed() and b.state.is_completed()
        assert a.id!=b.id and a.infrastructure_pid!=b.infrastructure_pid
        d=ops.deployment(c);assert d.paused
        assert len(c.read_deployment_schedules(d.id))==1
        assert not c.read_deployment_schedules(d.id)[0].active
    evidence={"first":str(a.id),"second":str(b.id),"first_pid":a.infrastructure_pid,
              "second_pid":b.infrastructure_pid,"states":[a.state.type.value,b.state.type.value],
              "deployment_paused":True,"schedule_active":False}
    (tmp_path/"restart_evidence.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")


def test_pause_is_safe_and_no_notifications(isolated_server):
    result=ops.schedule("pause")
    assert result=={"paused":True,"schedule_active":False}
