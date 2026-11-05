r"""Testes HTTP/ASGI com PostgreSQL real e rollback dos registros temporários.

Execute na raiz: .\.venv314\Scripts\python.exe -m unittest discover -s backend/tests -v
"""
import asyncio
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine, get_db
from app.main import app


async def requisicao(method, path, payload):
    """Exercita a aplicação ASGI completa sem dependências HTTP adicionais."""
    eventos = []
    corpo = json.dumps(payload).encode() if payload is not None else b""
    recebido = False

    async def receive():
        nonlocal recebido
        if not recebido:
            recebido = True
            return {"type": "http.request", "body": corpo, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(evento):
        eventos.append(evento)

    await app({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path,
        "raw_path": path.encode(), "query_string": b"", "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "server": ("test", 80), "client": ("test", 1234),
    }, receive, send)
    status = next(e["status"] for e in eventos if e["type"] == "http.response.start")
    body = b"".join(e.get("body", b"") for e in eventos if e["type"] == "http.response.body")
    return status, json.loads(body)


class CrudTests(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")

        def banco_teste():
            yield self.db

        app.dependency_overrides[get_db] = banco_teste
        self.produto = {"nome": "Teste " + uuid4().hex, "peso_gramas": 500,
                        "preco": 9.90, "estoque_atual": 10}
        self.cliente = {"razao_social": "Teste " + uuid4().hex,
                        "cnpj": str(uuid4().int % 10**14).zfill(14),
                        "cidade": "Salvador", "uf": " ba "}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def request(self, method, path, payload=None, status=200):
        codigo, body = asyncio.run(requisicao(method, path, payload))
        self.assertEqual(codigo, status, body)
        return body

    def test_produtos_crud_e_conflitos(self):
        produto = self.request("POST", "/produtos/", self.produto, 201)
        path = f"/produtos/{produto['id_produto']}"
        self.assertEqual(self.request("GET", path), produto)
        self.assertTrue(any(p["id_produto"] == produto["id_produto"]
                            for p in self.request("GET", "/produtos/")))
        self.request("POST", "/produtos/", self.produto, 409)
        novo = {**self.produto, "nome": self.produto["nome"] + " outro"}
        outro = self.request("POST", "/produtos/", novo, 201)
        self.request("PUT", f"/produtos/{outro['id_produto']}", self.produto, 409)
        atualizado = self.request("PUT", path, {**self.produto, "preco": 12.50})
        self.assertEqual(atualizado["preco"], 12.50)
        self.assertEqual(atualizado["created_at"], produto["created_at"])
        desativado = self.request("PATCH", path + "/desativar")
        self.assertFalse(desativado["ativo"])
        self.assertEqual(self.request("GET", path)["ativo"], False)

    def test_clientes_crud_e_conflitos(self):
        cliente = self.request("POST", "/clientes/", self.cliente, 201)
        self.assertEqual(cliente["uf"], "BA")
        path = f"/clientes/{cliente['id_cliente']}"
        self.assertEqual(self.request("GET", path), cliente)
        self.assertTrue(any(c["id_cliente"] == cliente["id_cliente"]
                            for c in self.request("GET", "/clientes/")))
        cnpj = self.cliente["cnpj"]
        formatado = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
        self.request("POST", "/clientes/", {**self.cliente, "cnpj": formatado}, 409)
        outro = self.request("POST", "/clientes/", {**self.cliente,
            "cnpj": str((int(cnpj) + 1) % 10**14).zfill(14)}, 201)
        self.request("PUT", f"/clientes/{outro['id_cliente']}", self.cliente, 409)
        atualizado = self.request("PUT", path, {**self.cliente, "cidade": "Recife", "uf": "pe"})
        self.assertEqual(atualizado["uf"], "PE")
        self.assertEqual(atualizado["created_at"], cliente["created_at"])

    def test_validacoes_produtos(self):
        for campo, valor in [("nome", " "), ("preco", 0), ("preco", -1),
                             ("preco", 1.001), ("peso_gramas", 0),
                             ("peso_gramas", 1.5), ("estoque_atual", -1),
                             ("created_at", "2020-01-01T00:00:00Z"),
                             ("updated_at", "2020-01-01T00:00:00Z")]:
            with self.subTest(campo=campo, valor=valor):
                self.request("POST", "/produtos/", {**self.produto, campo: valor}, 422)
                self.request("PUT", "/produtos/1", {**self.produto, campo: valor}, 422)
        self.request("POST", "/produtos/", {}, 422)

    def test_validacoes_clientes(self):
        for campo, valor in [("razao_social", " "), ("cidade", ""), ("uf", "XX"),
                             ("cnpj", "123"), ("email", "invalido"),
                             ("created_at", "2020-01-01T00:00:00Z"),
                             ("updated_at", "2020-01-01T00:00:00Z")]:
            with self.subTest(campo=campo):
                self.request("POST", "/clientes/", {**self.cliente, campo: valor}, 422)
                self.request("PUT", "/clientes/1", {**self.cliente, campo: valor}, 422)
        self.request("POST", "/clientes/", {}, 422)

    def test_inexistentes(self):
        for recurso, dados in [("produtos", self.produto), ("clientes", self.cliente)]:
            self.request("GET", f"/{recurso}/-1", status=404)
            self.request("PUT", f"/{recurso}/-1", dados, 404)
            self.request("GET", f"/{recurso}/abc", status=422)
        self.request("PATCH", "/produtos/-1/desativar", status=404)

    def test_datas_e_gatilhos(self):
        # NOW() é constante na transação externa dos testes. Somente os registros
        # temporários recebem datas antigas, permitindo comprovar cada gatilho.
        for tabela, chave, dados in [("produtos", "id_produto", self.produto),
                                      ("clientes", "id_cliente", self.cliente)]:
            item = self.request("POST", f"/{tabela}/", dados, 201)
            self.assertIsNotNone(item["created_at"])
            self.assertIsNotNone(item["updated_at"])
            self.assertIsNotNone(datetime.fromisoformat(item['created_at']).tzinfo)
            for method in (["PUT", "PATCH"] if tabela == "produtos" else ["PUT"]):
                # INSERT não aciona o gatilho de UPDATE: datas antigas tornam
                # visível a atualização mesmo dentro de uma única transação.
                entrada = dict(dados)
                if tabela == "produtos":
                    entrada["nome"] += uuid4().hex
                else:
                    entrada["cnpj"] = str(uuid4().int % 10**14).zfill(14)
                    entrada["uf"] = "BA"
                campos = ", ".join(entrada)
                valores = ", ".join(":" + campo for campo in entrada)
                identificador = self.db.execute(text(
                    f"INSERT INTO {tabela} ({campos}, created_at, updated_at) "
                    f"VALUES ({valores}, '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z') RETURNING {chave}"
                ), entrada).scalar_one()
                path = f"/{tabela}/{identificador}" + ("/desativar" if method == "PATCH" else "")
                atualizado = self.request(method, path, entrada if method == "PUT" else None)
                self.assertTrue(atualizado["created_at"].startswith("2000-01-01"))
                self.assertGreater(atualizado["updated_at"], atualizado["created_at"])

    def test_swagger(self):
        schema = self.request("GET", "/openapi.json")
        self.assertIn("post", schema["paths"]["/produtos/"])
        self.assertIn("put", schema["paths"]["/clientes/{id_cliente}"])


if __name__ == "__main__":
    unittest.main()
