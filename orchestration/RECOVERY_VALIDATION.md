# Etapa 11.2 — Resultado de idempotência e recuperação

Data: 2026-11-05. Branch: feat/prefect-orchestration.
**11 testes novos; 138 testes aprovados, zero falhas/erros/skips.**
Pytest também informou 33 subtests aprovados provenientes das suítes unittest existentes;
o JUnit soma 171 itens. Não foram contados como 171 testes independentes.
Tempo completo: **275,462 s**. Pytest 9.2.0, Prefect 3.9.1, Python 3.14.

## Diagnóstico e snapshot

Silver atual: aea6f0b3-e61c-42d3-8695-bb77a4274310.
DW run aplicado: 0a23e4e5-d21f-5f82-ac0c-9711a29454a3.
Watermarks das seis tabelas: 2026-11-05T16:37:40.143903+00:00.
Referência Gold: 14.998 pedidos, 44.939 itens, R$ 14.420.828,23, 473.781 unidades e ticket R$ 961,52.
Dimensões: 1.001 clientes, 50 produtos, 30 vendedores e 366 datas.

Antes dos testes, não havia flow principal RUNNING/PENDING/CANCELLING.
Foi criada uma cópia temporária consistente: datasets e controles, SQLite via API backup com
integrity_check=ok e DuckDB copiado sob conexão read_only, sem WAL pendente.
Essa cópia permaneceu como snapshot de referência; cada teste usou outra cópia ou fixture própria.
Nenhum backup anterior foi excluído.

## Cenários efetivamente executados

| Cenário | Esperado | Observado | Status | Evidência automatizada | Tempo |
| --- | --- | --- | --- | --- | ---: |
| Replay com mesmo ID | REUSED real, sem novos datasets ou mudanças | Dois Prefect IDs distintos; ETL/DW IDs fixos, estado e hashes iguais | PASSED | test_recovery.py::test_real_replay_same_logical_id_new_prefect_runs | 15.645 s |
| Falha transitória recuperável | Três tentativas, conclusão sem duplicação | Duas falhas de conexão injetadas, terceira tentativa concluiu | PASSED | test_recovery.py::test_transient_retry_recovers_without_duplication | 2.942 s |
| Indisponibilidade persistente | Parar após três tentativas | Failed após três chamadas; estado anterior preservado | PASSED | test_recovery.py::test_transient_retry_stops_at_three | 1.972 s |
| Candidato inválido | Failed e DW bloqueado | Parquet inválido em caminho temporário; DW não chamado; publicação preservada | PASSED | test_recovery.py::test_invalid_candidate_is_permanent_and_stops_dw | 1.986 s |
| Extração → Bronze | Sem publicação parcial; retomar mesmo job | Falha de rename antes da publicação; Failed → Completed | PASSED | test_recovery.py::test_flow_publication_failure_and_same_job_recovery[bronze_move] | 13.316 s |
| Transformação → Silver | Manter pointer/watermarks; reutilizar Bronze | before_publish falhou; versão anterior preservada; recuperação sem duplicar Bronze | PASSED | test_recovery.py::test_flow_publication_failure_and_same_job_recovery[silver_publish] | 11.269 s |
| Silver → DW | Preservar Silver confirmada e DW anterior | Failed antes de DW; replay aplica Silver já confirmada | PASSED | test_recovery.py::test_flow_publication_failure_and_same_job_recovery[before_dw] | 11.142 s |
| DW antes do commit | Rollback DW; retomada segura | DW anterior intacto; retry manual do mesmo job confirma | PASSED | test_recovery.py::test_flow_publication_failure_and_same_job_recovery[dw_before_commit] | 11.110 s |
| DW após commit | Preservar commit e reconciliar auditoria | Auditoria pendente recuperada via REUSED | PASSED | test_recovery.py::test_flow_publication_failure_and_same_job_recovery[dw_after_commit] | 11.199 s |
| Gold → auditoria final | Não desfazer dados válidos | Flow Failed com dados confirmados; replay concluiu auditoria sem novas versões | PASSED | test_recovery.py::test_flow_publication_failure_and_same_job_recovery[final_audit] | 11.108 s |
| Concorrência FULL/INCREMENTAL | Segundo flow bloqueado | Incremental concluído, FULL incompatível Failed; hashes/versões preservados | PASSED | test_recovery.py::test_concurrent_full_and_incremental_are_excluded | 3.974 s |


Tempos por cenário são do JUnit, incluindo setup/teardown de fixture; o primeiro inclui inicialização do servidor.
Os hooks/falhas são injetados em testes. Não foram expostos novos parâmetros de falha à produção.
Evidências e métricas sanitizadas estão em RECOVERY_RESULTS.json.
O relatório registra testes Failed deliberados como resultados esperados, não falhas da suíte.

## Replay real da Etapa 11.1

Identificador lógico repetido: d6cb127a-1507-4835-8bbd-0e3b79cf62f7.
ETL ID fixo: 53a5e456-a90c-5447-974a-6b0a6e901192.
DW ID fixo: 0a23e4e5-d21f-5f82-ac0c-9711a29454a3.

Dois Prefect flow runs novos, ambos Completed no servidor temporário:
- 5629ab15-2a15-4519-9eba-bcf10e696dc9
- 0695a89f-9700-432d-b81a-b0dcd2b4e2b5

As duas chamadas usaram o mesmo ID lógico e as rotas reais REUSED de ETL/DW.
A extração foi instrumentada para falhar caso fosse chamada: não foi chamada.
Arquivos Bronze/Silver, watermarks, versões, tabelas dimensionais/fato e Gold ficaram iguais
por contagens e hashes. Nenhuma duplicação. As auditorias de tentativas crescem legitimamente.

## Componentes reais versus mocks

- Replay: cópia dos componentes concluídos reais, Pipeline/Warehouse reais e motor Prefect real;
  a verificação de conectividade é simulada, e nova extração é explicitamente proibida no teste.
- Retries: conexão simulada no adaptador; callback/classificador e política do Prefect são reais.
- Permanente: candidato Parquet inválido em caminho temporário injetado no leitor; publicação oficial não adulterada.
- Fronteiras de publicação: PostgreSQL em schema temporário, ETL, Parquet, SQLite, DuckDB e Prefect reais;
  falhas injetadas por hooks existentes e mocks de rename/adaptador/finalização.
- Concorrência: dois flows reais, mesma cópia de destinos; incremental mantém guard e FULL é bloqueado.
- Suíte completa: testes anteriores reutilizados, não reimplementados; backend/frontend integrado
  redirecionados para schema temporário antes das importações.
- Nenhum servidor PostgreSQL real foi derrubado nem indisponibilizado.

## Rollback e watermarks

Antes do commit Silver: pointer e watermarks anteriores preservados.
Depois do commit Silver: nova Silver permanece válida; uma falha posterior no DW não a desfaz.
Antes do commit DW: rollback conserva DW anterior.
Após commit DW ou falha de auditoria final: preserva-se o commit e retoma-se a confirmação.
Todos os seis cenários de fronteira terminaram recuperados com o mesmo job e novos Prefect run IDs.

Isso confirma recuperação por fronteira, não atomicidade distribuída entre Parquet e DuckDB.
Diretórios intermediários podem permanecer sem serem publicados; o manifesto define a versão oficial.
Interrupção abrupta do SO/queda de energia não foi simulada: foram injetadas exceções controladas.

## Ambiente principal preservado

Comparação antes/depois da suíte:
- 108 arquivos protegidos, incluindo DW, manifesto, SQLite e históricos: SHA-256 iguais.
- Registros das seis tabelas públicas e valores das sequências: iguais.
- Silver principal e watermarks permaneceram nos valores do diagnóstico.
- Gold principal permaneceu nas referências acima.
- Sem cargas principais, dados sintéticos novos no CRM, agendamento, commit, push ou merge.
- Locks do SO são locais; não se conclui segurança distribuída entre hosts/OneDrive.

## Arquivos

Criados: orchestration/tests/test_recovery.py, orchestration/tests/prepare_snapshot.py,
orchestration/requirements-dev.txt, orchestration/RECOVERY.md,
orchestration/RECOVERY_VALIDATION.md e orchestration/RECOVERY_RESULTS.json.
Atualizado: orchestration/README.md para navegação.
Não foi necessária alteração de lógica dos flows/tasks, ETL, DW ou regras comerciais.

O utilitário prepare_snapshot foi executado e validado para uma nova pasta temporária.
A primeira rodada dos 11 cenários passou; seu wrapper teve erro de decodificação apenas ao imprimir o log.
A suíte completa posterior exportou JUnit e confirmou os 138 testes sem falhas.
Essa limitação do wrapper não foi confundida com falha do pipeline.

## Conclusão

Etapa 11.2 **APROVADA** para os cenários executados.
Veja RECOVERY.md para preparação reproduzível de snapshot, execução, recuperação e limites.


Nota de publicação (Etapa 11.6): JSONs brutos de resultados/estados permanecem locais e ignorados pelo Git. Este resumo Markdown preserva as métricas e evidências públicas revisadas; referências a JSONs descrevem suporte local, não arquivos distribuídos.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../docs/VALIDATION.md.
