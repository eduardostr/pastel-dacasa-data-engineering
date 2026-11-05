# Etapa 11.5 — Primeira execução automática comprovada

Resultado: **APROVADO**. Auditoria retrospectiva realizada em 05/11/2026.
Foi utilizada uma execução automática já concluída, conforme permitido pelo prompt.
Não se aguardou ficticiamente 06/11, não se disparou outra carga nem se modificou o cron.

## Evidência de origem e recebimento

- Flow run ID: 01a1ace3-b6d7-7d6e-9092-cc451777545f.
- Flow: pastel-da-casa-data-pipeline.
- Deployment: pastel-da-casa-incremental-daily.
- Deployment ID: 5bab29a2-ede7-4f76-ba66-07914c2722bd.
- auto_scheduled=true nos metadados do Prefect.
- Pool: pastel-da-casa-local-pool; worker pastel-local-worker.
- PID de infraestrutura: 18972.
- Log 2026-11-05T18:09:58.874129Z:
  Worker 'pastel-local-worker' submitting flow run '01a1ace3-b6d7-7d6e-9092-cc451777545f'.
- Parâmetros efetivos: incremental, dry_run=false, validate_only=false, allow_persistent=true, allow_full=false.
- Estado final: COMPLETED.
- 23 registros de log encontrados, incluindo submissão, seis pares de eventos de tasks e conclusão.

Essa é uma carga persistente real autorizada anteriormente, não o teste separado validate-only da Etapa 11.4.
O contexto de que a primeira execução ainda não estava comprovada foi resolvido pela auditoria desses registros.

## Horários e tasks

Horário agendado: **05/11/2026 às 15h10**, America/Sao_Paulo (18h10 UTC).
Início efetivo: 15:10:04,947735; término: 15:10:50,362502.
Duração Prefect: **45,414767 s**. Atraso de início: 4,947735 s.
Duração do processamento registrada na auditoria do flow: 45,343 s.

| Task | Estado | Duração Prefect | Tentativas | Retries |
| --- | --- | ---: | ---: | ---: |
| check_source-afa | COMPLETED | 2.127240 s | 1 | 0 |
| run_etl-162 | COMPLETED | 41.473003 s | 1 | 0 |
| validate_silver-8b9 | COMPLETED | 0.349494 s | 1 | 0 |
| run_warehouse-7fc | COMPLETED | 0.752366 s | 1 | 0 |
| validate_gold-3b1 | COMPLETED | 0.551032 s | 1 | 0 |
| finalize-019 | COMPLETED | 0.011256 s | 1 | 0 |


Os horários individuais, IDs e eventos de log relevantes estão em FIRST_AUTOMATIC_RUN.json.
Nenhuma task Failed, nenhum retry e nenhuma mensagem de erro de processamento.
Os logs e a timeline continuam acessíveis na UI do Prefect pelo flow run ID acima.

## Estado anterior: origem da comparação

O estado anterior não foi inventado nem capturado retroativamente como se fosse uma observação ao vivo.
Foi usado o snapshot consistente preservado na Etapa 11.2, com a mesma versão
identificada em previous_version do manifesto atual.
As versões históricas de manifesto e os registros de carga DW corroboram a comparação.
O snapshot anterior e seus hashes/contagens foram consultados somente por leitura.

| Campo | Antes | Depois |
| --- | --- | --- |
| Silver | aea6f0b3-e61c-42d3-8695-bb77a4274310 | 043f9a42-0a8c-435a-b7ee-041373e2ea92 |
| DW run aplicado | 0a23e4e5-d21f-5f82-ac0c-9711a29454a3 | 819c3324-226b-5186-8739-77f560d70ef0 |
| Watermark das seis tabelas | 2026-11-05T16:37:40.143903+00:00 | 2026-11-05T18:10:09.446670+00:00 |
| Arquivos históricos Bronze/Silver/quarentena | 105 | 126 |

Os 105 arquivos anteriores continuam presentes e com SHA-256 idêntico.
Os 21 arquivos adicionais são da nova versão de extração/publicação, não duplicações na visão corrente.
Os hashes e contagens das cinco tabelas analíticas são iguais entre o snapshot anterior e o DW atual;
somente controle/publicação/auditoria evoluíram como esperado.

## Processamento incremental

- ID lógico: 69cf9232-e72e-424d-a862-a8000b11ff63.
- ETL run ID: 1e808e67-66f3-5818-8818-3521d1c2a93c.
- DW run ID: 819c3324-226b-5186-8739-77f560d70ef0.
- Registros examinados nas seis tabelas: **125.856**.
- Registros extraídos: **0**.
- Inseridos, atualizados, rejeitados e excluídos: **0**.
- vendas_detalhadas: 44.939 linhas válidas; sem inserções/atualizações/remoções.
- Auditoria ETL: COMPLETED; DW: COMPLETED.
- DW processou 1.001 clientes, 50 produtos, 30 vendedores, 366 datas e 44.939 itens sem mutações.
- Nova Silver publicada e validada; dw_state usa exatamente sua versão.
- Watermarks avançaram após o commit bem-sucedido, sem inventar mudanças na origem.

Não haver inserções/atualizações é resultado válido da reconciliação sem alterações.

## Indicadores e integridade

| Indicador | Antes | Depois |
| --- | ---: | ---: |
| Clientes no DW | 1.001 | 1.001 |
| Produtos no DW | 50 | 50 |
| Vendedores no DW | 30 | 30 |
| Datas | 366 | 366 |
| Itens faturados / fato | 44.939 | 44.939 |
| Pedidos faturados | 14.998 | 14.998 |
| Receita líquida | R$ 14.420.828,23 | R$ 14.420.828,23 |
| Unidades | 473.781 | 473.781 |
| Ticket médio | R$ 961,52 | R$ 961,52 |

As referências financeiras foram comparadas, não forçadas.
A revalidação atual usou validate_source/validate_target já existentes via funções das tasks,
com PostgreSQL/DuckDB somente leitura e tabelas apenas TEMP na conexão DuckDB.
Isso não criou flow run nem executou extração ou carga adicional.
Zero erros referenciais e financeiros, zero duplicações por chave nas dimensões/fato e zero estoque negativo.
O hash de todos os arquivos de dados principais não-lock permaneceu igual antes/depois desta auditoria.

## Backups e configuração atual

Backup consistente existente:
backups/etapa11_4/20261105T181742Z_956ecfbe-3259-4802-a141-81369798f6a6/

Backup confirmado presente e SHA-256 de model.duckdb igual ao DW atual.
Não houve restauração, novo dump ou exclusão de backup.

Na verificação final:
- Server disponível, worker ONLINE.
- Pool Process READY e liberado, limite 1.
- Deployment READY e ativo, limite global efetivo 1.
- Um único cron 10 15 * * *, America/Sao_Paulo, ativo.
- Nenhuma execução duplicada para o mesmo horário/deployment.
- Nenhum run Pending/Running/Late/Failed no deployment principal.
- Três ocorrências futuras Scheduled, em 06, 07 e 08/11, às 15h10 locais.
- Próxima: **06/11/2026 às 15h10**.
- Os nomes provisórios aleatórios de runs Scheduled são normais; são renomeados no início do flow.
- O teste temporário da Etapa 11.4 não foi confundido com o deployment principal.

O agendamento foi preservado ativo conforme a última autorização; não foi pausado ou reconfigurado nesta etapa.

## Monitoramento e operação

O monitor agora apresenta auto_scheduled, expected_start_time, deployment_id e infrastructure_pid,
além dos estados, horários e tentativas já disponíveis.

```powershell
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
.\.venv314\Scripts\python.exe -m orchestration.monitor --limit 25
.\.venv314\Scripts\python.exe -m orchestration.monitor --alerts --limit 25
```

Para manter a automação, deixar computador ligado/sem suspensão, Docker/PostgreSQL, servidor Prefect e worker disponíveis.
Um run Late/Failed deve ser diagnosticado sem criar uma compensação manual automaticamente.
O flow tem zero retries integrais; tasks elegíveis possuem até três tentativas transitórias.
Para replay exato após diagnóstico/autorização, utilizar o ID lógico registrado, não presumir que
um run novo ou Retry com run_id ausente representa o mesmo processamento lógico.

## Verificações e Git

Um teste existente do monitor foi ampliado e reexecutado: 1 aprovado, 14 desse arquivo não selecionados.
A suíte completa de 153 é evidência da Etapa 11.3, não foi declarada como reexecutada aqui.
Os validadores reais de dados foram executados por leitura e passaram.
Nenhuma nova carga, alteração do CRM, geração sintética, serviço, mudança de branch ou operação no Git remoto.

Criados: orchestration/FIRST_AUTOMATIC_RUN.md e orchestration/FIRST_AUTOMATIC_RUN.json.
Modificados: orchestration/monitor.py, teste existente de sanitização, README.md,
orchestration/README.md e orchestration/WORKER.md para apontar a validação atual.
Branch continua feat/prefect-orchestration; sem commit/push/merge.

## Conclusão

Etapa 11.5 **APROVADA** pela execução automática real existente.
Origem Scheduler, recepção Worker, seis tasks Completed, auditoria, publicação e integridade comprovadas.
Nenhuma segunda execução foi iniciada para compensar ou reproduzir a carga.


Nota de publicação (Etapa 11.6): JSONs brutos de resultados/estados permanecem locais e ignorados pelo Git. Este resumo Markdown preserva as métricas e evidências públicas revisadas; referências a JSONs descrevem suporte local, não arquivos distribuídos.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../docs/VALIDATION.md.
