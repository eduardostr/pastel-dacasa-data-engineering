import os
from pathlib import Path
import tempfile
os.environ.setdefault("PREFECT_HOME",str(Path(tempfile.gettempdir())/"pastel_prefect11_testhome"))
os.environ.setdefault("PREFECT_SERVER_ANALYTICS_ENABLED","false")
import json
import unittest
from unittest.mock import Mock,patch
from uuid import uuid4

import duckdb
from prefect.logging import disable_run_logger
from orchestration.config import Settings,identifiers,plan
from orchestration.flows.pipeline import execute,data_pipeline
from orchestration.tasks import pipeline as tasks
from orchestration.deployment import specification
from etl.control.lock import writer_lock
from warehouse.tests.fixtures import WarehouseCase


class ConfigTests(unittest.TestCase):
    def test_defaults_and_flow(self):
        self.assertEqual(data_pipeline.name,"pastel-da-casa-data-pipeline")
        self.assertEqual(plan(dry_run=True)["mode"],"incremental")
        self.assertEqual(Settings().attempts,3)

    def test_guards(self):
        for kwargs in ({},{"mode":"full","allow_persistent":True},
                       {"mode":"bad","dry_run":True},{"dry_run":True,"validate_only":True}):
            with self.assertRaises(ValueError):plan(**kwargs)
        self.assertEqual(plan("full",allow_persistent=True,allow_full=True)["mode"],"full")

    def test_stable_ids(self):
        run=str(uuid4())
        self.assertEqual(identifiers(run),identifiers(run))
        self.assertNotEqual(identifiers(run)["etl_run_id"],identifiers(run)["dw_run_id"])

    def test_paused_deployment(self):
        spec=specification()
        self.assertTrue(spec["paused"])
        self.assertFalse(spec["active"])
        self.assertEqual(spec["cron"],"10 15 * * *")
        self.assertEqual(spec["timezone"],"America/Sao_Paulo")
        self.assertEqual(spec["concurrency_limit"],1)

    def test_retry_classification(self):
        self.assertTrue(tasks.transient(tasks.TransientFailure("temporary")))
        self.assertFalse(tasks.transient(ValueError("invalid")))
        self.assertFalse(tasks.transient(PermissionError("denied")))
        self.assertTrue(tasks.transient(duckdb.IOException("Could not set lock")))
        state=Mock()
        state.result.side_effect=tasks.TransientFailure()
        self.assertTrue(tasks.retry_transient(None,None,state))
        state.result.side_effect=tasks.PermanentFailure()
        self.assertFalse(tasks.retry_transient(None,None,state))

    def test_settings_attempts(self):
        for value in (0,4):
            with self.assertRaises(ValueError):Settings(attempts=value)

    def test_dry_run_no_files_or_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg=Settings(Path(folder)/"data",Path(folder)/"dw.duckdb")
            invoke=Mock()
            result=execute(cfg,plan(dry_run=True),identifiers(),invoke)
            self.assertEqual(result["status"],"PLAN_ONLY")
            invoke.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()),[])


class PipelineTests(WarehouseCase):
    def setUp(self):
        super().setUp()
        self.warehouse.run()
        self.cfg=Settings(self.silver,self.settings.database,retry_seconds=0)
        self.events=[]
        self.logger=patch("orchestration.tasks.pipeline.get_run_logger",return_value=Mock())
        self.logger.start();self.addCleanup(self.logger.stop)

    def invoke(self,task,*args):
        self.events.append(task.name)
        if task is tasks.check_source:return {"connected":True}
        if task is tasks.run_etl:return self.publication
        return task.fn(*args)

    def test_validations_reuse_existing_quality_readonly(self):
        before=self.settings.database.read_bytes()
        silver=tasks.validate_silver.fn(self.cfg,self.publication["version"],self.publication["run_id"])
        result=tasks.validate_gold.fn(self.cfg,silver)
        self.assertEqual(result["faturamento_total"],"48.70")
        self.assertEqual(result["pedidos_faturados"],3)
        self.assertEqual(before,self.settings.database.read_bytes())

    def test_validate_only_no_loads_or_audit(self):
        spec=plan(validate_only=True)
        result=execute(self.cfg,spec,identifiers(),self.invoke)
        self.assertEqual(self.events,["check_source","validate_silver","validate_gold"])
        self.assertEqual(result["status"],"VALIDATED")
        self.assertFalse((self.silver/"orchestration").exists())

    def test_dependency_order_full(self):
        result=execute(self.cfg,plan("full",allow_persistent=True,allow_full=True),identifiers(),self.invoke,"prefect-test")
        self.assertEqual(self.events,["check_source","run_etl","validate_silver","run_warehouse","validate_gold","finalize"])
        self.assertEqual(result["status"],"COMPLETED")
        self.assertEqual(result["prefect_run_id"],"prefect-test")
        self.assertTrue((self.silver/"orchestration/runs"/(result["run_id"]+".json")).is_file())

    def test_incremental_ids_and_reuse(self):
        ids=identifiers()
        result=execute(self.cfg,plan(allow_persistent=True),ids,self.invoke)
        self.assertEqual(result["results"]["warehouse"]["status"],"REUSED")
        self.assertEqual(result["results"]["warehouse"]["run_id"],ids["dw_run_id"])

    def test_invalid_silver_stops_warehouse_and_logs_failure(self):
        self.publication["version"]="unexpected-version"
        ids=identifiers()
        with self.assertRaises(tasks.PermanentFailure):
            execute(self.cfg,plan(allow_persistent=True),ids,self.invoke)
        self.assertNotIn("run_warehouse",self.events)
        report=json.loads((self.silver/"orchestration/runs"/(ids["run_id"]+".json")).read_text())
        self.assertEqual(report["status"],"FAILED")
        self.assertEqual(report["error_type"],"PermanentFailure")
        self.assertNotIn("password",json.dumps(report))

    def test_silver_change_blocks_warehouse(self):
        silver=tasks.validate_silver.fn(self.cfg)
        silver["fingerprint"]="changed"
        with self.assertRaises(tasks.PermanentFailure):
            tasks.run_warehouse.fn(self.cfg,"incremental",str(uuid4()),silver)

    def test_gold_requires_matching_version(self):
        silver=tasks.validate_silver.fn(self.cfg)
        silver["version"]="other"
        with self.assertRaises(tasks.PermanentFailure):tasks.validate_gold.fn(self.cfg,silver)

    def test_guard_excludes_second_run(self):
        with writer_lock(self.cfg.data_dir/"orchestration/guard"):
            with self.assertRaises(RuntimeError):
                execute(self.cfg,plan(allow_persistent=True),identifiers(),self.invoke)
        self.assertNotIn("run_etl",self.events)

    def test_sanitized_driver_errors(self):
        wrapped=tasks.safe_operation(Mock(side_effect=ValueError("secret-value")))
        wrapped.__wrapped__.__name__="check"
        with self.assertRaises(tasks.PermanentFailure) as failure:wrapped()
        self.assertNotIn("secret-value",str(failure.exception))


@unittest.skipUnless(os.getenv("PASTEL_TEST_PREFECT_RUNTIME")=="1","Runtime Prefect local opt-in")
class RuntimeTests(unittest.TestCase):
    def test_flow_and_retry_engine(self):
        from prefect.testing.utilities import prefect_test_harness
        from prefect import flow,task
        calls=[]
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{"PASTEL_DATA_DIR":folder+"/data","PASTEL_DW_PATH":folder+"/dw.duckdb"}):
            with prefect_test_harness():
                result=data_pipeline(dry_run=True)
                self.assertEqual(result["status"],"PLAN_ONLY")
                self.assertFalse(Path(folder,"data").exists())
                @task(retries=2,retry_delay_seconds=0,retry_condition_fn=tasks.retry_transient,persist_result=False)
                def flaky():
                    calls.append(1)
                    if len(calls)<3:raise tasks.TransientFailure("temporary")
                    return "ok"
                @flow(persist_result=False)
                def test_flow():return flaky()
                self.assertEqual(test_flow(),"ok")
                self.assertEqual(len(calls),3)
                failures=[]
                @task(retries=2,retry_delay_seconds=0,retry_condition_fn=tasks.retry_transient,persist_result=False)
                def permanent():
                    failures.append(1)
                    raise tasks.PermanentFailure("invalid")
                @flow(persist_result=False)
                def failure_flow():return permanent()
                with self.assertRaises(tasks.PermanentFailure):failure_flow()
                self.assertEqual(len(failures),1)
                # Exercita tasks reais Silver/DW/Gold com Prefect e arquivos temporários.
                from warehouse.tests.fixtures import fixture_rows,publish
                data_root=Path(folder)/"data"
                manifest=publish(data_root,fixture_rows(),1)
                @task(persist_result=False)
                def source_stub(cfg):return {"connected":True}
                @task(persist_result=False)
                def etl_stub(cfg,mode,run_id):return manifest
                with patch.object(tasks,"check_source",source_stub),patch.object(tasks,"run_etl",etl_stub):
                    result=data_pipeline(mode="full",allow_persistent=True,allow_full=True)
                self.assertEqual(result["status"],"COMPLETED")
                self.assertEqual(result["results"]["gold"]["faturamento_total"],"48.70")


if __name__=="__main__":unittest.main()
