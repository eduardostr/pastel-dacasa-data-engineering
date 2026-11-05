# Pastel da Casa — validação do DW (Etapa 08)

Data: 05/11/2026. Estado: IMPLEMENTADO E VALIDADO SEM CARGA PERSISTENTE.

## Testes automatizados

25 testes passaram, zero falhas. Duração da suíte final: 12,707 segundos.
DuckDB 2.0.0, PyArrow 26.0.1 e pytz 2026.6 no Python do projeto.

Fixtures exclusivamente locais: Parquets Silver publicados em diretórios
temporários e arquivos DuckDB temporários. Nenhum PostgreSQL foi utilizado
como origem ou alterado pelos testes do warehouse.

Cobertura:
- Dimensões com SKs distintas dos IDs CRM; fatos por item faturado.
- Preço histórico 9,90 preservado apesar de catálogo a 100,00.
- Faturamento, pedidos distintos, ticket, meses, produtos, UF, vendedores e recorrência.
- UTC/calendário contínuo e histórico de entidades atualmente inativas.
- Inclusões incrementais, SCD1 e SKs estáveis.
- Reconciliação de correções monetárias e alterações de status.
- Remoção da fato de pedidos que deixam de ser faturados.
- Preservação do mapeamento de dimensão ausente e reutilização no retorno.
- Reuso da mesma Silver e nova versão sem mudanças de negócio.
- Falha e rollback de dimensões/fato/controle, seguido de retomada.
- Falha de auditoria depois do commit e reconciliação no reuso.
- PK/FK, duplicidades, preço incorreto na venda e faturado sem itens.
- Checksum, manifesto com contagem divergente e arquivos staging não publicados.
- Proibição de retroceder versão e de alterar um arquivo durante a carga.
- CLI em modo plano e bloqueio de persistência sem confirmação técnica.

## Fixture dimensional de referência

| Tabela | Linhas |
| --- | ---: |
| dim_cliente | 2 |
| dim_produto | 2 |
| dim_vendedor | 2 |
| dim_tempo | 34 |
| fato_vendas | 4 |

Receita R$ 48,70; 3 pedidos faturados; ticket R$ 16,23. Dois itens de um mesmo
pedido contam uma única vez para pedidos/ticket/recorrência.
O teste de meio centavo confirmou arredondamento exato de R$ 0,005 para R$ 0,01.

## Integração adicional com a Silver real

Foi usado um banco DuckDB em diretório temporário, removido ao final. Esse teste
não criou data/warehouse/pastel_da_casa.duckdb.

Publicação Silver: 30f2e92e-d92e-4df9-b303-5e2e43e79bea.
Run Silver: 0d42d17e-5bea-4501-b912-2b509bd1ae3e.

| Tabela | Linhas confirmadas |
| --- | ---: |
| dim_cliente | 1001 |
| dim_produto | 50 |
| dim_vendedor | 30 |
| dim_tempo | 366 |
| fato_vendas | 44939 |

- Pedidos faturados: 14998.
- Faturamento: R$ 14.420.828,23.
- Unidades vendidas: 473781.
- Ticket médio: R$ 961,52.
- FULL temporária: 0,846 segundo.
- Reexecução: REUSED, 0,547 segundo.
- Zero erros de FK e financeiros.
- Manifesto e Parquets Silver permaneceram intactos.

Os 366 dias cobrem todas as datas existentes na Silver, incluindo pedidos
operacionais originais além do intervalo da geração sintética.

Os tempos são observações de uma execução local temporária, não garantia de
performance do futuro DW persistente. Não houve alteração do CRM, API, Streamlit,
.env, Docker Compose ou lógica da ETL. Não houve publicação no GitHub.

## Arquivos e controles

Código em warehouse/config.py, source.py, model.py, quality.py e loader.py.
CLI em warehouse/__main__.py; DDL, Gold e exemplos em warehouse/sql/.
Dependências em warehouse/requirements.txt; testes em warehouse/tests/.
Arquitetura, modelo dimensional, dicionário, fórmulas, limites e comandos em README.md.

dw_state só avança na mesma transação dos dados validados. dw_runs retém
tentativas, status, versão, métricas, duração e mensagens de erro.

## Pendência explícita

A carga persistente no DW de desenvolvimento aguarda autorização do usuário.
A CLI exige --execute --allow-persistent. Nenhum arquivo DuckDB operacional foi
criado pela entrega. A origem será exclusivamente a Silver publicada, sem PostgreSQL.

Relatório estruturado: validation_report.json.


> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../docs/VALIDATION.md.
