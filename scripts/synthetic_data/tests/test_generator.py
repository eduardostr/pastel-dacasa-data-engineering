import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import unittest

from sqlalchemy import text
from sqlalchemy.orm import Session

from scripts.synthetic_data.config import Config
from scripts.synthetic_data.generation import plan
from scripts.synthetic_data.isolation import isolated_database
from scripts.synthetic_data.persistence import context
from scripts.synthetic_data.runner import generate
from scripts.synthetic_data.validation import validate
from app.database import engine
from app.schemas.pedidos import PedidoEntrada
from app.services import pedidos

logging.getLogger("synthetic").addHandler(logging.NullHandler())


class PlanTests(unittest.TestCase):
    def test_reproducibility_and_seasonality(self):
        config = Config(start="2025-01-01", end="2026-01-01", pedidos=2400)
        a, b = list(plan(config)), list(plan(config))
        self.assertEqual(a, b)
        self.assertEqual(sum(o.status=="FATURADO" for o in a), 1800)
        monthly = {m: sum(o.created.month==m for o in a) for m in range(1,13)}
        self.assertEqual(len([n for n in monthly.values() if n]), 12)
        self.assertGreater(monthly[12], monthly[6])
        self.assertTrue(all(o.finished>=o.created for o in a))
        self.assertEqual(config.run_id(), replace(config,batch_size=17).run_id())

    def test_bad_config(self):
        for values in ({"clientes":0}, {"batch_size":0}, {"pedidos":-1},
                       {"start":"2026-02-01","end":"2025-01-01"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Config(**values)


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = isolated_database(engine)
        cls.target, cls.schema = cls.environment.__enter__()
        cls.config = Config(clientes=20,vendedores=3,produtos=8,pedidos=40,
                            start="2025-01-01",end="2026-01-01",batch_size=7,seed=93)
        # Cadastros externos à execução: preservação de campos e timestamps.
        with cls.target.begin() as c:
            c.execute(text("INSERT INTO clientes(razao_social,cnpj,cidade,uf) VALUES ('Registro externo','00000000000001','Salvador','BA')"))
            c.execute(text("INSERT INTO vendedores(nome,email) VALUES ('Registro externo','externo@example.test')"))
            c.execute(text("INSERT INTO produtos(nome,peso_gramas,preco,estoque_atual) VALUES ('Registro externo',500,9.90,22)"))
            cls.before = cls.snapshot(c)
        cls.result = generate(cls.target, cls.config)

    @classmethod
    def tearDownClass(cls):
        cls.environment.__exit__(None,None,None)

    @staticmethod
    def snapshot(c):
        return {table: c.execute(text(f"SELECT row_to_json(t)::text FROM {table} t WHERE {pk}=1")).scalar_one()
                for table,pk in (("clientes","id_cliente"),("vendedores","id_vendedor"),("produtos","id_produto"))}

    def test_status_totals_and_stock(self):
        with Session(self.target) as db:
            report = validate(db,self.config,self.result["run_id"])
            self.assertEqual(report["status_counts"],{"FATURADO":30,"PENDENTE":6,"CANCELADO":4})
            self.assertEqual(report["orders"],40)
            for id in db.execute(text("SELECT record_id FROM synthetic_objects WHERE run_id=:run AND kind='pedidos'"), {"run":self.result["run_id"]}).scalars():
                detail = pedidos.obter(db,id)
                expected = sum(i["quantidade"]*i["preco_unitario"]-i["desconto"] for i in detail["itens"])
                self.assertEqual(expected,detail["total"])

    def test_foreign_keys_and_uniqueness(self):
        with self.target.connect() as c:
            self.assertEqual(c.execute(text("SELECT count(*) FROM itens_pedido i LEFT JOIN pedidos p USING(id_pedido) LEFT JOIN produtos pr USING(id_produto) WHERE p.id_pedido IS NULL OR pr.id_produto IS NULL")).scalar_one(),0)
            self.assertEqual(c.execute(text("SELECT count(*) FROM (SELECT cnpj FROM clientes GROUP BY cnpj HAVING count(*)>1) d")).scalar_one(),0)
            self.assertEqual(c.execute(text("SELECT count(*) FROM (SELECT id_pedido,id_produto FROM itens_pedido GROUP BY id_pedido,id_produto HAVING count(*)>1) d")).scalar_one(),0)

    def test_existing_rows_and_trigger_preserved(self):
        with self.target.connect() as c:
            self.assertEqual(self.before,self.snapshot(c))
            self.assertEqual(c.execute(text("SELECT count(*) FROM pg_trigger WHERE tgname='trg_updated_at' AND tgrelid IN (SELECT oid FROM pg_class WHERE relnamespace=to_regnamespace(:schema))"), {"schema":self.schema}).scalar_one(),6)
        # A API normal não tem relógio de demonstração.
        with Session(self.target) as db:
            db.execute(text("UPDATE produtos SET preco=10 WHERE id_produto=1"))
            date = db.execute(text("SELECT updated_at FROM produtos WHERE id_produto=1")).scalar_one()
            self.assertGreater(date,datetime(2026,1,1,tzinfo=timezone.utc))
            db.rollback()

    def test_idempotent_replay(self):
        result = generate(self.target,replace(self.config,batch_size=3))
        self.assertEqual(result["created"],{})
        self.assertEqual(result["counts"],self.result["counts"])
        self.assertGreater(result["ignored"],0)

    def test_reject_reused_run_id(self):
        with self.assertRaises(ValueError):
            generate(self.target,replace(self.config,seed=94),self.result["run_id"])

    def test_context_cannot_modify_external_record(self):
        with Session(self.target) as db:
            db.execute(text("UPDATE synthetic_runs SET status='RUNNING' WHERE run_id=:run"), {"run":self.result["run_id"]})
            context(db,self.result["run_id"],datetime(2025,2,1,tzinfo=timezone.utc))
            with self.assertRaises(Exception):
                db.execute(text("UPDATE produtos SET preco=99 WHERE id_produto=1"))
            db.rollback()
        with self.target.connect() as c:
            self.assertEqual(self.before,self.snapshot(c))

    def test_failure_resume_without_duplicate_stock(self):
        config = replace(self.config,seed=100,batch_size=5,pedidos=20)
        original = pedidos.criar
        calls = 0

        def interrupt(db,data):
            nonlocal calls
            calls += 1
            if calls == 8:
                raise RuntimeError("Falha de teste após um lote confirmado")
            return original(db,data)

        with patch("scripts.synthetic_data.runner.pedidos.criar",side_effect=interrupt):
            with self.assertRaises(RuntimeError):
                generate(self.target,config)
        with self.target.connect() as c:
            self.assertEqual(c.execute(text("SELECT progress FROM synthetic_runs WHERE run_id=:run"),{"run":config.run_id()}).scalar_one(),5)
        resumed = generate(self.target,config)
        self.assertEqual(resumed["orders"],20)
        self.assertTrue(resumed["valid"])
        self.assertEqual(generate(self.target,config)["created"],{})
