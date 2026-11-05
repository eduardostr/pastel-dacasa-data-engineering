"""Cenários novos entre componentes: sem hooks expostos no ambiente principal."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
from unittest.mock import patch

import duckdb
import pytest
from prefect import task
from prefect.client.orchestration import get_client
from prefect.testing.utilities import prefect_test_harness
from prefect.utilities.asyncutils import run_coro_as_sync

from etl.config import Settings as ETLSettings, default_engine
from etl.pipeline import Pipeline
from etl.tests.support import IsolatedCase
from warehouse.config import Settings as DWSettings
from warehouse.loader import Warehouse
from orchestration.config import identifiers
from orchestration.flows.pipeline import data_pipeline
from orchestration.tasks import pipeline as tasks

pytestmark = pytest.mark.skipif(not os.getenv("PASTEL_RECOVERY_SNAPSHOT"), reason="Requer snapshot isolado expl?cito")

def replay_profile():
    snapshot=os.getenv("PASTEL_RECOVERY_SNAPSHOT")
    path=Path(snapshot)/"SNAPSHOT_READY.json" if snapshot else None
    return json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else {}


PRIOR_JOB = os.getenv("PASTEL_REPLAY_RUN_ID") or replay_profile().get(
    "logical_run_id", "d6cb127a-1507-4835-8bbd-0e3b79cf62f7")


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for layer in ("bronze","silver") for p in (root/layer).rglob("*") if p.is_file()}


def state(root, db):
    manifest=json.loads((root/"control/current.json").read_text(encoding="utf-8"))
    c=duckdb.connect(str(db),read_only=True)
    try:
        tables={t:c.execute("SELECT count(*),bit_xor(hash(r)) FROM "+t+" r").fetchone()
                for t in ("dim_cliente","dim_produto","dim_vendedor","dim_tempo","fato_vendas")}
        gold=c.execute("SELECT * FROM gold_kpis").fetchone()
        version=c.execute("SELECT silver_version,silver_fingerprint FROM dw_state").fetchone()
        duplicates=c.execute("SELECT count(*)-count(DISTINCT id_item) FROM fato_vendas").fetchone()[0]
    finally:c.close()
    return {"manifest":manifest,"tables":tables,"gold":gold,"dw_version":version,
            "duplicates":duplicates,"files":hashes(root)}


def save_evidence(root, db, node):
    target = Path(os.environ["PASTEL_RECOVERY_SNAPSHOT"]).parent / "evidence"
    target.mkdir(exist_ok=True)
    reports = []
    for path in (root / "orchestration/runs").glob("*.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        reports.append({k: report.get(k) for k in (
            "run_id", "prefect_run_id", "etl_run_id", "dw_run_id", "status",
            "silver_version", "error_type", "duration_seconds")})
    current = state(root, db)
    artifact = {"test": node.nodeid, "reports": reports, "gold": current["gold"],
                "tables": current["tables"], "duplicates": current["duplicates"],
                "silver_version": current["manifest"]["version"],
                "watermarks": current["manifest"]["watermarks"]}
    name = hashlib.sha256(node.nodeid.encode()).hexdigest()[:16] + ".json"
    (target / name).write_text(json.dumps(artifact, default=str, indent=2), encoding="utf-8")


@pytest.fixture(scope="module")
def server():
    with prefect_test_harness():yield


@pytest.fixture
def copied_run(tmp_path,monkeypatch,server,request):
    snapshot=Path(os.environ["PASTEL_RECOVERY_SNAPSHOT"])
    root=tmp_path/"data";db=tmp_path/"copy.duckdb"
    shutil.copytree(snapshot/"data",root)
    shutil.copy2(snapshot/"model.duckdb",db)
    monkeypatch.setenv("PASTEL_DATA_DIR",str(root))
    monkeypatch.setenv("PASTEL_DW_PATH",str(db))
    monkeypatch.setenv("PASTEL_SOURCE_SCHEMA",replay_profile().get("source_schema","public"))
    monkeypatch.setenv("PASTEL_RETRY_SECONDS","0")
    # A fotografia concluída deve passar pela rota REUSED real, jamais extrair da origem.
    def never_extract(*args,**kwargs):
        raise AssertionError("Replay tentou extrair novamente")
    monkeypatch.setattr("etl.pipeline.extract",never_extract)
    original=tasks.check_source.fn
    tasks.check_source.fn=tasks.safe_operation(lambda cfg: {"connected":True,"source":"mock-isolated"})
    yield root,db
    save_evidence(root,db,request.node)
    tasks.check_source.fn=original


def run(job=PRIOR_JOB,**kwargs):
    return data_pipeline(mode="incremental",allow_persistent=True,run_id=job,**kwargs)


async def read_states(ids):
    async with get_client() as client:
        return [(await client.read_flow_run(i)).state.type.value for i in ids]


def test_real_replay_same_logical_id_new_prefect_runs(copied_run):
    root,db=copied_run
    before=state(root,db)
    first=run();second=run()
    after=state(root,db)
    assert first["prefect_run_id"]!=second["prefect_run_id"]
    assert first["etl_run_id"]==second["etl_run_id"]==identifiers(PRIOR_JOB)["etl_run_id"]
    assert first["dw_run_id"]==second["dw_run_id"]==identifiers(PRIOR_JOB)["dw_run_id"]
    assert first["results"]["warehouse"]["status"]==second["results"]["warehouse"]["status"]=="REUSED"
    assert before==after
    assert after["duplicates"]==0
    c=sqlite3.connect(root/"control/audit.sqlite")
    try:
        rows=c.execute("SELECT status FROM attempts WHERE run_id=? ORDER BY started_at DESC LIMIT 2",
                       (identifiers(PRIOR_JOB)["etl_run_id"],)).fetchall()
        assert rows==[("REUSED",),("REUSED",)]
    finally:c.close()
    assert run_coro_as_sync(read_states([first["prefect_run_id"],second["prefect_run_id"]]))==["COMPLETED","COMPLETED"]


def test_transient_retry_recovers_without_duplication(copied_run):
    root,db=copied_run;before=state(root,db);calls=[]
    def source(cfg):
        calls.append(1)
        if len(calls)<3:
            from sqlalchemy.exc import OperationalError
            raise OperationalError(None,None,ConnectionError("connection temporarily unavailable"))
        return {"connected":True}
    with patch.object(tasks.check_source,"fn",tasks.safe_operation(source)):
        result=run()
    assert len(calls)==3
    assert result["status"]=="COMPLETED"
    assert state(root,db)==before


def test_transient_retry_stops_at_three(copied_run):
    root,db=copied_run;before=state(root,db);calls=[]
    def unavailable(cfg):
        calls.append(1)
        raise tasks.TransientFailure("controlled temporary outage")
    with patch.object(tasks.check_source,"fn",tasks.safe_operation(unavailable)):
        with pytest.raises(tasks.TransientFailure):
            run()
    assert len(calls)==3
    assert state(root,db)==before


def test_invalid_candidate_is_permanent_and_stops_dw(copied_run,tmp_path):
    root,db=copied_run;before=state(root,db);calls=[]
    original=tasks.load_publication
    # Arquivo inválido fora da publicação oficial. A publicação anterior fica intacta.
    bad=tmp_path/"invalid-candidate.parquet";bad.write_bytes(b"invalid parquet")
    def invalid(root):
        publication=original(root)
        publication["files"]["produtos"]["path"]=bad
        return publication
    def forbidden(*args):
        calls.append(1);raise AssertionError("DW não deveria executar")
    with patch.object(tasks,"load_publication",side_effect=invalid),patch.object(tasks.run_warehouse,"fn",forbidden):
        failed= data_pipeline(mode="incremental",allow_persistent=True,run_id=PRIOR_JOB,return_state=True)
    assert failed.is_failed()
    assert not calls
    assert state(root,db)==before
    # Estado real do Prefect, não só a exceção local.
    assert run_coro_as_sync(read_states([str(failed.state_details.flow_run_id)]))==["FAILED"]


@pytest.fixture
def small_pipeline(tmp_path,monkeypatch,server,request):
    # Reutiliza a fixture de integração PostgreSQL da ETL, sem dados públicos.
    case=IsolatedCase(methodName="runTest");case.setUp()
    try:
        root=case.settings.data_dir;db=tmp_path/"isolated.duckdb"
        case.pipeline.run("full")
        Warehouse(DWSettings(root,db)).run("full")
        monkeypatch.setenv("PASTEL_DATA_DIR",str(root))
        monkeypatch.setenv("PASTEL_DW_PATH",str(db))
        monkeypatch.setenv("PASTEL_SOURCE_SCHEMA",case.schema)
        monkeypatch.setenv("PASTEL_RETRY_SECONDS","0")
        with patch.object(tasks,"default_engine",return_value=case.engine):
            yield root,db
    finally:
        try:save_evidence(root,db,request.node)
        finally:case.doCleanups()


@pytest.mark.parametrize("phase",[
    "bronze_move","silver_publish","before_dw","dw_before_commit","dw_after_commit","final_audit"])
def test_flow_publication_failure_and_same_job_recovery(small_pipeline,phase):
    root,db=small_pipeline;before=state(root,db);job=str(uuid4());ids=identifiers(job)
    original_etl=Pipeline.run;original_dw=Warehouse.run;original_replace=os.replace
    def etl_hook(point):
        if point=="before_publish":raise RuntimeError("controlled Silver publication failure")
    def dw_hook(point):
        expected="before_commit" if phase=="dw_before_commit" else "after_commit"
        if point==expected:raise RuntimeError("controlled DW publication failure")
    def etl_run(self,*args,**kwargs):
        kwargs["fault"]=etl_hook
        return original_etl(self,*args,**kwargs)
    def dw_run(self,*args,**kwargs):
        kwargs["fault"]=dw_hook
        return original_dw(self,*args,**kwargs)
    def replace(src,dst):
        dst=Path(dst)
        if dst.parent.name==ids["etl_run_id"] and dst.parent.parent.name=="bronze":
            raise RuntimeError("controlled failure after extraction before Bronze publication")
        return original_replace(src,dst)
    def fail(*args,**kwargs):
        raise tasks.PermanentFailure("controlled failure at "+phase)
    if phase=="bronze_move":context=patch("os.replace",side_effect=replace)
    elif phase=="silver_publish":context=patch.object(Pipeline,"run",etl_run)
    elif phase=="before_dw":context=patch.object(tasks.run_warehouse,"fn",fail)
    elif phase in ("dw_before_commit","dw_after_commit"):context=patch.object(Warehouse,"run",dw_run)
    else:context=patch.object(tasks.finalize,"fn",fail)
    with context:
        failed=data_pipeline(mode="incremental",allow_persistent=True,run_id=job,return_state=True)
    assert failed.is_failed()
    at_failure=state(root,db)
    assert at_failure["tables"]==before["tables"]  # Sem alteração de negócio na origem isolada.
    assert at_failure["gold"]==before["gold"]
    assert all(at_failure["files"].get(k)==v for k,v in before["files"].items())
    if phase in ("bronze_move","silver_publish"):
        assert at_failure["manifest"]==before["manifest"]
    else:
        # ETL já comitou: não existe rollback distribuído de Silver/DW.
        assert at_failure["manifest"]["run_id"]==ids["etl_run_id"]
    if phase in ("bronze_move","silver_publish","before_dw","dw_before_commit"):
        assert at_failure["dw_version"]==before["dw_version"]
    else:assert at_failure["dw_version"][0]==at_failure["manifest"]["version"]
    files_at_failure=at_failure["files"]
    recovered=data_pipeline(mode="incremental",allow_persistent=True,run_id=job)
    after=state(root,db)
    assert recovered["status"]=="COMPLETED"
    assert after["manifest"]["run_id"]==ids["etl_run_id"]
    assert after["dw_version"][0]==after["manifest"]["version"]
    assert after["gold"]==before["gold"] and after["duplicates"]==0
    if phase not in ("bronze_move","silver_publish"):
        assert after["manifest"]==at_failure["manifest"]
        assert after["files"]==files_at_failure
    if phase=="silver_publish":
        assert {k:v for k,v in after["files"].items() if k.startswith("bronze/")}=={
            k:v for k,v in files_at_failure.items() if k.startswith("bronze/")}
    assert str(failed.state_details.flow_run_id)!=recovered["prefect_run_id"]
    assert run_coro_as_sync(read_states([str(failed.state_details.flow_run_id),recovered["prefect_run_id"]]))==["FAILED","COMPLETED"]


def test_concurrent_full_and_incremental_are_excluded(copied_run):
    root,db=copied_run;before=state(root,db);entered=Event();release=Event()
    def source(cfg):
        entered.set()
        if not release.wait(30):raise RuntimeError("test release timed out")
        return {"connected":True}
    with patch.object(tasks.check_source,"fn",tasks.safe_operation(source)):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(run)
            assert entered.wait(15)
            try:
                failed=data_pipeline(mode="full",allow_persistent=True,allow_full=True,
                                     run_id=str(uuid4()),return_state=True)
                assert failed.is_failed()
            finally:release.set()
            result=first.result(timeout=40)
    assert result["status"]=="COMPLETED"
    assert state(root,db)==before
    reports=list((root/"orchestration/runs").glob("*.json"))
    assert any(json.loads(p.read_text())["status"]=="FAILED" for p in reports)
