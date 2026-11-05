import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import test_crud as crud
from app.database import engine, get_db
from app.main import app
from app.routers.pedidos import executar
from app.schemas.pedidos import PedidoEntrada
from app.services import pedidos


class VendasTests(unittest.TestCase):
    # Cada teste usa a transação externa + savepoints, desfeita ao terminar.
    request = crud.CrudTests.request
    tearDown = crud.CrudTests.tearDown

    def setUp(self):
        crud.CrudTests.setUp(self)
        self.p = self.request("POST", "/produtos/", self.produto, 201)
        self.c = self.request("POST", "/clientes/", self.cliente, 201)
        self.v = self.request("POST", "/vendedores/", {
            "nome": "Vendedor Teste", "email": uuid4().hex + "@example.test"
        }, 201)
        self.dados = {"id_cliente": self.c["id_cliente"], "id_vendedor": self.v["id_vendedor"],
                      "itens": [{"id_produto": self.p["id_produto"], "quantidade": 2}]}

    def novo(self):
        return self.request("POST", "/pedidos/", self.dados, 201)

    def estoque(self):
        return self.request("GET", f"/produtos/{self.p['id_produto']}")["estoque_atual"]

    def test_cadastro_vendedor(self):
        self.assertTrue(any(v["id_vendedor"] == self.v["id_vendedor"]
                            for v in self.request("GET", "/vendedores/")))
        self.request("POST", "/vendedores/", {"nome": "Outro", "email": self.v["email"].upper()}, 409)
        self.request("POST", "/vendedores/", {"nome": " ", "email": "invalido"}, 422)

    def test_criacao_e_preco_historico(self):
        pedido = self.novo()
        self.assertEqual(pedido["status"], "PENDENTE")
        self.assertEqual(pedido["total"], 19.8)
        self.assertEqual(self.estoque(), 10)
        self.request("PUT", f"/produtos/{self.p['id_produto']}", {**self.produto, "preco": 15})
        atualizado = self.request("GET", f"/pedidos/{pedido['id_pedido']}")
        self.assertEqual(atualizado["total"], 19.8)
        faturado = self.request("PATCH", f"/pedidos/{pedido['id_pedido']}/faturar")
        self.assertEqual(faturado["total"], 19.8)
        self.assertTrue(any(p["id_pedido"] == pedido["id_pedido"]
                            for p in self.request("GET", "/pedidos/")))

    def test_produto_inexistente_rollback(self):
        antes = self.db.execute(text("SELECT count(*) FROM pedidos")).scalar_one()
        self.request("POST", "/pedidos/", {**self.dados, "itens": [
            self.dados["itens"][0], {"id_produto": 9223372036854775807, "quantidade": 1}]}, 404)
        self.assertEqual(self.db.execute(text("SELECT count(*) FROM pedidos")).scalar_one(), antes)
        self.assertEqual(self.estoque(), 10)

    def test_quantidades_ids_e_valores_invalidos(self):
        for quantidade in [0, -1, 1.5, True, 2147483648]:
            with self.subTest(quantidade=quantidade):
                self.request("POST", "/pedidos/", {**self.dados, "itens": [
                    {"id_produto": self.p["id_produto"], "quantidade": quantidade}]}, 422)
        for extra in [{"total": 0}, {"status": "FATURADO"}, {"created_at": "2000-01-01"}]:
            self.request("POST", "/pedidos/", {**self.dados, **extra}, 422)
        self.request("POST", "/pedidos/", {**self.dados, "itens": []}, 422)
        self.request("POST", "/pedidos/", {**self.dados, "itens": self.dados["itens"] * 2}, 422)
        self.request("POST", "/pedidos/", {**self.dados, "id_cliente": 0}, 422)
        self.request("GET", "/pedidos/0", status=422)
        self.request("GET", "/pedidos/9223372036854775807", status=404)

    def test_participantes_e_produtos_inativos(self):
        for tabela, chave, id in [("clientes", "id_cliente", self.c["id_cliente"]),
                                  ("vendedores", "id_vendedor", self.v["id_vendedor"]),
                                  ("produtos", "id_produto", self.p["id_produto"])]:
            with self.subTest(tabela=tabela):
                self.db.execute(text(f"UPDATE {tabela} SET ativo = FALSE WHERE {chave} = :id"), {"id": id})
                self.db.commit()
                self.request("POST", "/pedidos/", self.dados, 409)
                self.db.execute(text(f"UPDATE {tabela} SET ativo = TRUE WHERE {chave} = :id"), {"id": id})
                self.db.commit()
        for campo in ["id_cliente", "id_vendedor"]:
            self.request("POST", "/pedidos/", {**self.dados, campo: 9223372036854775807}, 404)

    def test_faturamento_revalida_situacao(self):
        for tabela, chave, id in [("clientes", "id_cliente", self.c["id_cliente"]),
                                  ("vendedores", "id_vendedor", self.v["id_vendedor"]),
                                  ("produtos", "id_produto", self.p["id_produto"])]:
            pedido = self.novo()
            path = f"/pedidos/{pedido['id_pedido']}"
            self.db.execute(text(f"UPDATE {tabela} SET ativo = FALSE WHERE {chave} = :id"), {"id": id})
            self.db.commit()
            self.request("PATCH", path + "/faturar", status=409)
            self.assertEqual(self.estoque(), 10)
            self.assertEqual(self.request("GET", path)["status"], "PENDENTE")
            self.db.execute(text(f"UPDATE {tabela} SET ativo = TRUE WHERE {chave} = :id"), {"id": id})
            self.db.commit()

    def test_faturamento_e_movimentacao(self):
        pedido = self.novo()
        path = f"/pedidos/{pedido['id_pedido']}"
        resultado = self.request("PATCH", path + "/faturar")
        self.assertEqual(resultado["status"], "FATURADO")
        self.assertEqual(self.estoque(), 8)
        movimentos = self.request("GET", path + "/movimentacoes")
        self.assertEqual(len(movimentos), 1)
        self.assertEqual(movimentos[0]["id_pedido"], pedido["id_pedido"])
        self.assertEqual(movimentos[0]["tipo"], "SAIDA")
        self.assertEqual(movimentos[0]["quantidade"], 2)
        self.assertEqual(resultado["created_at"], pedido["created_at"])

    def test_estoque_insuficiente_atomicidade(self):
        outro = self.request("POST", "/produtos/", {**self.produto,
            "nome": self.produto["nome"] + " insuficiente", "estoque_atual": 0}, 201)
        pedido = self.request("POST", "/pedidos/", {**self.dados, "itens": [
            self.dados["itens"][0], {"id_produto": outro["id_produto"], "quantidade": 1}]}, 201)
        path = f"/pedidos/{pedido['id_pedido']}"
        self.request("PATCH", path + "/faturar", status=409)
        self.assertEqual(self.estoque(), 10)
        self.assertEqual(self.request("GET", path)["status"], "PENDENTE")
        self.assertEqual(self.request("GET", path + "/movimentacoes"), [])

    def test_rollback_falha_apos_baixa(self):
        pedido = self.novo()
        path = f"/pedidos/{pedido['id_pedido']}"
        execute_original = self.db.execute

        def falha_movimentacao(sql, *args, **kwargs):
            if "INSERT INTO movimentacoes_estoque" in str(sql):
                raise RuntimeError("Falha simulada após UPDATE do estoque")
            return execute_original(sql, *args, **kwargs)

        with patch.object(self.db, "execute", side_effect=falha_movimentacao):
            with self.assertRaises(RuntimeError):
                self.request("PATCH", path + "/faturar")
        self.assertEqual(self.estoque(), 10)
        self.assertEqual(self.request("GET", path)["status"], "PENDENTE")
        self.assertEqual(self.request("GET", path + "/movimentacoes"), [])

    def test_faturamento_duplicado_e_cancelamento_faturado(self):
        pedido = self.novo()
        path = f"/pedidos/{pedido['id_pedido']}"
        self.request("PATCH", path + "/faturar")
        self.request("PATCH", path + "/faturar", status=409)
        self.request("PATCH", path + "/cancelar", status=409)
        self.request("POST", path + "/itens", self.dados["itens"][0], 409)
        self.assertEqual(self.estoque(), 8)
        self.assertEqual(len(self.request("GET", path + "/movimentacoes")), 1)

    def test_cancelamento_pendente(self):
        pedido = self.novo()
        path = f"/pedidos/{pedido['id_pedido']}"
        self.assertEqual(self.request("PATCH", path + "/cancelar")["status"], "CANCELADO")
        self.request("PATCH", path + "/faturar", status=409)
        self.request("PATCH", path + "/cancelar", status=409)
        self.request("POST", path + "/itens", self.dados["itens"][0], 409)
        self.assertEqual(self.estoque(), 10)

    def test_adicionar_itens(self):
        pedido = self.novo()
        path = f"/pedidos/{pedido['id_pedido']}"
        self.request("POST", path + "/itens", self.dados["itens"][0], 409)
        outro = self.request("POST", "/produtos/", {**self.produto, "nome": uuid4().hex}, 201)
        atualizado = self.request("POST", path + "/itens", {"id_produto": outro["id_produto"], "quantidade": 1}, 201)
        self.assertEqual(len(atualizado["itens"]), 2)
        self.assertEqual(atualizado["total"], 29.7)
        self.assertEqual(self.estoque(), 10)

    def test_auditoria_status(self):
        for acao in ["faturar", "cancelar"]:
            # INSERT permite fixar data anterior sem desativar os gatilhos.
            id = self.db.execute(text("""
                INSERT INTO pedidos (id_cliente, id_vendedor, created_at, updated_at)
                VALUES (:cliente, :vendedor, '2000-01-01Z', '2000-01-01Z') RETURNING id_pedido
            """), {"cliente": self.c["id_cliente"], "vendedor": self.v["id_vendedor"]}).scalar_one()
            self.db.execute(text("""
                INSERT INTO itens_pedido (id_pedido, id_produto, quantidade, preco_unitario)
                VALUES (:pedido, :produto, 1, 9.90)
            """), {"pedido": id, "produto": self.p["id_produto"]})
            self.db.commit()
            resultado = self.request("PATCH", f"/pedidos/{id}/{acao}")
            self.assertTrue(resultado["created_at"].startswith("2000-01-01"))
            self.assertGreater(resultado["updated_at"], resultado["created_at"])


class ConcorrenciaTests(unittest.TestCase):
    """Commit real em schema efêmero, sem gravar nas tabelas de desenvolvimento."""
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_vendas_" + uuid4().hex
        with engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.test_engine = create_engine(engine.url, connect_args={"options": f"-csearch_path={cls.schema}"})
        try:
            root = Path(__file__).resolve().parents[2]
            with cls.test_engine.begin() as c:
                with c.connection.cursor() as cursor:
                    cursor.execute((root / "database/oltp/001_schema.sql").read_text())
                    cursor.execute((root / "database/migrations/003_pedidos_vendas.sql").read_text())
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.test_engine.dispose()
        # O nome é exclusivamente um prefixo fixo + UUID gerado nesta classe.
        assert cls.schema.startswith("test_vendas_") and len(cls.schema) == 44
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))

    def setUp(self):
        with Session(self.test_engine) as db:
            cliente = db.execute(text("INSERT INTO clientes (razao_social, cnpj, cidade, uf) VALUES ('Teste', :cnpj, 'Salvador', 'BA') RETURNING id_cliente"), {"cnpj": str(uuid4().int % 10**14).zfill(14)}).scalar_one()
            vendedor = db.execute(text("INSERT INTO vendedores (nome, email) VALUES ('Teste', :email) RETURNING id_vendedor"), {"email": uuid4().hex + "@example.test"}).scalar_one()
            self.produto = db.execute(text("INSERT INTO produtos (nome, peso_gramas, preco, estoque_atual) VALUES (:nome, 500, 10, 5) RETURNING id_produto"), {"nome": uuid4().hex}).scalar_one()
            dados = PedidoEntrada(id_cliente=cliente, id_vendedor=vendedor,
                                  itens=[{"id_produto": self.produto, "quantidade": 3}])
            self.ids = [pedidos.criar(db, dados)["id_pedido"] for _ in range(2)]
            db.commit()

    def corrida(self, tarefas):
        barreira = Barrier(2)

        def worker(tarefa):
            operacao, id = tarefa
            with Session(self.test_engine) as db:
                barreira.wait(timeout=10)
                try:
                    executar(db, operacao, id)
                    return 200
                except HTTPException as erro:
                    return erro.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker, tarefa) for tarefa in tarefas]
            resultados = [f.result(timeout=20) for f in futures]
        self.assertEqual(sorted(resultados), [200, 409])

    def test_mesmo_pedido_duas_vezes(self):
        self.corrida([(pedidos.faturar, self.ids[0])] * 2)
        self.validar_baixa_unica()

    def test_dois_pedidos_mesmo_estoque(self):
        self.corrida([(pedidos.faturar, id) for id in self.ids])
        self.validar_baixa_unica()

    def test_faturar_contra_cancelar(self):
        self.corrida([(pedidos.faturar, self.ids[0]), (pedidos.cancelar, self.ids[0])])
        with self.test_engine.connect() as c:
            status = c.execute(text("SELECT status FROM pedidos WHERE id_pedido = :id"), {"id": self.ids[0]}).scalar_one()
            estoque = c.execute(text("SELECT estoque_atual FROM produtos WHERE id_produto = :id"), {"id": self.produto}).scalar_one()
            self.assertEqual(estoque, 2 if status == "FATURADO" else 5)

    def validar_baixa_unica(self):
        with self.test_engine.connect() as c:
            estoque = c.execute(text("SELECT estoque_atual FROM produtos WHERE id_produto = :id"), {"id": self.produto}).scalar_one()
            movimentos = c.execute(text("SELECT count(*) FROM movimentacoes_estoque WHERE id_produto = :id"), {"id": self.produto}).scalar_one()
            self.assertEqual(estoque, 2)
            self.assertEqual(movimentos, 1)
