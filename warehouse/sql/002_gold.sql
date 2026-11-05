CREATE OR REPLACE VIEW gold_kpis AS
WITH k AS (
    SELECT coalesce(sum(valor_liquido),CAST(0 AS DECIMAL(38,2))) AS faturamento_total,
        count(DISTINCT id_pedido) AS pedidos_faturados,count(*) AS itens_faturados,
        coalesce(sum(quantidade),0) AS unidades_vendidas FROM fato_vendas
), cents AS (
    SELECT *,CASE WHEN pedidos_faturados=0 THEN CAST(0 AS HUGEINT)
        ELSE (CAST(faturamento_total*100 AS HUGEINT) + pedidos_faturados//2)//pedidos_faturados
        END AS ticket_centavos FROM k
)
SELECT faturamento_total,pedidos_faturados,itens_faturados,unidades_vendidas,
    CAST(concat((ticket_centavos//100)::VARCHAR,'.',lpad((ticket_centavos%100)::VARCHAR,2,'0')) AS DECIMAL(38,2)) AS ticket_medio
FROM cents;

CREATE OR REPLACE VIEW gold_faturamento_total AS SELECT faturamento_total FROM gold_kpis;
CREATE OR REPLACE VIEW gold_pedidos_faturados AS SELECT pedidos_faturados FROM gold_kpis;
CREATE OR REPLACE VIEW gold_ticket_medio AS SELECT ticket_medio FROM gold_kpis;

CREATE OR REPLACE VIEW gold_faturamento_mensal AS
SELECT t.ano,t.mes,t.ano_mes,sum(f.valor_liquido) AS faturamento,
    count(DISTINCT f.id_pedido) AS pedidos_faturados,sum(f.quantidade) AS unidades
FROM fato_vendas f JOIN dim_tempo t USING(sk_tempo) GROUP BY t.ano,t.mes,t.ano_mes;

CREATE OR REPLACE VIEW gold_produtos_mais_vendidos AS
SELECT p.id_produto,p.nome,sum(f.quantidade) AS unidades_vendidas,
    sum(f.valor_liquido) AS faturamento,count(DISTINCT f.id_pedido) AS pedidos_faturados,
    dense_rank() OVER(ORDER BY sum(f.quantidade) DESC,sum(f.valor_liquido) DESC) AS posicao
FROM fato_vendas f JOIN dim_produto p USING(sk_produto) GROUP BY p.id_produto,p.nome;

CREATE OR REPLACE VIEW gold_faturamento_uf AS
SELECT c.uf,sum(f.valor_liquido) AS faturamento,count(DISTINCT f.id_pedido) AS pedidos_faturados
FROM fato_vendas f JOIN dim_cliente c USING(sk_cliente) GROUP BY c.uf;

CREATE OR REPLACE VIEW gold_ranking_vendedores AS
SELECT v.id_vendedor,v.nome,sum(f.valor_liquido) AS faturamento,
    count(DISTINCT f.id_pedido) AS pedidos_faturados,
    dense_rank() OVER(ORDER BY sum(f.valor_liquido) DESC) AS posicao
FROM fato_vendas f JOIN dim_vendedor v USING(sk_vendedor) GROUP BY v.id_vendedor,v.nome;

CREATE OR REPLACE VIEW gold_clientes_recorrentes AS
SELECT c.id_cliente,c.razao_social,c.uf,count(DISTINCT f.id_pedido) AS pedidos_faturados,
    sum(f.valor_liquido) AS faturamento,min(t.data) AS primeira_compra,max(t.data) AS ultima_compra
FROM fato_vendas f JOIN dim_cliente c USING(sk_cliente) JOIN dim_tempo t USING(sk_tempo)
GROUP BY c.id_cliente,c.razao_social,c.uf HAVING count(DISTINCT f.id_pedido)>=2;

