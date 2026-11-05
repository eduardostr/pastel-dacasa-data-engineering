# Etapa 11.1 — Incremental orquestrado autorizado

Execução única em 2026-11-05, na branch feat/prefect-orchestration.
Autorização explícita recebida após diagnóstico e plano. Sem commit/push, FULL, geração sintética,
alteração operacional ou ativação de agendamento.

## Execução e identificadores

- Flow: pastel-da-casa-data-pipeline.
- Prefect run: 9ffcfa42-16de-41b8-a654-ac279ddb691a.
- Run lógico: d6cb127a-1507-4835-8bbd-0e3b79cf62f7.
- ETL run: 53a5e456-a90c-5447-974a-6b0a6e901192.
- DW run: 0a23e4e5-d21f-5f82-ac0c-9711a29454a3.
- mode=incremental, dry_run=false, validate_only=false; manual.
- Estado Prefect consultado pela API: COMPLETED.

Início UTC: 2026-11-05T16:37:35.795952Z.
Término UTC: 2026-11-05T16:38:18.619423Z.
São Paulo: 13:37:35 a 13:38:18.
Duração Prefect: **42,823471 s**; duração interna: 42,773 s.
Wrapper: 48,994 s, incluindo inicialização e coleta posterior.

| Task | Estado | Duração Prefect | Tentativas |
| --- | --- | ---: | ---: |
| check_source-486 | COMPLETED | 2.119318 s | 1 |
| run_etl-c4a | COMPLETED | 39.113642 s | 1 |
| validate_silver-23f | COMPLETED | 0.311582 s | 1 |
| run_warehouse-393 | COMPLETED | 0.660065 s | 1 |
| validate_gold-b77 | COMPLETED | 0.537465 s | 1 |
| finalize-faf | COMPLETED | 0.008354 s | 1 |

Horários e IDs individuais constam no JSON adjacente. Nenhuma task precisou de retry.

## Backup

Backup único verificado:
backups/etapa11_1/20261105T163729Z_d6cb127a-1507-4835-8bbd-0e3b79cf62f7/

- Controles ETL copiados e conferidos por SHA-256.
- SQLite copiado pela API backup com origem read-only; integrity_check=ok.
- DuckDB copiado com conexão read-only, sem WAL pendente, SHA-256 conferido.
- Controles DW copiados sem arquivos de lock.
- 60 arquivos Bronze/Silver anteriores preservados e conferidos por SHA-256 antes/depois.
- Fotografias before/after, checks, resultados Prefect e log local preservados no backup.
- Nenhum backup anterior substituído. Espaço inicial aproximado: 233 GiB.
- Backups e logs locais permanecem ignorados pelo Git.

## Processamento

**125.856 linhas examinadas** nas seis tabelas de origem.
**1 cliente reextraído** pela janela inclusiva de segurança; source_changed=0.
Não representa cliente novo ou conteúdo alterado. Demais tabelas: zero extraídas.
Todas: zero inserções, atualizações, rejeições, chaves excluídas ou remoções de válidos.
vendas_detalhadas: 44.939 linhas válidas, sem alterações.

Warehouse COMPLETED: aplicou publicação Silver nova, sem mudanças de negócio.
Zero inserções, atualizações, remoções ou dimensões marcadas ausentes.

| Tabela | Antes | Depois |
| --- | ---: | ---: |
| dim_cliente | 1.001 | 1.001 |
| dim_produto | 50 | 50 |
| dim_vendedor | 30 | 30 |
| dim_tempo | 366 | 366 |
| fato_vendas | 44.939 | 44.939 |

## Watermarks e versões

Watermark das seis tabelas:
- Antes: 2026-11-05T13:02:06.207654+00:00.
- Depois: 2026-11-05T16:37:40.143903+00:00.

Janela inicial: 2026-11-05T12:47:06.207654+00:00.
Watermarks avançaram após publicação bem-sucedida; nenhuma falha ocorreu.

- Silver anterior: 30f2e92e-d92e-4df9-b303-5e2e43e79bea.
- Silver nova: aea6f0b3-e61c-42d3-8695-bb77a4274310.
- Bronze nova: bronze/53a5e456-a90c-5447-974a-6b0a6e901192/fb0b60589b20437680178c62f9ce6651.
- Silver nova: silver/53a5e456-a90c-5447-974a-6b0a6e901192/aea6f0b3-e61c-42d3-8695-bb77a4274310.
- DW utiliza essa mesma versão Silver.
- Gold não possui versão independente: são views sobre o DW, vinculadas à Silver em dw_state.

## Reconciliação e preservação

| Indicador | Antes | Depois |
| --- | ---: | ---: |
| Pedidos faturados | 14.998 | 14.998 |
| Itens faturados | 44.939 | 44.939 |
| Receita líquida | R$ 14.420.828,23 | R$ 14.420.828,23 |
| Unidades | 473.781 | 473.781 |
| Ticket | R$ 961,52 | R$ 961,52 |

Resultados provenientes das consultas e validações, sem valores forçados.
Zero erros referenciais/financeiros, itens duplicados na fato ou produtos com estoque negativo.
Fingerprints e contagens das cinco tabelas analíticas iguais ao backup.
Hashes dos registros das seis tabelas públicas e valores das sequências públicas iguais antes/depois.
Histórico operacional, tabelas analíticas e arquivos históricos preservados.

## Idempotência e limites

A execução sem mudanças não inventou inserções/atualizações nem duplicou linhas.
Não foi realizada uma segunda execução com o mesmo run_id: a autorização foi para uma carga única.
Portanto confirma-se aqui o incremental sem alterações; não se declara um novo teste operacional de replay.
Retomada/replay permanecem cobertos pelos testes isolados anteriores.

Após o término: nenhum deployment registrado e nenhum flow RUNNING/PENDING/CANCELLING.
Enumeração de processos Windows por CIM foi negada no diagnóstico; a execução usou consultas Prefect,
auditoria e locks reais. Nenhuma colisão ou recuperação de backup foi necessária.

Não há transação distribuída: se uma execução futura publicar Silver e falhar no DW, retome o mesmo job;
não retroceda arbitrariamente o watermark de uma publicação válida.

## Resultado

Validação incremental ponta a ponta **APROVADA**: seis tasks Completed, auditoria e versões
reconciliadas, métricas estáveis e registros operacionais preservados.
Agendamento permanece desativado. Esta execução não autoriza novas cargas ou publicação GitHub.


Nota de publicação (Etapa 11.6): JSONs brutos de resultados/estados permanecem locais e ignorados pelo Git. Este resumo Markdown preserva as métricas e evidências públicas revisadas; referências a JSONs descrevem suporte local, não arquivos distribuídos.
