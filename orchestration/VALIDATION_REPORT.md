# Validação — Prefect / Etapa 11

Data: 2026-11-05. Prefect instalado: **3.9.1**. Python existente: 3.14.
Nenhum deployment foi registrado, cron ativado ou flow persistente de desenvolvimento executado.
Não houve commit/push nesta etapa; autorização anterior foi usada somente para a publicação inicial.

## Implementação

Criados:
- orchestration/__init__.py
- orchestration/config/__init__.py
- orchestration/tasks/__init__.py
- orchestration/tasks/pipeline.py
- orchestration/flows/__init__.py
- orchestration/flows/pipeline.py
- orchestration/__main__.py
- orchestration/deployment.py
- orchestration/requirements.txt
- orchestration/tests/test_orchestration.py
- orchestration/README.md
- orchestration/VALIDATION_REPORT.md

Modificados: requirements.txt (agregador), .gitignore (.prefect/), README.md e docs/architecture.md.
ETL, API, SQL, Docker Compose, .env e warehouse existentes não foram alterados.

Flow pastel-da-casa-data-pipeline: origem → ETL → Silver → warehouse → Gold → relatório.
Modo incremental padrão; FULL com guarda extra; dry-run offline; validate-only sem cargas.
Retentativas seletivas até três tentativas totais; falhas permanentes interrompem o pipeline.
Locks reais por destino e locks dos componentes preservados; versão/fingerprint fixados e rechecados.
IDs determinísticos de ETL/DW para o mesmo run_id lógico, auditados junto do prefect_run_id.

## Testes executados nesta etapa

| Suíte | Quantidade | Resultado | Tempo unittest |
| --- | ---: | --- | ---: |
| Orquestração, incluindo runtime real | 17 | OK | 20,426 s |
| Backend em schema isolado | 23 | OK | 5,204 s |
| Frontend completo, integração isolada | 27 | OK | 13,823 s |
| Gerador sintético isolado | 9 | OK | 6,322 s |
| ETL isolada | 26 | OK | 119,903 s |
| Warehouse temporário | 25 | OK | 12,813 s |
| **Total** | **127** | **Sem falhas** | — |

Os 17 testes finais foram executados com PASTEL_TEST_PREFECT_RUNTIME=1, sem skips.
O harness iniciou e encerrou um servidor temporário. Verificou:
- flow registrado e executado no motor Prefect;
- três tentativas reais para falha transitória;
- uma única tentativa real para falha permanente;
- caminho Silver → warehouse → Gold e finalização com tasks reais e arquivos temporários;
- origem/ETL simuladas apenas nesse teste do runtime; PostgreSQL real coberto pelas suítes isoladas;
- ordem, modo FULL/incremental, dry-run sem arquivos/chamadas e validate-only sem cargas;
- falha Silver impedindo DW, versão divergente, lock concorrente e sanitização de erros.

Os testes com backend/frontend usaram o helper existente com engine redirecionada antes das importações;
não consumiram fixtures nem sequências do schema public.
O Prefect resolveu FastAPI 0.150.0 e websockets 16.1.1 no ambiente. Regressões acima passaram após a instalação.
pip check: sem conflitos. Não é uma validação de todas as combinações futuras de versões.

## Verificações adicionais

1. CLI --dry-run: plano sem conexão, import do runtime ou publicação.
2. CLI de deployment sem --serve: somente JSON de configuração.
3. Construção offline real via flow.to_deployment: daily-incremental, paused=True,
   schedule active=False, cron 0 2 * * *, America/Sao_Paulo; nenhum apply/registro.
4. .prefect/test.db é ignorado pelo Git.
5. Validate-only executado contra dados existentes, por tasks .fn com logger de leitura (sem flow persistente):
   - versão Silver 30f2e92e-d92e-4df9-b303-5e2e43e79bea;
   - 44.939 itens, 14.998 pedidos, R$ 14.420.828,23;
   - zero erros referenciais e financeiros;
   - SHA-256 do DW e current.json iguais antes/depois.
6. Servidor permanente não iniciado; nenhuma configuração global Prefect foi gravada.
7. Aviso de permissão em memo_store temporário apareceu no primeiro harness; não impediu os testes.
8. Não foram capturadas telas de uma UI permanente nem verificados dias de execução agendada.

## Recuperação e limites

Não há transação distribuída Parquet + DuckDB. Se ETL falhar antes de publicar, seu watermark não avança.
Se ETL concluir e DW falhar depois, a Silver válida permanece publicada; retome o mesmo job para atualizar DW.
Não se retrocede artificialmente um watermark já confirmado.

Locks são locais ao sistema operacional; não garantem coordenação entre hosts ou sincronizadores.
Colisão do guard falha imediatamente. Processo encerrado libera locks do SO; não apague arquivos ativos.
Interrupção forçada pode impedir finalize: consulte estados Prefect e controles internos.
Relatórios por tentativa e último estado são locais em data/orchestration/runs/ e ignorados.

O anexo recebido termina em “10. Bloqueio de”. A implementação cobre o escopo disponível;
nenhum requisito ausente foi interpretado como autorização para ativar agenda ou executar cargas.

## Próximos passos dependentes de decisão

Iniciar servidor local e usar validate-only para acompanhar a UI conforme README.
Registro pausado do deployment e ativação recorrente são ações distintas; não foram realizadas.
Cargas persistentes requerem autorização explícita. Nenhum conteúdo desta etapa foi enviado ao GitHub.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../docs/VALIDATION.md.
