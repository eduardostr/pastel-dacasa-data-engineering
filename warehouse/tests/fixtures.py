from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from etl.config.schema import SCHEMAS, SALES_SCHEMA
from etl.load.files import atomic_json, digest, inventory
from warehouse.config import Settings
from warehouse.loader import Warehouse

D = Decimal
BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def fixture_rows():
    customers = [
        {"id_cliente": 10, "razao_social": "Cliente A", "cnpj": "00000000000010", "cidade": "Salvador", "uf": "BA", "ativo": True},
        {"id_cliente": 20, "razao_social": "Cliente B", "cnpj": "00000000000020", "cidade": "Recife", "uf": "PE", "ativo": False},
    ]
    products = [
        {"id_produto": 100, "nome": "Massa 500g", "peso_gramas": 500, "preco": D("100.00"), "estoque_atual": 10, "ativo": True},
        {"id_produto": 200, "nome": "Disco 1kg", "peso_gramas": 1000, "preco": D("50.00"), "estoque_atual": 20, "ativo": False},
    ]
    sellers = [{"id_vendedor": 30, "nome": "Equipe A", "email": "a@example.test", "ativo": True},
               {"id_vendedor": 40, "nome": "Equipe B", "email": "b@example.test", "ativo": False}]
    orders = []
    for id, customer, seller, status, date in [
        (1000,10,30,"FATURADO",BASE), (1001,10,30,"FATURADO",datetime(2025,2,2,tzinfo=timezone.utc)),
        (1002,20,40,"FATURADO",datetime(2025,2,2,tzinfo=timezone.utc)),
        (1003,20,40,"PENDENTE",datetime(2025,2,3,tzinfo=timezone.utc)),
        (1004,10,30,"CANCELADO",datetime(2025,2,3,tzinfo=timezone.utc))]:
        orders.append({"id_pedido":id,"id_cliente":customer,"id_vendedor":seller,"status":status,
                       "data_pedido":date,"created_at":date,"updated_at":date})
    items=[]
    for id,order,product,q,price,discount in [(1,1000,100,2,"9.90","1.00"),(2,1000,200,1,"5.00","0.00"),
                    (3,1001,100,1,"9.90","0.00"),(4,1002,200,3,"5.00","0.00"),
                    (5,1003,100,1,"9.90","0.00"),(6,1004,200,1,"5.00","0.00")]:
        date=next(o["data_pedido"] for o in orders if o["id_pedido"]==order)
        items.append({"id_item":id,"id_pedido":order,"id_produto":product,"quantidade":q,
                      "preco_unitario":D(price),"desconto":D(discount),"created_at":date,"updated_at":date})
    for row in customers+products+sellers:
        row.update({"created_at":BASE,"updated_at":BASE})
    return {"clientes":customers,"produtos":products,"vendedores":sellers,"pedidos":orders,
            "itens_pedido":items,"movimentacoes_estoque":[]}


def derived(rows):
    orders={r["id_pedido"]:r for r in rows["pedidos"]}
    customers={r["id_cliente"]:r for r in rows["clientes"]}
    products={r["id_produto"]:r for r in rows["produtos"]}
    sellers={r["id_vendedor"]:r for r in rows["vendedores"]}
    sales=[];movements=[];totals={}
    for item in rows["itens_pedido"]:
        order=orders[item["id_pedido"]]
        if order["status"]!="FATURADO":
            continue
        c,p,v=customers[order["id_cliente"]],products[item["id_produto"]],sellers[order["id_vendedor"]]
        subtotal=item["quantidade"]*item["preco_unitario"]-item["desconto"]
        totals[order["id_pedido"]]=totals.get(order["id_pedido"],D("0.00"))+subtotal
        sales.append({"id_item":item["id_item"],"id_pedido":order["id_pedido"],"id_produto":p["id_produto"],
            "id_cliente":c["id_cliente"],"id_vendedor":v["id_vendedor"],"data_pedido":order["data_pedido"],"status":"FATURADO",
            "produto":p["nome"],"peso_gramas":p["peso_gramas"],"cliente":c["razao_social"],"cnpj":c["cnpj"],
            "cidade":c["cidade"],"uf":c["uf"],"vendedor":v["nome"],"email_vendedor":v["email"],
            "quantidade":item["quantidade"],"preco_unitario":item["preco_unitario"],"desconto":item["desconto"],
            "subtotal":subtotal,"source_updated_at":max(r["updated_at"] for r in (item,order,c,p,v))})
        movements.append({"id_movimentacao":len(movements)+1,"id_produto":p["id_produto"],"id_pedido":order["id_pedido"],
            "tipo":"SAIDA","quantidade":item["quantidade"],"observacao":"Fixture isolada",
            "data_movimentacao":order["data_pedido"],"created_at":order["created_at"],"updated_at":order["updated_at"]})
    for row in sales:
        row["total_pedido"]=totals[row["id_pedido"]]
    rows["movimentacoes_estoque"]=movements
    rows["vendas_detalhadas"]=sales


def publish(root, rows, ordinal, recalculate=True):
    if recalculate:
        derived(rows)
    version,run_id=str(uuid4()),str(uuid4())
    snapshot=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=ordinal)
    destination=root/"silver"/run_id/version
    destination.mkdir(parents=True)
    counts={}
    for table,schema in {**SCHEMAS,"vendas_detalhadas":SALES_SCHEMA}.items():
        records=[]
        for row in rows[table]:
            original={k:v for k,v in row.items() if not k.startswith("_")}
            records.append({**original,"_record_hash":digest(original),"_run_id":run_id,
                            "_extracted_at":snapshot,"_source":"fixture://isolated/"+table})
        data=pa.Table.from_pylist(records,schema=schema)
        pq.write_table(data,destination/(table+".parquet"),compression="zstd")
        counts[table]={"valid":len(records)}
    manifest={"version":version,"run_id":run_id,"published_at":snapshot.isoformat(),
              "snapshot_at":snapshot.isoformat(),"silver":str(destination.relative_to(root)),
              "files":inventory(root,[destination]),"source":{"origin":"fixture://isolated","quality_version":1},"metrics":counts}
    atomic_json(root/"control/current.json",manifest)
    return manifest


class WarehouseCase(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix="pastel_dw08_")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.silver=self.root/"data"
        self.rows=fixture_rows()
        self.publication=publish(self.silver,self.rows,1)
        self.settings=Settings(self.silver,self.root/"dw"/"isolated.duckdb")
        self.warehouse=Warehouse(self.settings)

    def sql(self,statement,params=None):
        c=duckdb.connect(str(self.settings.database),read_only=True)
        try:
            return c.execute(statement,params or []).fetchall()
        finally:
            c.close()
