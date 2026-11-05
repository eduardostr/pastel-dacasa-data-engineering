# Dicionário de dados

Contratos executáveis: database/oltp/001_schema.sql, database/migrations/, etl/config/schema.py e warehouse/sql/001_schema.sql.

## Origem e Silver

| Entidade | Chave | Campos de negócio |
| --- | --- | --- |
| clientes | id_cliente BIGINT | razao_social, cnpj único, cidade, uf, ativo |
| produtos | id_produto BIGINT | nome único, peso_gramas, preco, estoque_atual, ativo |
| vendedores | id_vendedor BIGINT | nome, email único, ativo |
| pedidos | id_pedido BIGINT | id_cliente, id_vendedor, status, data_pedido |
| itens_pedido | id_item BIGINT | id_pedido, id_produto, quantidade, preco_unitario, desconto |
| movimentacoes_estoque | id_movimentacao BIGINT | id_produto, id_pedido opcional, tipo, quantidade, observacao opcional, data_movimentacao |

Todas possuem created_at e updated_at TIMESTAMPTZ; gatilhos mantêm atualizações.
Valores de entrada usam NUMERIC(12,2), quantidades/peso inteiros. CNPJ é texto para preservar zeros.
Clientes não possuem e-mail. Status: PENDENTE/FATURADO/CANCELADO. Tipo de movimento: ENTRADA/SAIDA.
Cada produto é único dentro de um pedido. Movimentos históricos podem não ter pedido associado.

Parquet preserva chaves int64, quantidades int32, bool, dinheiro decimal128 e timestamps UTC em microssegundos.
Metadados: _run_id, _extracted_at, _source, _record_hash. Quarentena acrescenta _rejection_reason.
vendas_detalhadas deriva itens faturados com participantes, produto, preço, desconto, subtotal, total_pedido e source_updated_at.
Subtotal/total derivado: decimal128(38,2). Não some total_pedido por linha: ele é repetido por item.

## Dimensões e fato

| Tabela | Chave/grão | Atributos/medidas |
| --- | --- | --- |
| dim_cliente | sk_cliente / id_cliente único | razao_social, cnpj, cidade, uf, ativo |
| dim_produto | sk_produto / id_produto único | nome, peso_gramas, preco_catalogo, estoque_atual, ativo |
| dim_vendedor | sk_vendedor / id_vendedor único | nome, email, ativo |
| dim_tempo | sk_tempo / data única | ano, mes, dia, trimestre, ano_mes, mes_nome, dia_semana ISO, dia_semana_nome, fim_de_semana |
| fato_vendas | id_item único | IDs de origem, quatro SKs, data_pedido, quantidade, preco_unitario, desconto, valor_bruto, valor_liquido |

Dimensões cadastrais retêm datas de origem; controles incluem row_hash, presente_na_silver, loaded_version,
dw_created_at e dw_updated_at. Fato inclui source_updated_at, row_hash, loaded_version e datas do DW.
valor_bruto = quantidade × preço histórico; valor_liquido = valor_bruto − desconto. Medidas totais DECIMAL(38,2).
SKs não são reiniciadas a cada carga. Ausências da Silver são sinalizadas nas dimensões; fatos ausentes são reconciliados apenas no DW.
dw_state fixa a publicação Silver aplicada; dw_runs registra tentativas, status, métricas, validações e duração.

## Contratos Gold

| View | Conteúdo |
| --- | --- |
| gold_kpis | faturamento_total, pedidos_faturados distintos, itens_faturados, unidades_vendidas, ticket_medio |
| gold_faturamento_total / gold_pedidos_faturados / gold_ticket_medio | projeções dos KPIs |
| gold_faturamento_mensal | ano, mes, ano_mes, faturamento, pedidos_faturados, unidades |
| gold_produtos_mais_vendidos | produto, unidades, receita e posição |
| gold_ranking_vendedores | vendedor, receita, pedidos e posição |
| gold_faturamento_uf | UF, receita e pedidos |
| gold_clientes_recorrentes | clientes com pelo menos dois pedidos, receita e primeira/última compra |
| gold_vendas_detalhadas | item, pedido, participantes, produto, data UTC, UF e medidas históricas |
| gold_status_carga | silver_version e committed_at |

SQL completo em warehouse/sql/002_gold.sql e 003_dashboard.sql. O ticket é arredondado a centavos;
gráficos usam agregados, não preços de catálogo.
