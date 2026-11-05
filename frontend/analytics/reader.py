"""Consultas analíticas exclusivamente Gold; nunca abre conexão de escrita."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
import os
from pathlib import Path

import duckdb



class AnalyticsError(RuntimeError):
    pass


def database_path():
    default = Path(__file__).resolve().parents[2] / "data/warehouse/pastel_da_casa.duckdb"
    value = os.getenv("WAREHOUSE_DB_PATH")
    return (Path(value).expanduser() if value else default).resolve()


@contextmanager
def connection(path):
    path = Path(path)
    if not path.is_file():
        raise AnalyticsError("Data Warehouse não encontrado. Após autorização, execute a carga FULL descrita no README.")
    c = None
    try:
        c = duckdb.connect(str(path), read_only=True)
        c.execute("SET TimeZone='UTC'")
        c.execute("BEGIN TRANSACTION")
        yield c
    except (duckdb.Error, OSError) as error:
        raise AnalyticsError("Não foi possível ler o Data Warehouse. Ele pode estar em atualização, bloqueado ou sem as views Gold da Etapa 09. Feche leitores durante a carga autorizada e tente novamente.") from error
    finally:
        if c is not None:
            c.close()


def rows(c, sql, params=()):
    result = c.execute(sql, params)
    names = [d[0] for d in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def publication(path):
    with connection(path) as c:
        result = rows(c, "SELECT silver_version,committed_at FROM gold_status_carga")
        if not result:
            raise AnalyticsError("Data Warehouse sem publicação. Após autorização, execute uma carga FULL.")
        # Verifica o contrato mesmo quando a fato está vazia.
        c.execute("SELECT id_item,valor_liquido FROM gold_vendas_detalhadas LIMIT 0")
        stat = Path(path).stat()
        return (result[0]["silver_version"], str(result[0]["committed_at"]), stat.st_mtime_ns, stat.st_size)


@dataclass(frozen=True)
class Filters:
    start: date
    end: date
    seller: int | None = None
    product: int | None = None
    uf: str | None = None

    def parameters(self):
        if self.start > self.end:
            raise AnalyticsError("A data inicial deve ser anterior ou igual à data final.")
        return [self.start, self.end, self.seller, self.seller,
                self.product, self.product, self.uf, self.uf]


WHERE = """data BETWEEN ? AND ? AND (? IS NULL OR id_vendedor=?)
 AND (? IS NULL OR id_produto=?) AND (? IS NULL OR uf=?)"""
CTE = "WITH vendas AS (SELECT * FROM gold_vendas_detalhadas WHERE " + WHERE + ") "


def options(path, version):
    with connection(path) as c:
        ensure_version(c, version)
        bounds = c.execute("SELECT min(data),max(data) FROM gold_vendas_detalhadas").fetchone()
        return {
            "bounds": bounds,
            "sellers": rows(c, "SELECT DISTINCT id_vendedor,vendedor FROM gold_vendas_detalhadas ORDER BY vendedor,id_vendedor"),
            "products": rows(c, "SELECT DISTINCT id_produto,produto FROM gold_vendas_detalhadas ORDER BY produto,id_produto"),
            "ufs": [r[0] for r in c.execute("SELECT DISTINCT uf FROM gold_vendas_detalhadas ORDER BY uf").fetchall()],
        }


def ensure_version(c, version):
    row = c.execute("SELECT silver_version,committed_at FROM gold_status_carga").fetchone()
    if not row or (row[0], str(row[1])) != tuple(version[:2]):
        raise AnalyticsError("A publicação mudou durante a consulta. Clique em Atualizar indicadores.")


def summary(path, version, filters):
    params = filters.parameters()
    with connection(path) as c:
        ensure_version(c, version)
        kpi = rows(c, CTE + """SELECT
            coalesce(sum(valor_liquido),0) AS faturamento_total,
            count(DISTINCT id_pedido) AS pedidos_faturados,
            count(*) AS itens_faturados,coalesce(sum(quantidade),0) AS unidades_vendidas
            FROM vendas""", params)[0]
        bounds = c.execute("SELECT min(data),max(data) FROM gold_vendas_detalhadas").fetchone()
        if (filters.seller is None and filters.product is None and filters.uf is None
                and (bounds[0] is None or (filters.start <= bounds[0] and filters.end >= bounds[1]))):
            # Reutiliza o contrato executivo original quando o recorte abrange toda a base.
            kpi = rows(c, "SELECT * FROM gold_kpis")[0]
        else:
            # Recortes calculados sobre a mesma Gold; precisão suficiente para DECIMAL(38,2).
            with localcontext() as context:
                context.prec = 50
                kpi["ticket_medio"] = ((kpi["faturamento_total"] / kpi["pedidos_faturados"])
                    .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if kpi["pedidos_faturados"] else Decimal("0.00"))
        queries = {
            "monthly": "SELECT ano_mes,sum(valor_liquido) faturamento FROM vendas GROUP BY ano_mes ORDER BY ano_mes",
            "products": """SELECT id_produto,produto,sum(quantidade) unidades,sum(valor_liquido) faturamento
                FROM vendas GROUP BY id_produto,produto ORDER BY unidades DESC,faturamento DESC,id_produto LIMIT 10""",
            "sellers": """SELECT id_vendedor,vendedor,sum(valor_liquido) faturamento FROM vendas
                GROUP BY id_vendedor,vendedor ORDER BY faturamento DESC,id_vendedor""",
            "ufs": "SELECT uf,sum(valor_liquido) faturamento FROM vendas GROUP BY uf ORDER BY faturamento DESC,uf",
            "recurring": """SELECT id_cliente,cliente,count(DISTINCT id_pedido) pedidos,sum(valor_liquido) faturamento
                FROM vendas GROUP BY id_cliente,cliente HAVING count(DISTINCT id_pedido)>=2
                ORDER BY pedidos DESC,faturamento DESC,id_cliente LIMIT 20""",
            "recurrence": """SELECT count(*) clientes_com_compras,
                count(*) FILTER (WHERE pedidos>=2) clientes_recorrentes FROM
                (SELECT id_cliente,count(DISTINCT id_pedido) pedidos FROM vendas GROUP BY id_cliente)""",
        }
        return {"kpi": kpi, **{name: rows(c, CTE + query, params) for name, query in queries.items()}}


def details(path, version, filters, page=1, size=50):
    if not isinstance(page, int) or page < 1 or size not in (25, 50, 100):
        raise AnalyticsError("Paginação inválida.")
    with connection(path) as c:
        ensure_version(c, version)
        return rows(c, CTE + """SELECT id_item,id_pedido,data,cliente,uf,vendedor,produto,
            quantidade,preco_unitario,desconto,valor_liquido FROM vendas
            ORDER BY data_pedido DESC,id_item DESC LIMIT ? OFFSET ?""",
            filters.parameters() + [size, (page-1)*size])
