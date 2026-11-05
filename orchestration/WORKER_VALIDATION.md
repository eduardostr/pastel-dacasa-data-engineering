# Etapa 11.3 — Validação de worker, cron e monitoramento

Data: 2026-11-05. Branch: feat/prefect-orchestration.
Prefect 3.9.1; Python 3.14.10; pytest 9.2.0.
Nenhum commit, push, merge, serviço Windows, carga FULL/incremental ou ativação de agenda nesta etapa.
Foram gravados apenas configuração/metadados do Prefect e documentação/código solicitados.

## Infraestrutura registrada

- Prefect Server: disponível em http://127.0.0.1:4200 (API /api).
- Pool: pastel-da-casa-local-pool, tipo process, concorrência 1.
- Worker: pastel-local-worker, usando executável do venv, cwd e módulos do checkout.
- Deployment: pastel-da-casa-data-pipeline/pastel-da-casa-incremental-daily.
- Deployment ID: 5bab29a2-ede7-4f76-ba66-07914c2722bd.
- Limite efetivo do deployment: global_concurrency_limit.limit=1, ativo, zero slots ocupados ao conferir.
  O campo legado concurrency_limit da resposta API é null; não foi confundido com ausência de limite.
- Parâmetros padrão: incremental, dry_run=false, validate_only=false, allow_persistent=true, allow_full=false.
  Esses defaults preparam cargas futuras autorizadas; não foram utilizados para gravar dados nesta etapa.

Worker iniciado para o teste, processou o run e saiu com código 0.
**O worker não permanece em execução após o teste**; monitor registra OFFLINE após expirar heartbeat.
Para mantê-lo online, iniciar o comando worker em PowerShell dedicado, conforme WORKER.md.
Não foi instalado processo permanente de inicialização automática.

## Agendamento

Único schedule: cron 0 2 * * *, America/Sao_Paulo, slug daily-incremental.
Deployment paused=true e schedule active=false, conferidos pela API após os testes.
Não há próxima execução automática prevista enquanto inativo.
Um único run associado ao deployment foi encontrado: manual, auto_scheduled=false.
Nenhum disparo automático.

Timezone calculado com o scheduler do Prefect:
- 2017-11-05 02h00 local = 04h00 UTC (offset histórico -02).
- 2026-11-05 02h00 local = 05h00 UTC (offset -03).
Isso verifica o uso de IANA/DST em vez de fixar um offset UTC.

## Teste real no servidor local

Run: ae5a939c-e41f-48ca-830f-cfed269292f3.
ID lógico: ff78d4e7-e586-49be-a18f-6a6a59c4b9ac.
Execução através do Process Worker, subprocesso de infraestrutura PID 5184.
Overrides seguros: validate_only=true, dry_run=false, allow_persistent=false, allow_full=false.
Estado final COMPLETED, início 17:27:40.000550Z e fim 17:27:43.075576Z.
Duração: **3,075026 s**.

| Task | Estado | Duração | Tentativas |
| --- | --- | ---: | ---: |
| check_source-fb2 | COMPLETED | 2.110279 s | 1 |
| validate_gold-9d5 | COMPLETED | 0.534002 s | 1 |
| validate_silver-81f | COMPLETED | 0.320828 s | 1 |


Logs de submissão, carregamento do código, início/fim de flow e tasks foram capturados e vistos no Prefect.
O run seguro foi realizado antes do ajuste cosmético de nomes. Novos runs seguem
pastel-<ambiente>-<modo>-<prefixo-do-id>. O flow lógico e o processamento não mudaram.

## Teste de parada e reinicialização isolado

Servidor Prefect temporário e dois processos de worker reais, sem cargas:
- Primeiro processo consumiu dry-run e terminou normalmente.
- Segundo run foi criado com worker parado: Scheduled e sem start_time.
- Novo processo reconheceu o mesmo deployment e concluiu esse run.
- Primeiro histórico continuou Completed.
- Schedule continuou único, pausado e inativo.

Evidência:
- Primeiro run: d7fbea79-72b9-4c53-bc5f-21dbfea956aa, PID de infraestrutura 5036.
- Segundo run: fe2e3b84-84a4-413c-9aa5-ced9864f428f, PID de infraestrutura 17780.


Não foi simulado desligamento forçado durante escrita ou queda de energia.
Comportamento de jobs pendentes/running e procedimento manual de recuperação constam em WORKER.md.
Não foi interrompido PostgreSQL.

## Testes automatizados

**15 novos + 138 existentes = 153 aprovados**, zero falhas/erros/skips.
Há ainda 33 subtests unittest aprovados; o JUnit os agrega ao total de itens, sem inflar o total de testes independentes.
Tempo da suíte completa:
**306.128 s**.

| Teste novo | Resultado | Tempo JUnit |
| --- | --- | ---: |
| test_deployment_contract | PASSED | 0.003 s |
| test_reject_nonlocal_or_credential_urls[negative-case-1] | PASSED | 0.002 s |
| test_reject_nonlocal_or_credential_urls[negative-case-2] | PASSED | 0.002 s |
| test_reject_nonlocal_or_credential_urls[negative-case-3] | PASSED | 0.002 s |
| test_reject_nonlocal_or_credential_urls[negative-case-4] | PASSED | 0.002 s |
| test_worker_virtualenv_and_limits | PASSED | 0.002 s |
| test_worker_environment_excludes_credentials | PASSED | 0.002 s |
| test_schedule_activation_guard | PASSED | 0.002 s |
| test_alert_sanitization_and_attempts | PASSED | 0.003 s |
| test_offline_deployment_build | PASSED | 0.078 s |
| test_safe_kind_guard | PASSED | 0.002 s |
| test_registration_idempotent_no_schedule_dispatched | PASSED | 11.473 s |
| test_existing_pool_type_not_replaced | PASSED | 0.052 s |
| test_worker_restart_pending_run_and_history | PASSED | 18.943 s |
| test_pause_is_safe_and_no_notifications | PASSED | 0.063 s |


Configuração, cron/timezone, guards, ambiente sem credenciais, sanitização e limites foram testados por unidade.
Registro duas vezes, preservação de pool de outro tipo, pausa e worker/reinicialização usaram servidor real isolado.
Mocks de alertas são identificados no teste; nenhum canal externo foi configurado.
A suíte completa reutilizou os testes de concorrência FULL/incremental, locks, retries e recuperação existentes.
Os testes com PostgreSQL usaram schemas temporários; nenhum registro público ou sequência de CRM foi usado como fixture.

## Segurança e monitoramento

- Hashes dos arquivos de dados principais iguais antes/depois da validação via worker e da suíte completa.
- Hashes dos registros das seis tabelas públicas e valores de sequências iguais.
- Sem novas publicações Bronze/Silver/DW no ambiente principal.
- .env, credenciais e regras comerciais preservados.
- .prefect/ e *.log já estavam ignorados; não foi necessária nova regra.
- Testes negativos contêm valores demonstrativos para URLs inválidas; não são credenciais reais.
  As evidências publicáveis não copiam esses valores de parâmetros.
- Monitor local consultado contra o servidor: pool/deployment corretos, worker parado identificado,
  sem alertas de flow no filtro. Estado do servidor não foi confundido com estado do worker.
- Alerts mostra Failed/Crashed/Cancelled, task, tentativas e duração; não replica mensagens arbitrárias
  nem envia e-mail, WhatsApp, webhook ou serviço pago.

## Arquivos

Criados: orchestration/operations.py, orchestration/monitor.py,
orchestration/tests/test_operations.py, orchestration/WORKER.md,
orchestration/WORKER_VALIDATION.md e orchestration/WORKER_RESULTS.json.
Modificados nesta etapa: orchestration/flows/pipeline.py (somente nome de run),
orchestration/README.md, README.md e docs/architecture.md.
Outras alterações locais da Etapa 11 já estavam pendentes; não foram commitadas.

CLI antiga deployment --serve preservada. ETL, warehouse, SQL e dados operacionais não foram alterados.

## Próximos comandos e limites

O guia WORKER.md contém os comandos reais para:
- iniciar servidor, registrar pool/deployment pausado e iniciar worker;
- criar run seguro e consultar monitor/alertas;
- reiniciar worker e interromper por Ctrl+C;
- pausar futuras programações;
- habilitar cron apenas com autorização explícita e --authorize-recurring.

Nenhuma ativação foi executada. Pausa de schedule não cancela jobs já enfileirados.
Máquina, servidor, banco e worker precisam permanecer disponíveis para automação futura.
Não há garantia de retomada automática de um processo Python morto nem coordenação entre hosts.

Resultado: infraestrutura preparada e teste seguro aprovado; **agendamento permanece desativado**.


Nota de publicação (Etapa 11.6): JSONs brutos de resultados/estados permanecem locais e ignorados pelo Git. Este resumo Markdown preserva as métricas e evidências públicas revisadas; referências a JSONs descrevem suporte local, não arquivos distribuídos.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../docs/VALIDATION.md.
