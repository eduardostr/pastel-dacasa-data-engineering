-- Execute somente em um DW já carregado e autorizado.
SELECT * FROM gold_kpis;
SELECT * FROM gold_faturamento_total;
SELECT * FROM gold_pedidos_faturados;
SELECT * FROM gold_ticket_medio;
SELECT * FROM gold_faturamento_mensal ORDER BY ano,mes;
SELECT * FROM gold_produtos_mais_vendidos ORDER BY posicao,id_produto LIMIT 10;
SELECT * FROM gold_faturamento_uf ORDER BY faturamento DESC,uf;
SELECT * FROM gold_ranking_vendedores ORDER BY posicao,id_vendedor;
SELECT * FROM gold_clientes_recorrentes ORDER BY faturamento DESC,id_cliente LIMIT 20;

-- Conferir preço histórico versus preço atual; não recalcular vendas pelo catálogo.
SELECT f.id_item,f.id_pedido,f.preco_unitario,p.preco_catalogo,f.valor_liquido
FROM fato_vendas f JOIN dim_produto p USING(sk_produto)
ORDER BY f.id_item LIMIT 10;

SELECT silver_version,silver_run_id,committed_at FROM dw_state;
SELECT run_id,mode,silver_version,status,duration_seconds
FROM dw_runs ORDER BY started_at DESC LIMIT 20;

