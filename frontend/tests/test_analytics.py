from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import hashlib
import unittest

import duckdb
from streamlit.testing.v1 import AppTest

from frontend.analytics import reader
from frontend.domain import moeda
from warehouse.tests.fixtures import WarehouseCase, publish


def analytics_app():
    from frontend.analytics.ui import render
    render()


class AnalyticsTests(WarehouseCase):
    def setUp(self):
        super().setUp()
        self.warehouse.run()
        self.path = str(self.settings.database)
        self.version = reader.publication(self.path)
        self.filters = reader.Filters(date(2025,1,1),date(2025,2,28))

    def summary(self, **kwargs):
        return reader.summary(self.path,self.version,reader.Filters(
            kwargs.pop("start",self.filters.start),kwargs.pop("end",self.filters.end),**kwargs))

    def test_kpis_historical_prices_distinct_orders(self):
        result=self.summary()["kpi"]
        self.assertEqual(result["faturamento_total"],Decimal("48.70"))
        self.assertEqual(result["pedidos_faturados"],3)
        self.assertEqual(result["ticket_medio"],Decimal("16.23"))
        self.assertEqual(result["itens_faturados"],4)
        self.assertEqual(result["unidades_vendidas"],7)
        existing=self.sql("SELECT faturamento_total,pedidos_faturados,itens_faturados,unidades_vendidas,ticket_medio FROM gold_kpis")[0]
        self.assertEqual(tuple(result[k] for k in ["faturamento_total","pedidos_faturados","itens_faturados","unidades_vendidas","ticket_medio"]),existing)

    def test_every_filter_and_combined(self):
        for kwargs,expected,orders in [
            ({"seller":30},"33.70",2),({"product":100},"28.70",2),({"uf":"PE"},"15.00",1),
            ({"start":date(2025,1,1),"end":date(2025,1,1)},"23.80",1),
            ({"seller":30,"product":100,"uf":"BA","start":date(2025,2,2),"end":date(2025,2,2)},"9.90",1)]:
            with self.subTest(kwargs=kwargs):
                k=self.summary(**kwargs)["kpi"]
                self.assertEqual(k["faturamento_total"],Decimal(expected))
                self.assertEqual(k["pedidos_faturados"],orders)
        data=self.summary(product=100)
        self.assertEqual(sum(r["faturamento"] for r in data["monthly"]),Decimal("28.70"))
        self.assertEqual(sum(r["faturamento"] for r in data["sellers"]),Decimal("28.70"))
        self.assertEqual(sum(r["faturamento"] for r in data["ufs"]),Decimal("28.70"))
        self.assertEqual([r["id_produto"] for r in data["products"]],[100])

    def test_rankings_and_recurrence(self):
        data=self.summary()
        self.assertEqual(data["products"][0]["id_produto"],200)
        self.assertEqual(data["products"][0]["unidades"],4)
        self.assertEqual(data["recurring"][0]["id_cliente"],10)
        self.assertEqual(data["recurring"][0]["pedidos"],2)
        self.assertEqual(data["recurrence"][0]["clientes_recorrentes"],1)

    def test_parameterized_injection_empty_and_invalid_dates(self):
        result=self.summary(uf="BA' OR 1=1 --")
        self.assertEqual(result["kpi"]["itens_faturados"],0)
        self.assertEqual(result["monthly"],[])
        with self.assertRaises(reader.AnalyticsError):
            self.summary(start=date(2026,1,1),end=date(2025,1,1))

    def test_readonly_and_no_changes(self):
        before=hashlib.sha256(Path(self.path).read_bytes()).hexdigest()
        with reader.connection(self.path) as c:
            with self.assertRaises(duckdb.Error):
                c.execute("CREATE TABLE forbidden(id INTEGER)")
        self.summary()
        self.assertEqual(before,hashlib.sha256(Path(self.path).read_bytes()).hexdigest())

    def test_details_filter_pagination(self):
        rows=reader.details(self.path,self.version,self.filters,size=25)
        self.assertEqual(len(rows),4)
        self.assertEqual(len({r["id_item"] for r in rows}),4)
        self.assertEqual(reader.details(self.path,self.version,self.filters,page=2,size=25),[])
        chosen=reader.details(self.path,self.version,reader.Filters(date(2025,1,1),date(2025,2,28),product=100),size=25)
        self.assertEqual(len(chosen),2)
        with self.assertRaises(reader.AnalyticsError):
            reader.details(self.path,self.version,self.filters,size=5000)

    def test_missing_file_does_not_create(self):
        path=self.root/"absent.duckdb"
        with self.assertRaisesRegex(reader.AnalyticsError,"não encontrado"):
            reader.publication(path)
        self.assertFalse(path.exists())

    def test_missing_gold_contract(self):
        path=self.root/"empty.duckdb"
        duckdb.connect(str(path)).close()
        with self.assertRaises(reader.AnalyticsError):
            reader.publication(path)

    def test_reader_failure_is_friendly(self):
        with patch("frontend.analytics.reader.duckdb.connect",side_effect=duckdb.IOException("locked")):
            with self.assertRaises(reader.AnalyticsError):
                reader.publication(self.path)

    def test_money_display_and_ui(self):
        self.assertEqual(moeda(Decimal("1234567.89")),"R$ 1.234.567,89")
        with patch.dict("os.environ",{"WAREHOUSE_DB_PATH":self.path}):
            app=AppTest.from_function(analytics_app,default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertEqual([m.value for m in app.metric],["R$ 48,70","3","R$ 16,23","4"])
            self.assertEqual(len(app.get("plotly_chart")),5)
            self.assertEqual(len(app.dataframe[0].value),4)
            next(x for x in app.selectbox if x.label=="UF").set_value("PE").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value,"R$ 15,00")
            next(x for x in app.date_input if x.label=="Data inicial").set_value(date(2026,1,1)).run()
            self.assertTrue(app.warning)
            self.assertEqual(len(app.metric),0)

    def test_update_invalidates_cache_and_rejects_stale_version(self):
        from frontend.analytics.ui import cached_summary
        before=cached_summary(self.path,self.version,self.filters,0)
        self.rows["itens_pedido"][2]["preco_unitario"]=Decimal("11.90")
        self.rows["itens_pedido"][2]["updated_at"]=datetime(2025,2,4,tzinfo=timezone.utc)
        publish(self.silver,self.rows,2)
        self.warehouse.run("incremental")
        version=reader.publication(self.path)
        after=cached_summary(self.path,version,self.filters,0)
        self.assertNotEqual(version,self.version)
        self.assertEqual(before["kpi"]["faturamento_total"],Decimal("48.70"))
        self.assertEqual(after["kpi"]["faturamento_total"],Decimal("50.70"))
        with self.assertRaises(reader.AnalyticsError):
            reader.summary(self.path,self.version,self.filters)

    def test_reused_upgrades_views_without_touching_fact(self):
        before=self.sql("SELECT * FROM fato_vendas ORDER BY id_item")
        c=duckdb.connect(self.path)
        c.execute("DROP VIEW gold_vendas_detalhadas")
        c.execute("DROP VIEW gold_status_carga")
        c.close()
        result=self.warehouse.run("incremental")
        self.assertEqual(result["status"],"REUSED")
        self.assertEqual(before,self.sql("SELECT * FROM fato_vendas ORDER BY id_item"))
        self.assertEqual(self.summary()["kpi"]["pedidos_faturados"],3)

    def test_missing_and_empty_ui(self):
        with patch.dict("os.environ",{"WAREHOUSE_DB_PATH":str(self.root/"absent.duckdb")}):
            app=AppTest.from_function(analytics_app).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.warning)
            self.assertEqual(len(app.metric),0)
        for order in self.rows["pedidos"]:
            if order["status"]=="FATURADO":order["status"]="PENDENTE"
        publish(self.silver,self.rows,2)
        self.warehouse.run("incremental")
        with patch.dict("os.environ",{"WAREHOUSE_DB_PATH":self.path}):
            app=AppTest.from_function(analytics_app).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.info)
            self.assertEqual(len(app.metric),0)

    def test_navigation_independent_from_operational_api(self):
        from unittest.mock import Mock
        response=Mock(ok=True,status_code=200)
        response.json.return_value=[]
        with patch.dict("os.environ",{"WAREHOUSE_DB_PATH":self.path}),patch(
                "frontend.api.requests.request",return_value=response) as request:
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=20).run()
            self.assertIn("Pedidos",app.radio[0].options)
            request.reset_mock()
            app.radio[0].set_value("Inteligência Comercial").run()
            self.assertFalse(app.exception)
            request.assert_not_called()
            self.assertEqual(app.metric[0].value,"R$ 48,70")


if __name__=="__main__":
    unittest.main()
