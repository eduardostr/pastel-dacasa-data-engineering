# Validação — Etapa 09

Data: 2026-11-05.

## Entrega

Criados:
- frontend/analytics/__init__.py
- frontend/analytics/reader.py: caminho configurável, conexões somente leitura, publicação, filtros parametrizados, agregações e paginação.
- frontend/analytics/ui.py: cards, cinco gráficos Plotly, recorrência, detalhes, filtros, cache e estados de erro/vazio.
- frontend/analytics/README.md: arquitetura, execução, contratos e atualização.
- frontend/tests/test_analytics.py: 14 testes isolados.
- warehouse/sql/003_dashboard.sql: views Gold detalhada e de publicação.

Modificados:
- frontend/app.py: nova área sem alterar os fluxos existentes.
- frontend/requirements.txt: Plotly, DuckDB e pytz.
- warehouse/loader.py: publicação transacional das views adicionais, inclusive no caminho REUSED.
- README.md e warehouse/README.md: referências para a nova área.

## Testes executados

- 14 testes analíticos: OK (8,936 s na execução final).
- 25 testes warehouse: OK (13,054 s).
- 12 regressões frontend operacional (test_frontend e test_vendas): OK (3,332 s).
- Total: 51 aprovados.

Cobertura: Gold, preços históricos, contagem distinta, filtros individuais e combinados,
parâmetros sem interpolação, rankings/recorrência, paginação, arquivo ausente,
contrato incompleto, DW sem vendas, erro de leitura/bloqueio, valores monetários,
renderização AppTest, independência da API, cache após atualização, views em REUSED
sem alterar a fato e conexão que rejeita escrita. Todos usam bancos temporários.
Os avisos ScriptRunContext são do AppTest fora do servidor Streamlit.

## Cópia temporária do DW real

Foi copiado o arquivo persistente para um diretório temporário, aplicada a SQL003 **somente na cópia**,
e executadas as consultas da interface. A cópia foi removida ao finalizar.

- Faturamento: R$ 14.420.828,23.
- Pedidos faturados: 14.998.
- Itens faturados: 44.939.
- Unidades: 473.781.
- Ticket: R$ 961,52.
- Detalhes retornados: 50 linhas.
- Resumo e detalhes sem cache: 0,154 s (medição local, sem garantia de SLA).
- SHA-256 do arquivo original antes/depois: idêntico.

## Registro da entrega original e atualização posterior

Atualização 2026-11-05: após autorização explícita, as duas views Gold foram aplicadas no DW persistente com backup. Fingerprints das tabelas e indicadores foram preservados; consultas dos gráficos validadas. O texto seguinte documenta a pendência existente antes dessa autorização.

O DW persistente existe e possui os dados da Etapa 08, mas ainda não tem as duas views
Gold novas. Nenhuma carga persistente foi executada nesta etapa.
Após autorização explícita, fechar leitores Streamlit e executar:

```powershell
.\.venv314\Scripts\python.exe -m warehouse --mode incremental --execute --allow-persistent
```

Com a mesma Silver, retorna REUSED, preserva dimensões/fato e publica as views dentro da
transação. Se houver nova Silver publicada, o comando também sincroniza essa versão;
confira a publicação antes da execução autorizada.
Até a atualização, a interface apresenta orientação, sem métricas falsas.

PostgreSQL, API, ETL, Silver e .env não foram modificados. Nenhuma publicação GitHub.
Não foram produzidas capturas de navegador; interface verificada por AppTest, sem inspeção visual manual.
