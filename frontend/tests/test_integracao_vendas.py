"""Fluxo Streamlit → FastAPI → PostgreSQL real, com rollback integral."""
import asyncio
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from unittest.mock import Mock, patch

from sqlalchemy import text
from sqlalchemy.orm import Session
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from backend.tests import test_crud as crud
from app.database import engine, get_db
from app.main import app as api


class IntegracaoVendasTests(unittest.TestCase):
    def test_fluxo_completo_sem_persistir(self):
        with engine.connect() as connection:
            transacao = connection.begin()
            db = Session(bind=connection, join_transaction_mode="create_savepoint")

            def banco_teste():
                yield db

            def http(method, url, json=None, **kwargs):
                status, body = asyncio.run(crud.requisicao(method, urlsplit(url).path, json))
                response = Mock(ok=status < 400, status_code=status)
                response.json.return_value = body
                return response

            api.dependency_overrides[get_db] = banco_teste
            try:
                cliente = db.execute(text("""
                    INSERT INTO clientes (razao_social, cnpj, cidade, uf)
                    VALUES ('Integração UI', :cnpj, 'Salvador', 'BA') RETURNING id_cliente
                """), {"cnpj": str(uuid4().int % 10**14).zfill(14)}).scalar_one()
                produto = db.execute(text("""
                    INSERT INTO produtos (nome, peso_gramas, preco, estoque_atual)
                    VALUES (:nome, 500, 12.50, 10) RETURNING id_produto
                """), {"nome": "Integração " + uuid4().hex}).scalar_one()
                db.commit()
                email = uuid4().hex + "@example.test"
                with patch("frontend.api.requests.request", side_effect=http):
                    ui = AppTest.from_file(str(ROOT / "frontend/app.py"), default_timeout=20).run()
                    ui.radio[0].set_value("Vendedores").run()
                    next(t for t in ui.text_input if t.label == "Nome do vendedor").set_value("Vendedor Integração")
                    next(t for t in ui.text_input if t.label == "E-mail do vendedor").set_value(email)
                    next(b for b in ui.button if b.label == "Cadastrar vendedor").click().run()
                    self.assertFalse(ui.exception)
                    self.assertTrue(ui.success)
                    vendedor = db.execute(text("SELECT id_vendedor FROM vendedores WHERE email = :email"), {"email": email}).scalar_one()
                    ui.radio[0].set_value("Pedidos").run()
                    next(s for s in ui.selectbox if s.label == "Cliente do pedido").set_value(cliente)
                    next(s for s in ui.selectbox if s.label == "Vendedor responsável").set_value(vendedor)
                    ui.multiselect[0].set_value([produto]).run()
                    next(n for n in ui.number_input if n.key == f"pedido_qtd_{produto}").set_value(2).run()
                    next(b for b in ui.button if b.label == "Criar pedido").click().run()
                    self.assertFalse(ui.exception)
                    self.assertTrue(ui.success)
                    pedido = db.execute(text("SELECT id_pedido FROM pedidos WHERE id_vendedor = :id"), {"id": vendedor}).scalar_one()
                    next(s for s in ui.selectbox if s.label == "Consultar pedido").set_value(pedido).run()
                    next(c for c in ui.checkbox if c.label == "Confirmo o faturamento").check()
                    next(b for b in ui.button if b.label == "Faturar pedido").click().run()
                    self.assertFalse(ui.exception)
                    self.assertTrue(ui.success)
                    self.assertEqual(db.execute(text("SELECT estoque_atual FROM produtos WHERE id_produto = :id"), {"id": produto}).scalar_one(), 8)
                    self.assertEqual(db.execute(text("SELECT status FROM pedidos WHERE id_pedido = :id"), {"id": pedido}).scalar_one(), "FATURADO")
                    self.assertEqual(db.execute(text("SELECT quantidade FROM movimentacoes_estoque WHERE id_pedido = :id"), {"id": pedido}).scalar_one(), 2)
                    self.assertTrue(any("Movimentação" in tabela.value.columns for tabela in ui.dataframe))
            finally:
                api.dependency_overrides.clear()
                db.close()
                transacao.rollback()
