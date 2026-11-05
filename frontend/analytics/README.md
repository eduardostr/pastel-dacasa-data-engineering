# Inteligência Comercial — Etapa 09

Área analítica separada do CRM operacional. Streamlit → consultas SQL parametrizadas → views Gold → DuckDB. Não usa FastAPI, PostgreSQL ou Parquet diretamente.

## Executar

Na raiz do projeto, PowerShell:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r frontend/requirements.txt
.\.venv314\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1
```

Abra http://127.0.0.1:8501 e selecione **Inteligência Comercial**.
O CRM operacional continua necessitando da API; a área analítica funciona independentemente dela.

Opcional: `$env:WAREHOUSE_DB_PATH = 'C:\caminho\arquivo.duckdb'`.
Padrão: `data/warehouse/pastel_da_casa.duckdb`, relativo à raiz do projeto.

## Preparar e atualizar o DW

A interface abre somente arquivos existentes, com `read_only=True`, e não cria views ou tabelas.
As novas views `gold_vendas_detalhadas` (uma linha por item faturado) e `gold_status_carga`
são publicadas transacionalmente pelo loader junto das views anteriores.
Nenhuma tabela dimensional foi alterada.

**Somente após autorização explícita**, para um DW inexistente:
```powershell
.\.venv314\Scripts\python.exe -m warehouse --mode full --execute --allow-persistent
```

Para DW existente, após autorização e com leitores Streamlit fechados durante a escrita:
```powershell
.\.venv314\Scripts\python.exe -m warehouse --mode incremental --execute --allow-persistent
```

Uma Silver já carregada retorna REUSED e instala as views Gold sem recarregar a fato.
Após novas alterações operacionais, execute primeiro a ETL incremental conforme README e depois
o warehouse incremental, com as autorizações aplicáveis. Reinicie o Streamlit e clique
**Atualizar indicadores**. Não é preciso repetir a geração sintética.

Cache de agregados/opções/páginas: TTL de 300 segundos, limites de entradas, chave por caminho,
versão/publicação, tamanho/mtime do arquivo, filtros e revisão manual.
A versão é conferida sem cache a cada interação e novamente dentro da transação de leitura.
Não há conexões armazenadas em cache; todas fecham mesmo após erros.

## Indicadores e filtros

- Faturamento: soma do valor líquido histórico dos itens faturados, já descontado o desconto.
- Pedidos: COUNT(DISTINCT id_pedido), mesmo com vários itens por pedido.
- Ticket médio: faturamento do recorte / pedidos distintos; Decimal com arredondamento comercial a centavos.
- Itens: quantidade de linhas faturadas; unidades somam a quantidade dos itens.
- Recorrência: clientes com ao menos dois pedidos distintos no recorte; gráfico dos 20 primeiros,
  contador considera todos os clientes recorrentes.
- Top produtos: dez primeiros por unidades; desempate por receita e ID.

Todos os gráficos e detalhes recebem o mesmo período inclusivo (UTC), vendedor, produto e UF.
Com filtro de produto, ticket e receita representam somente os itens selecionados dos pedidos,
não o valor integral de cada pedido. Cadastro ativo/inativo não exclui vendas históricas.
A UF é a dimensão corrente (SCD1), conforme contrato do warehouse.
Preços de catálogo não entram nos cálculos. Cálculos usam Decimal; somente os valores agregados
dos gráficos são convertidos para float na renderização Plotly.

SQL agrega no DuckDB. Detalhes: 25, 50 ou 100 linhas por página, ordem estável por data e ID de item.
Sem venda no recorte, exibe estado vazio sem cards. Sem arquivo, contrato Gold ou publicação,
exibe orientação; erros de leitura/bloqueio não derrubam o CRM.

## Verificar

```powershell
.\.venv314\Scripts\python.exe -B -m unittest discover -s frontend/tests -p test_analytics.py -v
.\.venv314\Scripts\python.exe -B -m unittest discover -s warehouse/tests -v
```

Os testes analíticos usam apenas arquivos temporários, com fixtures isoladas.
