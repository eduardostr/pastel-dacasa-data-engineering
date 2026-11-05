"""Suíte completa isolada, com baseline de replay descartável; não usa destinos principais."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT=Path(__file__).resolve().parents[2]


def file_state():
    paths=[]
    if (ROOT/"data").exists():
        paths += [p for p in (ROOT/"data").rglob("*") if p.is_file() and not p.name.endswith(".lock")]
    if (ROOT/".env").is_file():paths.append(ROOT/".env")
    result={}
    for path in paths:
        with path.open("rb") as stream:result[str(path.relative_to(ROOT))]=hashlib.file_digest(stream,"sha256").hexdigest()
    return result


def business_state():
    from etl.config import default_engine
    from sqlalchemy import text
    result={};engine=default_engine()
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ",postgresql_readonly=True) as c:
            with c.begin():
                for table,key in [("clientes","id_cliente"),("produtos","id_produto"),("vendedores","id_vendedor"),
                                  ("pedidos","id_pedido"),("itens_pedido","id_item"),("movimentacoes_estoque","id_movimentacao")]:
                    if c.execute(text("SELECT to_regclass(:name)"),{"name":"public."+table}).scalar_one():
                        result[table]=list(c.execute(text("SELECT count(*),md5(coalesce(string_agg(to_jsonb(r)::text,'' ORDER BY "+key+"),'')) FROM public."+table+" r")).fetchone())
                result["sequences"]=[list(r) for r in c.execute(text("SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename"))]
    finally:engine.dispose()
    return result


def replay_baseline(destination):
    from unittest.mock import patch
    from uuid import uuid4
    from prefect.testing.utilities import prefect_test_harness
    from etl.tests.support import IsolatedCase
    from orchestration.flows.pipeline import data_pipeline
    from orchestration.tasks import pipeline as tasks
    case=IsolatedCase(methodName="runTest");case.setUp()
    try:
        db=Path(case.temp.name)/"model.duckdb"
        env={"PASTEL_DATA_DIR":str(case.settings.data_dir),"PASTEL_DW_PATH":str(db),
             "PASTEL_SOURCE_SCHEMA":case.schema,"PASTEL_RETRY_SECONDS":"0"}
        job=str(uuid4())
        with patch.dict(os.environ,env),patch.object(tasks,"default_engine",return_value=case.engine):
            with prefect_test_harness():
                data_pipeline(mode="full",allow_persistent=True,allow_full=True,run_id=str(uuid4()))
                result=data_pipeline(mode="incremental",allow_persistent=True,run_id=job)
        destination.mkdir(parents=True,exist_ok=False)
        shutil.copytree(case.settings.data_dir,destination/"data",ignore=shutil.ignore_patterns("*.lock"))
        shutil.copy2(db,destination/"model.duckdb")
        (destination/"SNAPSHOT_READY.json").write_text(json.dumps({
            "logical_run_id":job,"etl_run_id":result["etl_run_id"],"dw_run_id":result["dw_run_id"],
            "silver_version":result["silver_version"],"source_schema":case.schema},indent=2),encoding="utf-8")
    finally:case.doCleanups()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot",type=Path,help="Opcional: snapshot existente compatível; padrão cria baseline real em schema temporário.")
    args=parser.parse_args()
    os.chdir(ROOT)
    sys.path[:0]=[str(ROOT),str(ROOT/"backend"),str(ROOT/"backend/tests")]
    session=Path(tempfile.mkdtemp(prefix="pastel_test_suite_"))
    os.environ.update(PREFECT_HOME=str(session/"prefect"),PREFECT_API_URL="",
                      PREFECT_SERVER_ANALYTICS_ENABLED="false",PASTEL_TEST_PREFECT_RUNTIME="1")
    before_files=file_state();before_pg=business_state()
    import pytest
    snapshot=args.snapshot.resolve() if args.snapshot else session/"snapshot"
    if args.snapshot is None:replay_baseline(snapshot)
    os.environ["PASTEL_RECOVERY_SNAPSHOT"]=str(snapshot)
    from scripts.synthetic_data.isolation import isolated_database
    from sqlalchemy.orm import sessionmaker
    import app.database as database
    code=1
    try:
        with isolated_database(database.engine) as (engine,schema):
            original_engine,original_sessions=database.engine,database.SessionLocal
            try:
                database.engine=engine
                database.SessionLocal=sessionmaker(bind=engine,autoflush=False,autocommit=False)
                code=pytest.main(["backend/tests","frontend/tests","scripts/synthetic_data/tests","etl/tests",
                    "warehouse/tests","orchestration/tests","--import-mode=importlib","-v","--tb=short",
                    "-o","cache_dir="+str(session/"cache"),"--basetemp="+str(session/"pytest"),
                    "--junitxml="+str(session/"results.xml")])
            finally:database.engine, database.SessionLocal=original_engine,original_sessions
    finally:
        checks={"pytest_exit_code":int(code),"data_and_env_unchanged":before_files==file_state(),
                "operational_and_sequences_unchanged":before_pg==business_state()}
        (session/"preservation.json").write_text(json.dumps(checks,indent=2),encoding="utf-8")
        print(json.dumps({"evidence_dir":str(session),**checks}),flush=True)
    if not checks["data_and_env_unchanged"] or not checks["operational_and_sequences_unchanged"]:
        return 1
    return int(code)


if __name__=="__main__":raise SystemExit(main())
