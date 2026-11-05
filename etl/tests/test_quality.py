from decimal import Decimal
import pandas as pd

from etl.load.files import digest
from etl.quality import clean_snapshot
from etl.transform.snapshot import sales_snapshot
from etl.tests.support import IsolatedCase


class QualityTests(IsolatedCase):
    def frames(self):
        manifest = self.pipeline.run("full")
        return self.bronze_frames(manifest), manifest

    def test_exact_and_ambiguous_primary_key_duplicates(self):
        frames, manifest = self.frames()
        duplicate = frames["clientes"].iloc[0].copy()
        frames["clientes"] = pd.concat([frames["clientes"], pd.DataFrame([duplicate])], ignore_index=True)
        valid, rejected = clean_snapshot(frames)
        self.assertEqual(len(valid["clientes"]), 2)
        self.assertEqual(rejected["clientes"][0]["_rejection_reason"], "exact_duplicate")
        duplicate["razao_social"] = "Conflito"
        duplicate["_record_hash"] = digest({"nome": "Conflito"})
        frames["clientes"].iloc[-1] = duplicate
        valid, rejected = clean_snapshot(frames)
        self.assertEqual(len(valid["clientes"]), 1)
        self.assertTrue(any(r["_rejection_reason"] == "ambiguous_duplicate" for r in rejected["clientes"]))
        self.assertFalse(valid["pedidos"])

    def test_quarantine_missing_foreign_key(self):
        frames, manifest = self.frames()
        frames["pedidos"].loc[0, "id_cliente"] = 999
        valid, rejected = clean_snapshot(frames)
        self.assertEqual(len(valid["pedidos"]), 2)
        self.assertTrue(any("missing_parent:id_cliente" in r["_rejection_reason"] for r in rejected["pedidos"]))
        sales = sales_snapshot(valid, manifest["run_id"], pd.Timestamp(manifest["snapshot_at"]).to_pydatetime(), "test")
        self.assertEqual(sales.num_rows, 0)

    def test_bad_item_never_produces_partial_sale(self):
        frames, manifest = self.frames()
        extra = frames["itens_pedido"].iloc[0].copy()
        extra["id_item"] = 99
        extra["id_produto"] = 2
        extra["quantidade"] = -1
        extra["_record_hash"] = digest({"bad": 1})
        frames["itens_pedido"] = pd.concat([frames["itens_pedido"], pd.DataFrame([extra])], ignore_index=True)
        valid, rejected = clean_snapshot(frames)
        self.assertTrue(any("invalid_positive_integer" in r["_rejection_reason"] for r in rejected["itens_pedido"]))
        self.assertFalse(any(p["id_pedido"] == 1 for p in valid["pedidos"]))
        self.assertTrue(rejected["pedidos"])

    def test_status_normalization_and_original_bronze(self):
        frames, manifest = self.frames()
        frames["pedidos"].loc[1, "status"] = " aberto "
        frames["clientes"].loc[0, "uf"] = " ba "
        valid, rejected = clean_snapshot(frames)
        self.assertEqual(valid["pedidos"][1]["status"], "PENDENTE")
        self.assertEqual(valid["clientes"][0]["uf"], "BA")
        self.assertEqual(frames["pedidos"].loc[1, "status"], " aberto ")
        self.assertFalse(any(rejected.values()))

    def test_nulls_and_financial_rejections(self):
        frames, manifest = self.frames()
        frames["produtos"].loc[0, "preco"] = Decimal("-1.00")
        frames["clientes"].loc[0, "cidade"] = None
        valid, rejected = clean_snapshot(frames)
        self.assertTrue(any("invalid_money:preco" in r["_rejection_reason"] for r in rejected["produtos"]))
        self.assertTrue(any("required:cidade" in r["_rejection_reason"] for r in rejected["clientes"]))
        self.assertTrue(rejected["pedidos"])
