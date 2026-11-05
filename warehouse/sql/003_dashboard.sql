-- Contrato Gold filtrável: uma linha por item faturado; sem preço de catálogo.
CREATE OR REPLACE VIEW gold_vendas_detalhadas AS
SELECT f.id_item,f.id_pedido,f.id_cliente,f.id_produto,f.id_vendedor,
 t.data,t.ano_mes,f.data_pedido,c.razao_social AS cliente,c.uf,
 p.nome AS produto,v.nome AS vendedor,f.quantidade,f.preco_unitario,
 f.desconto,f.valor_bruto,f.valor_liquido
FROM fato_vendas f
JOIN dim_cliente c USING(sk_cliente)
JOIN dim_produto p USING(sk_produto)
JOIN dim_vendedor v USING(sk_vendedor)
JOIN dim_tempo t USING(sk_tempo);

CREATE OR REPLACE VIEW gold_status_carga AS
SELECT silver_version,committed_at FROM dw_state WHERE singleton=1;

