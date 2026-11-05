from contextlib import redirect_stderr,redirect_stdout
import io
import json
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
import unittest

from warehouse.__main__ import main
from warehouse.tests.fixtures import WarehouseCase,publish


class SourceSafetyTests(WarehouseCase):
    def test_incremental_requires_baseline(self):
        with self.assertRaises(RuntimeError):
            self.warehouse.run("incremental")
        self.assertEqual(self.sql("SELECT count(*) FROM dw_state"),[(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM fato_vendas"),[(0,)])

    def test_checksum_failure_does_not_advance_state(self):
        self.warehouse.run("full")
        before=self.sql("SELECT * FROM dw_state")
        manifest=publish(self.silver,self.rows,2)
        path=self.silver/manifest["silver"]/"clientes.parquet"
        with path.open("ab") as f:
            f.write(b"bad")
        with self.assertRaises(RuntimeError):
            self.warehouse.run("incremental")
        self.assertEqual(self.sql("SELECT * FROM dw_state"),before)

    def test_unpublished_staging_is_not_consumed(self):
        self.warehouse.run("full")
        (self.silver/".staging").mkdir()
        (self.silver/".staging"/"vendas_detalhadas.parquet").write_bytes(b"invalid")
        result=self.warehouse.run("incremental")
        self.assertEqual(result["status"],"REUSED")
        self.assertEqual(result["gold"]["faturamento_total"],"48.70")

    def test_duplicate_keys_rejected_with_rollback(self):
        from copy import deepcopy
        self.warehouse.run("full")
        state=self.sql("SELECT * FROM dw_state")
        self.rows["clientes"].append(deepcopy(self.rows["clientes"][0]))
        publish(self.silver,self.rows,2)
        with self.assertRaises(ValueError):
            self.warehouse.run("incremental")
        self.assertEqual(self.sql("SELECT * FROM dw_state"),state)

    def test_wrong_sales_price_rejected(self):
        from decimal import Decimal
        self.warehouse.run("full")
        self.rows["vendas_detalhadas"][0]["preco_unitario"]=Decimal("100.00")
        publish(self.silver,self.rows,2,recalculate=False)
        with self.assertRaises(ValueError):
            self.warehouse.run("incremental")
        self.assertEqual(self.sql("SELECT preco_unitario FROM fato_vendas WHERE id_item=1"),[(Decimal("9.90"),)])

    def test_missing_parent_rejected(self):
        self.rows["pedidos"][0]["id_cliente"]=999
        publish(self.silver,self.rows,2,recalculate=False)
        with self.assertRaises(ValueError):
            self.warehouse.run("full")
        self.assertEqual(self.sql("SELECT count(*) FROM fato_vendas"),[(0,)])

    def test_no_version_rollback_to_old_silver(self):
        self.warehouse.run("full")
        old=(self.silver/"control/current.json").read_text()
        publish(self.silver,self.rows,2)
        result=self.warehouse.run("incremental")
        (self.silver/"control/current.json").write_text(old)
        with self.assertRaises(RuntimeError):
            self.warehouse.run("incremental")
        self.assertEqual(self.sql("SELECT silver_version FROM dw_state"),[(result["silver_version"],)])

    def test_manifest_counts_must_match_parquet(self):
        pointer=self.silver/"control/current.json"
        manifest=json.loads(pointer.read_text())
        manifest["metrics"]["clientes"]["valid"]=999
        pointer.write_text(json.dumps(manifest))
        with self.assertRaises(RuntimeError):
            self.warehouse.run("full")

    def test_silver_files_cannot_change_during_load(self):
        self.warehouse.run("full")
        manifest=publish(self.silver,self.rows,2)
        path=self.silver/manifest["silver"]/"clientes.parquet"
        def corrupt(stage):
            if stage=="after_fact":
                with path.open("ab") as f:
                    f.write(b"bad")
        before=self.sql("SELECT * FROM dw_state")
        with self.assertRaises(RuntimeError):
            self.warehouse.run("incremental",fault=corrupt)
        self.assertEqual(self.sql("SELECT * FROM dw_state"),before)

    def test_billed_order_without_items_is_rejected(self):
        self.rows["itens_pedido"]=[r for r in self.rows["itens_pedido"] if r["id_pedido"]!=1001]
        publish(self.silver,self.rows,2)
        with self.assertRaisesRegex(ValueError,"pedido faturado sem itens"):
            self.warehouse.run("full")
        self.assertEqual(self.sql("SELECT count(*) FROM dw_state"),[(0,)])


class CliSafetyTests(unittest.TestCase):
    def test_cli_plan_and_permission_guard(self):
        with TemporaryDirectory() as directory:
            db=Path(directory)/"new"/"test.duckdb"
            args=["warehouse","--mode","full","--database",str(db)]
            with patch("sys.argv",args),redirect_stdout(io.StringIO()):
                self.assertEqual(main(),0)
            self.assertFalse(db.exists())
            with patch("sys.argv",args+["--execute"]),redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()
            self.assertFalse(db.exists())
