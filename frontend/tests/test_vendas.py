import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).resolve().parents[1] / "app.py")


class VendasInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.dados = {
            "produtos": [{"id_produto": 1, "nome": "Massa Teste", "preco": 10.0,
                          "peso_gramas": 500, "estoque_atual": 10, "ativo": True}],
            "clientes": [{"id_cliente": 1, "razao_social": "Cliente Teste", "cnpj": "00000000000001",
                          "cidade": "Salvador", "uf": "BA", "ativo": True}],
            "vendedores": [{"id_vendedor": 1, "nome": "Vendedor Teste", "email": "teste@example.test", "ativo": True}],
            "pedidos": [],
        }
        self.movimentos = []
        patcher = patch("frontend.api.requests.request", side_effect=self.http)
        patcher.start()
        self.addCleanup(patcher.stop)

    def http(self, method, url, json=None, **kwargs):
        self.calls.append((method, url, json))
        path = url.split(":8000")[-1].strip("/").split("/")
        recurso = path[0]
        if method == "GET":
            body = self.movimentos if path[-1] == "movimentacoes" else (
                self.dados[recurso][0] if len(path) > 1 else self.dados[recurso])
        elif recurso == "vendedores":
            body = {**json, "id_vendedor": 2}
            self.dados[recurso].append(body)
        elif method == "POST":
            body = {"id_pedido": 1, "id_cliente": 1, "cliente": "Cliente Teste",
                    "id_vendedor": 1, "vendedor": "Vendedor Teste", "status": "PENDENTE",
                    "created_at": "2026-11-04T12:00:00Z", "updated_at": "2026-11-04T12:00:00Z",
                    "data_pedido": "2026-11-04T12:00:00Z", "total": 20.0,
                    "itens": [{"id_produto": 1, "nome": "Massa Teste", "quantidade": 2,
                               "preco_unitario": 10.0, "desconto": 0, "subtotal": 20.0}]}
            self.dados[recurso].append(body)
        else:
            body = self.dados["pedidos"][0]
            body["status"] = "FATURADO" if path[-1] == "faturar" else "CANCELADO"
            if path[-1] == "faturar":
                self.dados["produtos"][0]["estoque_atual"] -= 2
                self.movimentos.append({"id_movimentacao": 1, "id_pedido": 1, "id_produto": 1,
                    "tipo": "SAIDA", "quantidade": 2, "data_movimentacao": "2026-11-04T12:01:00Z",
                    "observacao": "Faturamento do pedido #1"})
        response = Mock(ok=True, status_code=201 if method == "POST" else 200)
        response.json.return_value = deepcopy(body)
        return response

    def app(self, page):
        app = AppTest.from_file(APP, default_timeout=15).run()
        app.radio[0].set_value(page).run()
        self.assertFalse(app.exception)
        return app

    def button(self, app, label):
        return next(b for b in app.button if b.label == label)

    def pedido(self):
        app = self.app("Pedidos")
        self.button(app, "Criar pedido").click().run()
        self.assertTrue(app.error)
        app.multiselect[0].set_value([1]).run()
        next(n for n in app.number_input if n.label.startswith("Quantidade ·")).set_value(2).run()
        self.assertTrue(any(m.value == "R$ 20,00" for m in app.metric))
        self.button(app, "Criar pedido").click().run()
        self.assertEqual(self.dados["pedidos"][0]["status"], "PENDENTE")
        payload = next(c[2] for c in self.calls if c[0] == "POST" and "/pedidos/" in c[1])
        self.assertNotIn("total", payload)
        self.assertNotIn("preco_unitario", payload["itens"][0])
        return app

    def test_vendedor(self):
        app = self.app("Vendedores")
        self.button(app, "Cadastrar vendedor").click().run()
        self.assertTrue(app.error)
        app.text_input[0].set_value("Novo Vendedor")
        app.text_input[1].set_value("novo@example.test")
        self.button(app, "Cadastrar vendedor").click().run()
        self.assertTrue(app.success)
        self.assertEqual(self.dados["vendedores"][-1]["nome"], "Novo Vendedor")
        self.assertFalse(app.exception)

    def test_pedido_faturamento_movimentacao(self):
        app = self.pedido()
        self.button(app, "Faturar pedido").click().run()
        self.assertTrue(app.error)
        self.assertFalse(any(c[0] == "PATCH" for c in self.calls))
        next(c for c in app.checkbox if c.label == "Confirmo o faturamento").check()
        self.button(app, "Faturar pedido").click().run()
        self.assertEqual(self.dados["pedidos"][0]["status"], "FATURADO")
        self.assertEqual(self.dados["produtos"][0]["estoque_atual"], 8)
        self.assertFalse(any(b.label == "Faturar pedido" for b in app.button))
        self.assertTrue(any("Movimentação" in df.value.columns for df in app.dataframe))
        self.assertFalse(app.exception)

    def test_pedido_cancelamento(self):
        app = self.pedido()
        self.button(app, "Cancelar pedido").click().run()
        self.assertTrue(app.error)
        next(c for c in app.checkbox if c.label == "Confirmo o cancelamento").check()
        self.button(app, "Cancelar pedido").click().run()
        self.assertEqual(self.dados["pedidos"][0]["status"], "CANCELADO")
        self.assertEqual(self.dados["produtos"][0]["estoque_atual"], 10)
        self.assertFalse(app.exception)
