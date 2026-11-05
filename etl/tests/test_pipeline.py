from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import sqlite3
from contextlib import closing

from sqlalchemy import text

from etl.config.schema import COLUMNS
from etl.load.files import current_manifest, read_table
from etl.tests.support import IsolatedCase


class PipelineTests(IsolatedCase):
    def test_full_snapshot_and_types(self):
        with self.engine.connect() as c:
            before = c.execute(text("SELECT row_to_json(t)::text FROM produtos t ORDER BY id_produto")).scalars().all()
        manifest = self.pipeline.run("full")
        self.assertEqual(manifest["metrics"]["clientes"]["extracted"], 2)
        self.assertEqual(manifest["metrics"]["pedidos"]["valid"], 3)
        self.assertTrue(all(manifest["metrics"][t]["rejected"] == 0 for t in COLUMNS))
        bronze = read_table(self.settings.data_dir / manifest["bronze"] / "produtos.parquet")
        self.assertEqual(str(bronze.schema.field("preco").type), "decimal128(12, 2)")
        self.assertEqual(str(bronze.schema.field("created_at").type), "timestamp[us, tz=UTC]")
        self.assertEqual(bronze.to_pylist()[0]["preco"], Decimal("100.00"))
        self.assertIn("_source", bronze.column_names)
        self.assertFalse(self.rows("clientes")[1]["ativo"])
        self.assertIsNone(self.rows("movimentacoes_estoque")[0]["observacao"])
        self.assertEqual(self.rows("vendas_detalhadas")[0]["subtotal"], Decimal("18.80"))
        self.assertEqual(self.rows("vendas_detalhadas")[0]["preco_unitario"], Decimal("9.90"))
        self.assertEqual(manifest["metrics"]["vendas_detalhadas"]["financial_total"], "18.80")
        with self.engine.connect() as c:
            after = c.execute(text("SELECT row_to_json(t)::text FROM produtos t ORDER BY id_produto")).scalars().all()
        self.assertEqual(before, after)

    def test_incremental_update_and_related_sales(self):
        first = self.pipeline.run("full")
        self.sql("UPDATE clientes SET cidade='Fortaleza',uf='CE',ativo=false WHERE id_cliente=1")
        self.sql("UPDATE produtos SET nome='Massa Nova',preco=200 WHERE id_produto=1")
        second = self.pipeline.run("incremental")
        self.assertEqual(second["metrics"]["clientes"]["updated"], 1)
        self.assertEqual(second["metrics"]["produtos"]["updated"], 1)
        self.assertEqual(second["metrics"]["vendas_detalhadas"]["updated"], 1)
        sale = self.rows("vendas_detalhadas")[0]
        self.assertEqual(sale["cidade"], "Fortaleza")
        self.assertEqual(sale["produto"], "Massa Nova")
        self.assertEqual(sale["preco_unitario"], Decimal("9.90"))
        self.assertEqual(len(self.rows("clientes")), 2)
        self.assertFalse(self.rows("clientes")[0]["ativo"])
        self.assertNotEqual(first["version"], second["version"])

    def test_incremental_backdated_insert(self):
        self.pipeline.run("full")
        self.sql("INSERT INTO clientes(razao_social,cnpj,cidade,uf,created_at,updated_at) VALUES ('Novo Histórico','00000000000003','Salvador','BA','2024-01-01Z','2024-01-01Z')")
        result = self.pipeline.run("incremental")
        self.assertEqual(result["metrics"]["clientes"]["source_changed"], 1)
        self.assertEqual(result["metrics"]["clientes"]["inserted"], 1)
        self.assertEqual(len(self.rows("clientes")), 3)

    def test_reuse_same_run_is_idempotent(self):
        run_id = str(uuid4())
        first = self.pipeline.run("full", run_id)
        second = self.pipeline.run("full", run_id)
        self.assertEqual(first["version"], second["version"])
        self.assertEqual(len(list((self.settings.data_dir / "silver" / run_id).iterdir())), 1)
        self.assertEqual(len(self.rows("vendas_detalhadas")), 1)

    def test_failure_resume_preserves_watermark_and_bronze(self):
        first = self.pipeline.run("full")
        self.sql("UPDATE clientes SET cidade='Fortaleza' WHERE id_cliente=1")
        run_id = str(uuid4())
        def fail(stage):
            if stage == "after_build":
                raise RuntimeError("Falha simulada")
        with self.assertRaises(RuntimeError):
            self.pipeline.run("incremental", run_id, fault=fail)
        current = current_manifest(self.settings.data_dir)
        self.assertEqual(first["version"], current["version"])
        self.assertEqual(first["watermarks"], current["watermarks"])
        self.sql("UPDATE clientes SET cidade='Recife' WHERE id_cliente=1")
        resumed = self.pipeline.run("incremental", run_id)
        self.assertEqual(self.rows("clientes")[0]["cidade"], "Fortaleza")
        self.pipeline.run("incremental")
        self.assertEqual(self.rows("clientes")[0]["cidade"], "Recife")

    def test_equal_timestamp_is_included(self):
        from dataclasses import replace
        from etl.extract.postgres import extract
        from etl.pipeline import source_signature
        first = self.pipeline.run("full")
        first["watermarks"] = {t: "2025-01-01T00:00:00+00:00" for t in COLUMNS}
        settings = replace(self.settings, lookback_seconds=0)
        extracted = extract(self.engine, settings, str(uuid4()), "incremental", first, source_signature(self.engine, settings))
        self.assertEqual(extracted["stats"]["clientes"]["source_changed"], 0)
        self.assertEqual(extracted["stats"]["clientes"]["extracted"], 2)

    def test_late_commit_with_old_timestamp(self):
        connection = self.engine.connect()
        transaction = connection.begin()
        try:
            connection.execute(text("INSERT INTO clientes(razao_social,cnpj,cidade,uf,created_at,updated_at) VALUES ('Late','00000000000004','Salvador','BA','2024-01-01Z','2024-01-01Z')"))
            self.pipeline.run("full")
            self.assertEqual(len(self.rows("clientes")), 2)
            transaction.commit()
            result = self.pipeline.run("incremental")
            self.assertEqual(result["metrics"]["clientes"]["inserted"], 1)
            self.assertEqual(len(self.rows("clientes")), 3)
        finally:
            if transaction.is_active:
                transaction.rollback()
            connection.close()

    def test_consistent_snapshot_with_concurrent_commit(self):
        from sqlalchemy import event
        state = {"done": False}
        def after_query(conn, cursor, statement, parameters, context, executemany):
            if not state["done"] and 'FROM "' + self.schema + '"."clientes" ORDER BY' in statement:
                state["done"] = True
                with self.engine.begin() as writer:
                    id = writer.execute(text("INSERT INTO pedidos(id_cliente,id_vendedor,status,created_at,updated_at) VALUES (1,1,'PENDENTE','2024-01-01Z','2024-01-01Z') RETURNING id_pedido")).scalar_one()
                    writer.execute(text("INSERT INTO itens_pedido(id_pedido,id_produto,quantidade,preco_unitario) VALUES (:id,1,1,9.90)"), {"id": id})
        event.listen(self.engine, "after_cursor_execute", after_query)
        try:
            result = self.pipeline.run("full")
        finally:
            event.remove(self.engine, "after_cursor_execute", after_query)
        self.assertTrue(state["done"])
        self.assertEqual(result["metrics"]["pedidos"]["scanned"], 3)
        self.assertEqual(len(self.rows("pedidos")), 3)
        self.pipeline.run("incremental")
        self.assertEqual(len(self.rows("pedidos")), 4)

    def test_reprocess_current_uses_original_bronze(self):
        run_id = str(uuid4())
        first = self.pipeline.run("full", run_id)
        self.sql("UPDATE clientes SET cidade='Fortaleza' WHERE id_cliente=1")
        second = self.pipeline.run("full", run_id, reprocess=True)
        self.assertNotEqual(first["version"], second["version"])
        self.assertEqual(first["bronze"], second["bronze"])
        self.assertEqual(self.rows("clientes")[0]["cidade"], "Salvador")
        self.pipeline.run("incremental")
        self.assertEqual(self.rows("clientes")[0]["cidade"], "Fortaleza")
        with self.assertRaises(RuntimeError):
            self.pipeline.run("full", run_id, reprocess=True)

    def test_publication_recovery_after_pointer_commit(self):
        self.pipeline.run("full")
        self.sql("UPDATE clientes SET cidade='Fortaleza' WHERE id_cliente=1")
        run_id = str(uuid4())
        def fail(stage):
            if stage == "after_publish":
                raise RuntimeError("Falha após o commit lógico")
        with self.assertRaises(RuntimeError):
            self.pipeline.run("incremental", run_id, fault=fail)
        committed = current_manifest(self.settings.data_dir)
        self.assertEqual(committed["run_id"], run_id)
        self.assertEqual(self.rows("clientes")[0]["cidade"], "Fortaleza")
        recovered = self.pipeline.run("incremental", run_id)
        self.assertEqual(recovered["version"], committed["version"])
        with closing(sqlite3.connect(self.settings.data_dir / "control/audit.sqlite")) as c:
            self.assertEqual(c.execute("SELECT status FROM attempts WHERE attempt_id=?", (committed["attempt_id"],)).fetchone()[0], "COMPLETED")

    def test_tampered_bronze_never_advances_watermark(self):
        first = self.pipeline.run("full")
        run_id = str(uuid4())
        def fail(stage):
            if stage == "after_extract":
                raise RuntimeError("Falha de teste")
        with self.assertRaises(RuntimeError):
            self.pipeline.run("incremental", run_id, fault=fail)
        import json
        checkpoint = json.loads((self.settings.data_dir / "control/runs" / run_id / "extraction.json").read_text())
        bronze = self.settings.data_dir / checkpoint["bronze"] / "clientes.parquet"
        with bronze.open("ab") as stream:
            stream.write(b"corrompido")
        with self.assertRaises(RuntimeError):
            self.pipeline.run("incremental", run_id)
        self.assertEqual(current_manifest(self.settings.data_dir)["version"], first["version"])
        self.assertEqual(current_manifest(self.settings.data_dir)["watermarks"], first["watermarks"])

    def test_source_deletes_are_audited(self):
        self.pipeline.run("full")
        self.sql("DELETE FROM itens_pedido WHERE id_pedido=3")
        self.sql("DELETE FROM pedidos WHERE id_pedido=3")
        result = self.pipeline.run("incremental")
        self.assertEqual(result["metrics"]["pedidos"]["deleted_keys"], 1)
        self.assertEqual(result["metrics"]["pedidos"]["removed_from_valid"], 1)
        self.assertEqual(len(self.rows("pedidos")), 2)
        self.assertEqual(len(self.rows("vendas_detalhadas")), 1)

    def test_schema_drift_aborts(self):
        first = self.pipeline.run("full")
        self.sql("ALTER TABLE clientes ADD COLUMN nova_coluna TEXT")
        with self.assertRaises(RuntimeError):
            self.pipeline.run("incremental")
        self.assertEqual(current_manifest(self.settings.data_dir)["version"], first["version"])

    def test_status_change_propagates_to_sales(self):
        self.pipeline.run("full")
        self.assertEqual(len(self.rows("vendas_detalhadas")), 1)
        # Fatura somente o pedido de teste, em transação de fixture isolada.
        with self.engine.begin() as c:
            c.execute(text("UPDATE pedidos SET status='FATURADO' WHERE id_pedido=2"))
            c.execute(text("UPDATE produtos SET estoque_atual=estoque_atual-1 WHERE id_produto=1"))
            c.execute(text("INSERT INTO movimentacoes_estoque(id_produto,id_pedido,tipo,quantidade) VALUES (1,2,'SAIDA',1)"))
        result = self.pipeline.run("incremental")
        self.assertEqual(len(self.rows("vendas_detalhadas")), 2)
        self.assertEqual(result["metrics"]["vendas_detalhadas"]["inserted"], 1)
        self.assertEqual(result["metrics"]["vendas_detalhadas"]["financial_total"], "28.70")

    def test_old_failed_run_cannot_override_newer_publication(self):
        self.pipeline.run("full")
        run_id = str(uuid4())
        def fail(stage):
            if stage == "after_extract":
                raise RuntimeError("Falha simulada")
        with self.assertRaises(RuntimeError):
            self.pipeline.run("incremental", run_id, fault=fail)
        latest = self.pipeline.run("incremental")
        with self.assertRaises(RuntimeError):
            self.pipeline.run("incremental", run_id)
        self.assertEqual(current_manifest(self.settings.data_dir)["version"], latest["version"])

    def test_incremental_without_baseline_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.pipeline.run("incremental")
        self.assertIsNone(current_manifest(self.settings.data_dir))

    def test_quarantine_is_published_with_reason(self):
        self.sql("UPDATE clientes SET uf='XX' WHERE id_cliente=2")
        result = self.pipeline.run("full")
        self.assertEqual(result["metrics"]["clientes"]["valid"], 1)
        self.assertEqual(result["metrics"]["clientes"]["rejected"], 1)
        rejected = read_table(self.settings.data_dir / result["quarantine"] / "clientes.parquet").to_pylist()
        self.assertEqual(rejected[0]["uf"], "XX")
        self.assertIn("invalid_uf", rejected[0]["_rejection_reason"])
        original = read_table(self.settings.data_dir / result["bronze"] / "clientes.parquet").to_pylist()
        self.assertEqual(original[1]["uf"], "XX")
        # Corrigir a origem deve recuperar o registro antes rejeitado.
        self.sql("UPDATE clientes SET uf='PE' WHERE id_cliente=2")
        corrected = self.pipeline.run("incremental")
        self.assertEqual(corrected["metrics"]["clientes"]["rejected"], 0)
        self.assertEqual(len(self.rows("clientes")), 2)

    def test_extraction_failure_is_not_published(self):
        from unittest.mock import patch
        from etl.extract import postgres
        original = postgres.pq.ParquetWriter
        calls = {"count": 0}
        def fail(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("Falha durante extração")
            return original(*args, **kwargs)
        run_id = str(uuid4())
        with patch("etl.extract.postgres.pq.ParquetWriter", side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.pipeline.run("full", run_id)
        self.assertIsNone(current_manifest(self.settings.data_dir))
        self.assertFalse((self.settings.data_dir / "control/runs" / run_id / "extraction.json").exists())
        result = self.pipeline.run("full", run_id)
        self.assertEqual(result["metrics"]["pedidos"]["valid"], 3)

    def test_incremental_without_changes_does_not_duplicate(self):
        self.pipeline.run("full")
        result = self.pipeline.run("incremental")
        for table in COLUMNS:
            self.assertEqual(result["metrics"][table]["source_changed"], 0)
            self.assertEqual(result["metrics"][table]["inserted"], 0)
            self.assertEqual(result["metrics"][table]["updated"], 0)
        self.assertEqual(len(self.rows("vendas_detalhadas")), 1)
