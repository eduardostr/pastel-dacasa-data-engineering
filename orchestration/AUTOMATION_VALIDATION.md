# Etapa 11.4 — Preparação e validação da operação automatizada

Data: 2026-11-05. Branch feat/prefect-orchestration.
A instrução desta etapa exige nova autorização antes de executar/reativar cargas persistentes.
Nenhuma carga persistente foi iniciada manualmente ou pelo teste desta etapa.

## Descoberta no diagnóstico

O cron principal estava ativo em 15h10, America/Sao_Paulo, com worker ONLINE.
**Uma carga automática já havia concluído antes deste diagnóstico**, sob autorização anterior:
- Run 01a1ace3-b6d7-7d6e-9092-cc451777545f, auto_scheduled=true.
- Agendado 2026-11-05T18:10:00Z (15h10 local).
- Início 18:10:04.947735Z; término 18:10:50.362502Z.
- Duração consultada no Prefect: 45.414767 s.

- Seis tasks COMPLETED, uma tentativa por task; zero retries.
- 125.856 registros examinados; zero extraídos, inseridos, atualizados, rejeitados ou excluídos.
- Silver publicada 043f9a42-0a8c-435a-b7ee-041373e2ea92 e DW atualizado/reconciliado.
- O flow não foi disparado ou repetido por esta etapa.

Às 18:12:29Z, foram pausados deployment, cron e pool principais por instrução da Etapa 11.4.
Estado anterior registrado: deployment paused=false, pool is_paused=false, schedule active=true.
Não havia carga em andamento para interromper. O worker existente não foi encerrado.

## Infraestrutura e agenda ao finalizar

- Prefect Server funcional: http://127.0.0.1:4200.
- Pool principal process: pastel-da-casa-local-pool, PAUSADO, limite 1.
- Deployment principal: pastel-da-casa-incremental-daily, PAUSADO.
- ID principal: 5bab29a2-ede7-4f76-ba66-07914c2722bd.
- Um único deployment com esse nome e um único cron: 10 15 * * *, America/Sao_Paulo.
- Schedule INATIVO; limite global do deployment 1.
- Parâmetros: incremental, dry_run=false, validate_only=false, allow_persistent=true, allow_full=false.
- Nenhum run principal Scheduled/Late/Pending/Running/Cancelling pendente ao conferir.
- Nenhuma próxima execução automática registrada enquanto pausado.
- Próxima ocorrência civil, se reativado antes dela: 06/11/2026 às 15h10 (18h10 UTC).
- Não há garantia de horário exato sem disponibilidade da infraestrutura; não foi instalado serviço Windows.

Workers observados na conferência final:
- pastel-local-worker: ONLINE; heartbeat 2026-11-05T18:25:24.132765Z.


PostgreSQL disponível por leitura e tabelas necessárias presentes.
DuckDB aberto read_only, reconciliado com Silver; diretórios de dados/control/warehouse acessíveis
e com permissão declarada de escrita. Não foi usado arquivo de teste nos destinos principais.
PREFECT_API_URL foi definida explicitamente nos comandos/processos; não houve alteração de perfil global.

## Backup consistente e estado inicial

Novo backup completo de snapshot, único e conferido:
backups/etapa11_4/20261105T181742Z_956ecfbe-3259-4802-a141-81369798f6a6/
Arquivos no backup: 186; espaço livre final: 231.39 GiB.

O snapshot copiou Bronze/Silver/quarentena/controles; SQLite pela API backup com integrity_check=ok;
DW sob conexão read_only sem WAL pendente e com hashes conferidos.
Backups anteriores foram preservados. A cópia de teste ficou em diretório temporário separado.
A nova referência difere legitimamente da Etapa 11.1 porque o run automático das 15h10 já ocorreu.

## Disparo automático seguro — evidência real

Deployment e pool separados: pastel-scheduling-probe-956ecfbe.
Deployment ID: 5ce6f0c2-3674-4d7f-8db7-597eed57a394.
Run: 01a1acee-6c66-7c4a-85e8-842a7337e0db.
ID lógico: 956ecfbe-3259-4802-a141-81369798f6a6.

O teste registrou intervalo de um dia ancorado num instante próximo, apenas para não esperar
o próximo dia. Não substituiu o cron principal e foi desativado ao finalizar.
Nenhuma chamada create_flow_run_from_deployment foi usada: o scheduler criou o run.
auto_scheduled=true confirmado; worker Process próprio submeteu a execução ao subprocesso.
Overrides: validate_only=true, dry_run=false, allow_persistent=false, allow_full=false.
Destinos apontavam ao snapshot temporário; PostgreSQL foi somente consultado.

- Horário esperado: 2026-11-05T18:18:28.575026Z.
- Início: 18:18:38.164063Z; fim: 18:18:41.319038Z.
- Duração: 3,154975 s; atraso observado de início: 9,589037 s (inclui startup do worker).
- Estado COMPLETED; worker retornou código 0; 14 registros de log localizados no Prefect.
- Nenhuma task ETL/warehouse foi chamada; somente as três verificações abaixo.

| Task segura | Estado | Duração | Tentativas |
| --- | --- | ---: | ---: |
| check_source-ec3 | COMPLETED | 2.110274 s | 1 |
| validate_gold-341 | COMPLETED | 0.598959 s | 1 |
| validate_silver-b37 | COMPLETED | 0.331485 s | 1 |


Após o teste: deployment temporário pausado, schedule inativo e pool temporário pausado.
O histórico/logs foram preservados no Prefect; o deployment principal não foi excluído.
O worker de teste encerrou normalmente. O worker principal segue disponível, porém seu pool está bloqueado.

## Integridade antes/depois do teste seguro

Silver e DW: 043f9a42-0a8c-435a-b7ee-041373e2ea92.
Watermarks das seis tabelas, antes e depois: 2026-11-05T18:10:09.446670+00:00.
DW run aplicado: 819c3324-226b-5186-8739-77f560d70ef0.

| Indicador | Antes | Depois |
| --- | ---: | ---: |
| Pedidos faturados | 14.998 | 14.998 |
| Itens faturados | 44.939 | 44.939 |
| Receita | R$ 14.420.828,23 | R$ 14.420.828,23 |
| Unidades | 473.781 | 473.781 |
| Ticket | R$ 961,52 | R$ 961,52 |

Contagens: 1.001 clientes, 50 produtos, 30 vendedores, 366 datas e 44.939 itens na fato.
SHA-256 de todos os arquivos de dados principais, exceto locks, iguais antes/depois.
Hashes dos registros das seis tabelas públicas e valores das sequências iguais.
Dados do backup/DW atual, contagens, Gold e dw_state idênticos. Zero duplicações de id_item.
Nenhum avanço de watermark, escrita no DW ou publicação de datasets pelo teste seguro.

## Regressão e limites

15 testes existentes de configuração/worker foram executados novamente: todos aprovados,
zero falhas, em 35.644 s.

A suíte completa de 153 pertence à Etapa 11.3 e não foi declarada como reexecutada nesta etapa.
A prova operacional de scheduling é adicional, com scheduler/worker reais e logs.
Não houve queda forçada de processo ou restauração de backup.
Se o processo do probe for morto antes do finally, verifique/pause seu pool e schedule;
seus parâmetros continuam sendo somente validate-only.

## Plano de próxima ativação — ainda NÃO autorizado

Depois de confirmar novamente backups, worker ONLINE e ausência de jobs principais pendentes:
1. Liberar apenas o pool principal.
2. Reativar somente o cron principal 10 15 * * *, America/Sao_Paulo.
3. Aguardar a próxima ocorrência futura; não executar compensação manual de hoje.
4. Monitorar as seis tasks e conferir métricas, versões, watermarks e Gold.

Comandos preparados, **não executados**:

```powershell
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
$env:PREFECT_HOME = (Join-Path (Get-Location) ".prefect")
.\.venv314\Scripts\prefect.exe work-pool resume pastel-da-casa-local-pool
.\.venv314\Scripts\python.exe -m orchestration.operations schedule resume --authorize-recurring
```

A ativação autorizará escritas futuras em Bronze/Silver, controles/watermarks, auditorias e DuckDB.
Não autoriza alterar registros comerciais, gerar dados sintéticos, rodar FULL ou cargas manuais extras.
Retries de task reutilizam IDs do mesmo flow. Para retomar exatamente um job após falha, capture o ID lógico
no relatório e use-o explicitamente; um Retry de flow com run_id ausente não deve ser presumido replay
do mesmo ID lógico. Não existe rollback distribuído de Silver + DW.

Computador ligado/sem suspensão, Docker/PostgreSQL, Prefect Server e worker precisam estar disponíveis.
Se houver Scheduled/Late/Pending/Running antes da liberação, diagnosticar e revisar o plano;
não cancelar nem executar pendências automaticamente.

## Arquivos e estado Git

Criados: orchestration/scheduling_probe.py, orchestration/AUTOMATION_VALIDATION.md
e orchestration/AUTOMATION_RESULTS.json.
Atualizados: guias operacionais para 15h10 e instrução de retomada do pool.
Não houve commit, push, merge, serviço permanente ou mudança de regras/ETL/warehouse.
O agendamento principal permanece PAUSADO aguardando nova confirmação.


Nota de publicação (Etapa 11.6): JSONs brutos de resultados/estados permanecem locais e ignorados pelo Git. Este resumo Markdown preserva as métricas e evidências públicas revisadas; referências a JSONs descrevem suporte local, não arquivos distribuídos.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../docs/VALIDATION.md.
