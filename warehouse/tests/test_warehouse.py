from decimal import Decimal
from warehouse.tests.fixtures import WarehouseCase


class WarehouseTests(WarehouseCase):
    def test_full_dimensions_fact_and_finances(self):
        result=self.warehouse.run("full")
        self.assertEqual(result["status"],"COMPLETED")
        self.assertEqual(self.sql("SELECT count(*) FROM dim_cliente")[0][0],2)
        self.assertEqual(self.sql("SELECT count(*) FROM dim_produto")[0][0],2)
        self.assertEqual(self.sql("SELECT count(*) FROM dim_vendedor")[0][0],2)
        self.assertEqual(self.sql("SELECT count(*) FROM dim_tempo")[0][0],34)
        self.assertEqual(self.sql("SELECT count(*) FROM fato_vendas")[0][0],4)
        self.assertEqual(result["gold"]["faturamento_total"],"48.70")
        self.assertEqual(result["gold"]["pedidos_faturados"],3)
        self.assertEqual(result["gold"]["ticket_medio"],"16.23")
        self.assertEqual(self.sql("SELECT preco_unitario FROM fato_vendas WHERE id_item=1")[0][0],Decimal("9.90"))
        self.assertEqual(self.sql("SELECT preco_catalogo FROM dim_produto WHERE id_produto=100")[0][0],Decimal("100.00"))
        self.assertFalse(self.sql("SELECT ativo FROM dim_cliente WHERE id_cliente=20")[0][0])
        self.assertEqual(self.sql("SELECT count(*) FROM fato_vendas WHERE id_pedido IN (1003,1004)")[0][0],0)

    def test_gold_without_double_counting(self):
        self.warehouse.run("full")
        monthly=self.sql("SELECT ano_mes,faturamento FROM gold_faturamento_mensal ORDER BY ano_mes")
        self.assertEqual(monthly,[("2025-01",Decimal("23.80")),("2025-02",Decimal("24.90"))])
        self.assertEqual(self.sql("SELECT id_produto,unidades_vendidas FROM gold_produtos_mais_vendidos WHERE posicao=1")[0],(200,4))
        self.assertEqual(self.sql("SELECT id_cliente,pedidos_faturados FROM gold_clientes_recorrentes"),[(10,2)])
        self.assertEqual(self.sql("SELECT id_vendedor FROM gold_ranking_vendedores WHERE posicao=1"),[(30,)])
        self.assertEqual(self.sql("SELECT uf,faturamento FROM gold_faturamento_uf ORDER BY uf"),[("BA",Decimal("33.70")),("PE",Decimal("15.00"))])

    def test_incremental_dimensions_scd1_stable_keys(self):
        from datetime import timedelta
        from warehouse.tests.fixtures import BASE,publish
        self.warehouse.run("full")
        keys=self.sql("SELECT id_cliente,sk_cliente FROM dim_cliente ORDER BY id_cliente")
        self.rows["clientes"][0].update({"cidade":"Fortaleza","uf":"CE","updated_at":BASE+timedelta(days=40)})
        self.rows["produtos"][0].update({"nome":"Massa Nova","preco":Decimal("999.00"),"updated_at":BASE+timedelta(days=40)})
        publish(self.silver,self.rows,2)
        result=self.warehouse.run("incremental")
        self.assertEqual(result["metrics"]["dim_cliente"]["updated"],1)
        self.assertEqual(result["metrics"]["dim_produto"]["updated"],1)
        self.assertEqual(self.sql("SELECT id_cliente,sk_cliente FROM dim_cliente ORDER BY id_cliente"),keys)
        self.assertEqual(self.sql("SELECT uf FROM dim_cliente WHERE id_cliente=10"),[("CE",)])
        self.assertEqual(self.sql("SELECT faturamento FROM gold_faturamento_uf WHERE uf='CE'"),[(Decimal("33.70"),)])
        self.assertEqual(self.sql("SELECT preco_unitario FROM fato_vendas WHERE id_item=1"),[(Decimal("9.90"),)])
        self.assertEqual(result["gold"]["faturamento_total"],"48.70")

    def test_incremental_new_dimensions_and_fact(self):
        from datetime import datetime,timezone
        from warehouse.tests.fixtures import publish,BASE
        self.warehouse.run("full")
        old_product_keys=self.sql("SELECT id_produto,sk_produto FROM dim_produto ORDER BY id_produto")
        self.rows["clientes"].append({"id_cliente":25,"razao_social":"Novo","cnpj":"00000000000025","cidade":"São Paulo","uf":"SP","ativo":True,"created_at":BASE,"updated_at":BASE})
        self.rows["produtos"].append({"id_produto":150,"nome":"Mini massa","peso_gramas":250,"preco":Decimal("10.00"),"estoque_atual":30,"ativo":True,"created_at":BASE,"updated_at":BASE})
        self.rows["vendedores"].append({"id_vendedor":35,"nome":"Equipe nova","email":"novo@example.test","ativo":True,"created_at":BASE,"updated_at":BASE})
        date=datetime(2025,2,4,tzinfo=timezone.utc)
        self.rows["pedidos"].append({"id_pedido":1005,"id_cliente":25,"id_vendedor":35,"status":"FATURADO","data_pedido":date,"created_at":date,"updated_at":date})
        self.rows["itens_pedido"].append({"id_item":7,"id_pedido":1005,"id_produto":150,"quantidade":3,"preco_unitario":Decimal("4.90"),"desconto":Decimal("0.00"),"created_at":date,"updated_at":date})
        publish(self.silver,self.rows,2)
        result=self.warehouse.run("incremental")
        for dim in ("dim_cliente","dim_produto","dim_vendedor","dim_tempo"):
            self.assertEqual(result["metrics"][dim]["inserted"],1)
        self.assertEqual(result["metrics"]["fato_vendas"]["inserted"],1)
        self.assertEqual(self.sql("SELECT id_produto,sk_produto FROM dim_produto WHERE id_produto IN (100,200) ORDER BY id_produto"),old_product_keys)
        self.assertEqual(self.sql("SELECT sk_produto FROM dim_produto WHERE id_produto=150"),[(3,)])
        self.assertEqual(result["gold"]["faturamento_total"],"63.40")

    def test_status_reconciliation_removes_and_adds_facts(self):
        from warehouse.tests.fixtures import publish
        self.warehouse.run("full")
        self.rows["pedidos"][1]["status"]="CANCELADO"
        publish(self.silver,self.rows,2)
        result=self.warehouse.run("incremental")
        self.assertEqual(result["metrics"]["fato_vendas"]["removed"],1)
        self.assertEqual(result["gold"]["faturamento_total"],"38.80")
        self.assertEqual(self.sql("SELECT * FROM gold_clientes_recorrentes"),[])
        self.rows["pedidos"][3]["status"]="FATURADO"
        publish(self.silver,self.rows,3)
        result=self.warehouse.run("incremental")
        self.assertEqual(result["metrics"]["fato_vendas"]["inserted"],1)
        self.assertEqual(result["gold"]["faturamento_total"],"48.70")

    def test_financial_correction_from_silver_updates_item(self):
        from warehouse.tests.fixtures import publish
        self.warehouse.run("full")
        self.rows["itens_pedido"][0]["quantidade"]=3
        publish(self.silver,self.rows,2)
        result=self.warehouse.run("incremental")
        self.assertEqual(result["metrics"]["fato_vendas"]["updated"],1)
        self.assertEqual(result["gold"]["faturamento_total"],"58.60")
        self.assertEqual(self.sql("SELECT valor_liquido FROM fato_vendas WHERE id_item=1"),[(Decimal("28.70"),)])

    def test_reuse_same_silver_is_idempotent(self):
        self.warehouse.run("full")
        rows=self.sql("SELECT * FROM fato_vendas ORDER BY id_item")
        state=self.sql("SELECT * FROM dw_state")
        replay=self.warehouse.run("incremental")
        self.assertEqual(replay["status"],"REUSED")
        self.assertEqual(replay["metrics"],{})
        self.assertEqual(self.sql("SELECT * FROM fato_vendas ORDER BY id_item"),rows)
        self.assertEqual(self.sql("SELECT * FROM dw_state"),state)

    def test_new_silver_without_business_changes_writes_no_rows(self):
        from warehouse.tests.fixtures import publish
        self.warehouse.run("full")
        facts=self.sql("SELECT * FROM fato_vendas ORDER BY id_item")
        publish(self.silver,self.rows,2)
        result=self.warehouse.run("incremental")
        self.assertEqual(result["status"],"COMPLETED")
        for stats in result["metrics"].values():
            self.assertEqual(stats["inserted"],0)
            self.assertEqual(stats["updated"],0)
        self.assertEqual(self.sql("SELECT * FROM fato_vendas ORDER BY id_item"),facts)
        self.assertEqual(self.sql("SELECT silver_version FROM dw_state")[0][0],result["silver_version"])

    def test_failure_rolls_back_data_and_version(self):
        from warehouse.tests.fixtures import publish
        self.warehouse.run("full")
        facts=self.sql("SELECT * FROM fato_vendas ORDER BY id_item")
        dims=self.sql("SELECT * FROM dim_cliente ORDER BY sk_cliente")
        state=self.sql("SELECT * FROM dw_state")
        self.rows["clientes"][0]["uf"]="CE"
        self.rows["pedidos"][1]["status"]="CANCELADO"
        publish(self.silver,self.rows,2)
        def fail(stage):
            if stage=="after_fact":
                raise RuntimeError("Falha simulada antes do commit")
        with self.assertRaises(RuntimeError):
            self.warehouse.run("incremental",fault=fail)
        self.assertEqual(self.sql("SELECT * FROM fato_vendas ORDER BY id_item"),facts)
        self.assertEqual(self.sql("SELECT * FROM dim_cliente ORDER BY sk_cliente"),dims)
        self.assertEqual(self.sql("SELECT * FROM dw_state"),state)
        self.assertEqual(self.sql("SELECT status FROM dw_runs ORDER BY started_at DESC LIMIT 1"),[("FAILED",)])
        result=self.warehouse.run("incremental")
        self.assertEqual(result["gold"]["faturamento_total"],"38.80")

    def test_commit_before_audit_failure_is_recovered(self):
        from warehouse.tests.fixtures import publish
        self.warehouse.run("full")
        publish(self.silver,self.rows,2)
        def fail(stage):
            if stage=="after_commit":
                raise RuntimeError("Falha na auditoria pós-commit")
        with self.assertRaises(RuntimeError):
            self.warehouse.run("incremental",fault=fail)
        state=self.sql("SELECT silver_version FROM dw_state")[0][0]
        self.assertEqual(self.sql("SELECT status FROM dw_runs ORDER BY started_at DESC LIMIT 1"),[("PUBLISHED_AUDIT_PENDING",)])
        replay=self.warehouse.run("incremental")
        self.assertEqual(replay["status"],"REUSED")
        self.assertEqual(replay["silver_version"],state)
        self.assertEqual(self.sql("SELECT count(*) FROM dw_runs WHERE status='PUBLISHED_AUDIT_PENDING'"),[(0,)])

    def test_absent_dimension_mapping_is_retained_and_reused(self):
        from copy import deepcopy
        from warehouse.tests.fixtures import publish
        self.warehouse.run("full")
        original=deepcopy(self.rows)
        sk=self.sql("SELECT sk_cliente FROM dim_cliente WHERE id_cliente=20")[0][0]
        self.rows["clientes"]=[r for r in self.rows["clientes"] if r["id_cliente"]!=20]
        self.rows["pedidos"]=[r for r in self.rows["pedidos"] if r["id_cliente"]!=20]
        order_ids={r["id_pedido"] for r in self.rows["pedidos"]}
        self.rows["itens_pedido"]=[r for r in self.rows["itens_pedido"] if r["id_pedido"] in order_ids]
        publish(self.silver,self.rows,2)
        result=self.warehouse.run("incremental")
        self.assertEqual(result["metrics"]["dim_cliente"]["marked_absent"],1)
        self.assertEqual(self.sql("SELECT presente_na_silver FROM dim_cliente WHERE id_cliente=20"),[(False,)])
        self.rows=original
        publish(self.silver,self.rows,3)
        self.warehouse.run("incremental")
        self.assertEqual(self.sql("SELECT sk_cliente,presente_na_silver FROM dim_cliente WHERE id_cliente=20"),[(sk,True)])

    def test_empty_snapshot_has_zero_indicators(self):
        from warehouse.tests.fixtures import publish
        for name in self.rows:
            self.rows[name]=[]
        publish(self.silver,self.rows,2)
        result=self.warehouse.run("full")
        self.assertEqual(result["gold"]["faturamento_total"],"0.00")
        self.assertEqual(result["gold"]["pedidos_faturados"],0)
        self.assertEqual(result["gold"]["ticket_medio"],"0.00")
        self.assertEqual(self.sql("SELECT count(*) FROM dim_tempo"),[(0,)])

    def test_ticket_half_cent_is_exactly_rounded(self):
        from warehouse.tests.fixtures import publish
        self.rows["pedidos"]=self.rows["pedidos"][:2]
        self.rows["itens_pedido"]=[self.rows["itens_pedido"][0],self.rows["itens_pedido"][2]]
        for index,item in enumerate(self.rows["itens_pedido"]):
            item["quantidade"]=1;item["desconto"]=Decimal("0.00")
            item["preco_unitario"]=Decimal("0.01") if index==0 else Decimal("0.00")
        publish(self.silver,self.rows,2)
        result=self.warehouse.run("full")
        self.assertEqual(result["gold"]["faturamento_total"],"0.01")
        self.assertEqual(result["gold"]["ticket_medio"],"0.01")

    def test_utc_calendar_and_surrogate_relationships(self):
        self.warehouse.run("full")
        self.assertEqual(self.sql("SELECT dia_semana_nome,fim_de_semana FROM dim_tempo WHERE data=DATE '2025-02-02'"),[("Domingo",True)])
        self.assertEqual(self.sql("SELECT count(*) FROM fato_vendas f LEFT JOIN dim_cliente d USING(sk_cliente) WHERE d.sk_cliente IS NULL"),[(0,)])
        self.assertNotEqual(self.sql("SELECT sk_cliente,id_cliente FROM dim_cliente WHERE id_cliente=10")[0][0],10)
