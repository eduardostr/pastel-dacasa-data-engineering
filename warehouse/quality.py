from warehouse.model import DIMENSIONS, FACT_FIELDS, hash_expression

CORE_SALE = ["id_item", "id_pedido", "id_produto", "id_cliente", "id_vendedor", "data_pedido",
             "status", "quantidade", "preco_unitario", "desconto", "subtotal", "total_pedido"]


def ensure_zero(c, sql, label):
    value = c.execute(sql).fetchone()[0]
    if value:
        raise ValueError(f"Qualidade: {label} ({value} registros)")


def difference_count(c, left, right):
    return c.execute(f"SELECT count(*) FROM (({left} EXCEPT {right}) UNION ALL ({right} EXCEPT {left})) differences").fetchone()[0]


def validate_source(c):
    for table, key in (("clientes", "id_cliente"), ("produtos", "id_produto"),
                       ("vendedores", "id_vendedor"), ("pedidos", "id_pedido"),
                       ("itens_pedido", "id_item"), ("movimentacoes_estoque", "id_movimentacao"),
                       ("vendas_detalhadas", "id_item")):
        ensure_zero(c, f"SELECT count(*)-count(DISTINCT {key}) FROM s_{table}", "PK nula/duplicada: " + table)
        ensure_zero(c, f"SELECT count(*) FROM s_{table} WHERE {key}<=0", "PK não positiva: " + table)
    for table in ("clientes", "produtos", "vendedores", "pedidos", "itens_pedido", "movimentacoes_estoque"):
        ensure_zero(c, f"SELECT count(*) FROM s_{table} WHERE created_at IS NULL OR updated_at IS NULL OR updated_at<created_at",
                    "auditoria inválida: " + table)
    for child, field, parent, pk in (
        ("pedidos", "id_cliente", "clientes", "id_cliente"),
        ("pedidos", "id_vendedor", "vendedores", "id_vendedor"),
        ("itens_pedido", "id_pedido", "pedidos", "id_pedido"),
        ("itens_pedido", "id_produto", "produtos", "id_produto"),
        ("movimentacoes_estoque", "id_produto", "produtos", "id_produto"),
        ("movimentacoes_estoque", "id_pedido", "pedidos", "id_pedido"),
    ):
        optional = child == "movimentacoes_estoque" and field == "id_pedido"
        null = "" if optional else f" OR ch.{field} IS NULL"
        ensure_zero(c, f"SELECT count(*) FROM s_{child} ch LEFT JOIN s_{parent} p ON p.{pk}=ch.{field} WHERE (ch.{field} IS NOT NULL AND p.{pk} IS NULL){null}",
                    "FK inválida: " + child + "." + field)
    ensure_zero(c, "SELECT count(*) FROM s_pedidos WHERE status IS NULL OR status NOT IN ('PENDENTE','FATURADO','CANCELADO') OR data_pedido IS NULL", "status/data do pedido")
    ensure_zero(c, "SELECT count(*) FROM s_produtos WHERE preco IS NULL OR preco<=0 OR peso_gramas IS NULL OR peso_gramas<=0 OR estoque_atual IS NULL OR estoque_atual<0", "produto inválido")
    ensure_zero(c, """SELECT count(*) FROM s_itens_pedido WHERE quantidade IS NULL OR quantidade<=0
        OR preco_unitario IS NULL OR preco_unitario<0 OR desconto IS NULL OR desconto<0
        OR desconto>CAST(quantidade AS DECIMAL(18,0))*preco_unitario""", "valores dos itens")
    ensure_zero(c, "SELECT count(*) FROM (SELECT id_pedido,id_produto FROM s_itens_pedido GROUP BY id_pedido,id_produto HAVING count(*)>1) d", "produto repetido no pedido")
    ensure_zero(c, "SELECT count(*) FROM s_movimentacoes_estoque WHERE quantidade IS NULL OR quantidade<=0 OR tipo NOT IN ('ENTRADA','SAIDA')", "movimentação inválida")
    ensure_zero(c, """SELECT count(*) FROM s_itens_pedido i JOIN s_pedidos p USING(id_pedido)
        LEFT JOIN s_movimentacoes_estoque m ON m.id_pedido=i.id_pedido AND m.id_produto=i.id_produto AND m.tipo='SAIDA'
        WHERE (p.status='FATURADO' AND (m.id_movimentacao IS NULL OR m.quantidade<>i.quantidade))
           OR (p.status<>'FATURADO' AND m.id_movimentacao IS NOT NULL)""", "saídas e itens divergentes")
    ensure_zero(c, """SELECT count(*) FROM (SELECT id_pedido,id_produto FROM s_movimentacoes_estoque
        WHERE tipo='SAIDA' AND id_pedido IS NOT NULL GROUP BY id_pedido,id_produto HAVING count(*)>1) d""", "saída duplicada")
    ensure_zero(c, """SELECT count(*) FROM s_pedidos p WHERE p.status='FATURADO'
        AND NOT EXISTS(SELECT 1 FROM s_itens_pedido i WHERE i.id_pedido=p.id_pedido)""", "pedido faturado sem itens")
    c.execute("""CREATE OR REPLACE TEMP TABLE expected_sales AS
        WITH items AS (
            SELECT i.id_item,i.id_pedido,i.id_produto,p.id_cliente,p.id_vendedor,p.data_pedido,p.status,
                i.quantidade,i.preco_unitario,i.desconto,
                CAST(CAST(i.quantidade AS DECIMAL(18,0))*i.preco_unitario-i.desconto AS DECIMAL(38,2)) AS subtotal
            FROM s_itens_pedido i JOIN s_pedidos p USING(id_pedido) WHERE p.status='FATURADO'
        )
        SELECT *,CAST(sum(subtotal) OVER(PARTITION BY id_pedido) AS DECIMAL(38,2)) AS total_pedido FROM items
    """)
    columns = ",".join(CORE_SALE)
    if difference_count(c, f"SELECT {columns} FROM expected_sales", f"SELECT {columns} FROM s_vendas_detalhadas"):
        raise ValueError("Qualidade: vendas_detalhadas não reconcilia com pedidos/itens Silver")
    expected = c.execute("SELECT count(*),count(DISTINCT id_pedido),coalesce(sum(subtotal),0) FROM expected_sales").fetchone()
    return {"silver_sale_items": expected[0], "silver_billed_orders": expected[1], "silver_net_value": str(expected[2])}


def validate_target(c):
    for name, (sk, key, _, attrs) in DIMENSIONS.items():
        ensure_zero(c, f"SELECT count(*)-count(DISTINCT {sk}) FROM {name}", "SK: " + name)
        ensure_zero(c, f"SELECT count(*)-count(DISTINCT {key}) FROM {name}", "ID/data original: " + name)
        fields = [key] + attrs
        if difference_count(c, f"SELECT {','.join(fields)} FROM {name} WHERE presente_na_silver",
                            f"SELECT {','.join(fields)} FROM st_{name}"):
            raise ValueError("Qualidade: dimensão não reconcilia: " + name)
        ensure_zero(c, f"SELECT count(*) FROM {name} WHERE row_hash IS DISTINCT FROM {hash_expression(fields)}", "hash da dimensão: " + name)
    fields = ",".join(FACT_FIELDS)
    if difference_count(c, f"SELECT {fields} FROM fato_vendas", f"SELECT {fields} FROM st_fato_vendas"):
        raise ValueError("Qualidade: fato não reconcilia por item")
    for dim, (sk, _, _, _) in DIMENSIONS.items():
        ensure_zero(c, f"SELECT count(*) FROM fato_vendas f LEFT JOIN {dim} d USING({sk}) WHERE d.{sk} IS NULL OR NOT d.presente_na_silver",
                    "fato sem dimensão: " + sk)
    ensure_zero(c, "SELECT count(*)-count(DISTINCT id_item) FROM fato_vendas", "item duplicado na fato")
    ensure_zero(c, """SELECT count(*) FROM fato_vendas f JOIN dim_tempo t USING(sk_tempo)
        WHERE CAST(f.data_pedido AS DATE)<>t.data OR f.valor_liquido<>f.valor_bruto-f.desconto
           OR f.valor_bruto<>CAST(f.quantidade AS DECIMAL(18,0))*f.preco_unitario""", "datas ou valores da fato")
    fact = c.execute("SELECT count(*),count(DISTINCT id_pedido),coalesce(sum(valor_liquido),0) FROM fato_vendas").fetchone()
    source = c.execute("SELECT count(*),count(DISTINCT id_pedido),coalesce(sum(subtotal),0) FROM s_vendas_detalhadas").fetchone()
    if fact != source:
        raise ValueError("Qualidade: contagem/valor global da fato diverge da Silver")
    return {"fact_items": fact[0], "billed_orders": fact[1], "net_value": str(fact[2]), "foreign_key_errors": 0, "financial_errors": 0}
