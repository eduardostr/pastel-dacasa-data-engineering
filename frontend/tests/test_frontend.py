import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.api import ApiClient, ApiError
from frontend.domain import filtrar_clientes, filtrar_produtos, indicadores


PRODUTO = {"id_produto": 1, "nome": "Massa Tradicional", "peso_gramas": 500,
           "preco": 8.90, "estoque_atual": 20, "ativo": True}
CLIENTE = {"id_cliente": 1, "razao_social": "Pastelaria Exemplo", "cnpj": "00000000000001",
           "cidade": "Salvador", "uf": "BA", "ativo": True}
APP = str(Path(__file__).resolve().parents[1] / "app.py")


class DomainTests(unittest.TestCase):
    def test_dashboard(self):
        dados = indicadores([PRODUTO, {**PRODUTO, "ativo": False, "estoque_atual": 3}], [CLIENTE])
        self.assertEqual(dados, {"clientes": 1, "ativos": 1, "estoque": 23, "valor": Decimal("204.70")})
        self.assertEqual(indicadores([], [])["valor"], 0)

    def test_filtros(self):
        self.assertEqual(filtrar_produtos([PRODUTO], "TRADICIONAL", "Ativos"), [PRODUTO])
        self.assertEqual(filtrar_produtos([PRODUTO], "", "Inativos"), [])
        self.assertEqual(filtrar_clientes([CLIENTE], "00.000.000/0000-01", "BA"), [CLIENTE])
        self.assertEqual(filtrar_clientes([CLIENTE], "pastelaria", "PE"), [])


class ApiTests(unittest.TestCase):
    @patch("frontend.api.requests.request")
    def test_sucesso_configuracao_timeout(self, request):
        request.return_value = Mock(ok=True, status_code=201)
        request.return_value.json.return_value = PRODUTO
        with patch.dict("os.environ", {"API_BASE_URL": "http://api:9000/"}):
            self.assertEqual(ApiClient().request("POST", "/produtos/", PRODUTO), PRODUTO)
        self.assertEqual(request.call_args.args, ("POST", "http://api:9000/produtos/"))
        self.assertEqual(request.call_args.kwargs["timeout"], (3.05, 15))

    @patch("frontend.api.requests.request")
    def test_erros(self, request):
        for error in [requests.Timeout(), requests.ConnectionError()]:
            request.side_effect = error
            with self.assertRaises(ApiError):
                ApiClient().listar("produtos")
        request.side_effect = None
        for status, detail in [(404, "Não encontrado"), (409, "Duplicado"),
                                (422, [{"loc": ["body", "preco"], "msg": "Inválido"}])]:
            request.return_value = Mock(ok=False, status_code=status)
            request.return_value.json.return_value = {"detail": detail}
            with self.assertRaisesRegex(ApiError, str(status)):
                ApiClient().request("POST", "/produtos/", {})
        request.return_value.json.side_effect = ValueError()
        with self.assertRaisesRegex(ApiError, "resposta inválida"):
            ApiClient().listar("produtos")


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.produtos = [dict(PRODUTO)]
        self.clientes = [dict(CLIENTE)]
        self.calls = []
        self.patcher = patch("frontend.api.requests.request", side_effect=self.http)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def http(self, method, url, json=None, **kwargs):
        self.calls.append((method, url, json))
        recurso = self.produtos if "/produtos" in url else self.clientes
        if method == "GET":
            body = [dict(item) for item in recurso]
        elif method == "POST":
            body = {**json, "id_produto" if recurso is self.produtos else "id_cliente": 2}
            recurso.append(body)
        elif method == "PUT":
            recurso[0].update(json)
            body = recurso[0]
        else:
            recurso[0]["ativo"] = False
            body = recurso[0]
        response = Mock(ok=True, status_code=201 if method == "POST" else 200)
        response.json.return_value = body
        return response

    def app(self, page):
        app = AppTest.from_file(APP, default_timeout=15).run()
        if page != "Dashboard":
            app.radio[0].set_value(page).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def button(self, app, label):
        return next(b for b in app.button if b.label == label)

    def test_dashboard_e_navegacao(self):
        app = self.app("Dashboard")
        self.assertEqual([m.value for m in app.metric], ["1", "1", "20", "R$ 178,00"])
        app.radio[0].set_value("Clientes").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.dataframe), 1)

    def test_produto_cadastro_edicao_desativacao(self):
        app = self.app("Produtos")
        self.button(app, "Cadastrar produto").click().run()
        self.assertTrue(app.error)
        self.assertFalse(any(c[0] == "POST" for c in self.calls))
        next(x for x in app.text_input if x.label == "Nome do produto").set_value("Massa Nova")
        self.button(app, "Cadastrar produto").click().run()
        self.assertEqual(self.produtos[-1]["nome"], "Massa Nova")
        self.assertTrue(app.success)
        # O segundo formulário de produto é o de edição.
        nomes = [x for x in app.text_input if x.label == "Nome do produto"]
        nomes[1].set_value("Massa Editada")
        self.button(app, "Salvar alterações").click().run()
        self.assertEqual(self.produtos[0]["nome"], "Massa Editada")
        self.button(app, "Desativar produto").click().run()
        self.assertTrue(app.error)
        self.assertFalse(any(c[0] == "PATCH" for c in self.calls))
        next(c for c in app.checkbox if c.label == "Confirmo a desativação deste produto").check()
        self.button(app, "Desativar produto").click().run()
        self.assertFalse(self.produtos[0]["ativo"])
        self.assertEqual(len(app.exception), 0)

    def test_cliente_cadastro_edicao(self):
        app = self.app("Clientes")
        next(x for x in app.text_input if x.label == "Razão social").set_value("Novo Cliente")
        next(x for x in app.text_input if x.label == "CNPJ").set_value("00000000000090")
        next(x for x in app.text_input if x.label == "Cidade").set_value("Recife")
        self.button(app, "Cadastrar cliente").click().run()
        self.assertEqual(self.clientes[-1]["razao_social"], "Novo Cliente")
        cidades = [x for x in app.text_input if x.label == "Cidade"]
        cidades[1].set_value("Lauro de Freitas")
        self.button(app, "Salvar alterações").click().run()
        self.assertEqual(self.clientes[0]["cidade"], "Lauro de Freitas")
        self.assertEqual(len(app.exception), 0)

    def test_falha_conexao(self):
        with patch("frontend.api.requests.request", side_effect=requests.ConnectionError()):
            app = AppTest.from_file(APP, default_timeout=15).run()
        self.assertTrue(app.error)
        self.assertEqual(len(app.metric), 0)
        self.assertEqual(len(app.exception), 0)

    def test_listagens_vazias(self):
        self.produtos.clear()
        self.clientes.clear()
        for pagina in ["Dashboard", "Produtos", "Clientes"]:
            app = self.app(pagina)
            self.assertTrue(app.info)


if __name__ == "__main__":
    unittest.main()
