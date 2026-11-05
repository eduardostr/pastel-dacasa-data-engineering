from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import text

from etl.config import Settings, default_engine
from etl.pipeline import Pipeline
from etl.load.files import dataset, read_table
from scripts.synthetic_data.isolation import isolated_database


class IsolatedCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="pastel_etl07_")
        self.addCleanup(self.temp.cleanup)
        self.environment = isolated_database(default_engine())
        self.engine, self.schema = self.environment.__enter__()
        self.addCleanup(lambda: self.environment.__exit__(None, None, None))
        self.settings = Settings(Path(self.temp.name) / "data", self.schema, batch_size=2, lookback_seconds=900)
        self.pipeline = Pipeline(self.engine, self.settings)
        with self.engine.begin() as c:
            for sql in (
                "INSERT INTO clientes(razao_social,cnpj,cidade,uf,ativo,created_at,updated_at) VALUES ('Cliente Exemplo','00000000000001','Salvador','BA',true,'2025-01-01Z','2025-01-01Z'),('Cliente Inativo','00000000000002','Recife','PE',false,'2025-01-01Z','2025-01-01Z')",
                "INSERT INTO vendedores(nome,email,created_at,updated_at) VALUES ('Equipe Exemplo','vendas@example.test','2025-01-01Z','2025-01-01Z')",
                "INSERT INTO produtos(nome,peso_gramas,preco,estoque_atual,ativo,created_at,updated_at) VALUES ('Massa 500g',500,100,8,true,'2025-01-01Z','2025-01-01Z'),('Massa Inativa',1000,5,0,false,'2025-01-01Z','2025-01-01Z')",
                "INSERT INTO pedidos(id_cliente,id_vendedor,status,data_pedido,created_at,updated_at) VALUES (1,1,'FATURADO','2025-01-01Z','2025-01-01Z','2025-01-01Z'),(1,1,'PENDENTE','2025-01-01Z','2025-01-01Z','2025-01-01Z'),(1,1,'CANCELADO','2025-01-01Z','2025-01-01Z','2025-01-01Z')",
                "INSERT INTO itens_pedido(id_pedido,id_produto,quantidade,preco_unitario,desconto,created_at,updated_at) VALUES (1,1,2,9.90,1,'2025-01-01Z','2025-01-01Z'),(2,1,1,9.90,0,'2025-01-01Z','2025-01-01Z'),(3,1,1,9.90,0,'2025-01-01Z','2025-01-01Z')",
                "INSERT INTO movimentacoes_estoque(id_produto,id_pedido,tipo,quantidade,data_movimentacao,created_at,updated_at) VALUES (1,NULL,'ENTRADA',10,'2025-01-01Z','2025-01-01Z','2025-01-01Z'),(1,1,'SAIDA',2,'2025-01-01Z','2025-01-01Z','2025-01-01Z')",
            ):
                c.execute(text(sql))

    def sql(self, sql, values=None):
        with self.engine.begin() as connection:
            connection.execute(text(sql), values or {})

    def rows(self, name):
        return dataset(self.settings.data_dir, name).to_pylist()

    def bronze_frames(self, manifest):
        from etl.config.schema import COLUMNS
        return {table: read_table(self.settings.data_dir / manifest["bronze"] / (table + ".parquet")).to_pandas(
            integer_object_nulls=True, timestamp_as_object=True) for table in COLUMNS}
