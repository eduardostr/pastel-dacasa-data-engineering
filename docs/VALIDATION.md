# Validação técnica

Última suíte completa registrada no ambiente local em 2026-11-05: **160 testes e 33 subtestes aprovados em 300,07 s**, sem falhas, erros ou testes pulados. Um aviso PytestAssertRewriteWarning sobre anyio já importado foi documentado; não afetou os resultados. A suíte foi executada no checkout limpo destinado a este repositório, com configuração sensível fornecida somente ao ambiente do processo. Não são resultados de GitHub Actions nem benchmark de produção.

Cobertura: backend CRUD/vendas/configuração, frontend operacional/analítico, geração sintética, snapshot e tipos, qualidade/quarentena, Bronze/Silver, dimensões/fato/Gold, Prefect, contrato de scheduling, idempotência, retries, recuperação e exclusão de concorrência. A suíte usa schemas PostgreSQL e arquivos/servidor Prefect temporários. As verificações confirmaram preservação dos dados e sequências principais e do `.env`.

```powershell
.\.venv314\Scripts\python.exe -m pip install -r orchestration/requirements-dev.txt
.\.venv314\Scripts\python.exe -B -m orchestration.tests.run_suite
```

Requer instalação das dependências principais, PostgreSQL acessível, configuração local válida e permissão CREATE SCHEMA. O runner cria baseline FULL apenas em destinos descartáveis. Não é necessário receber os datasets privados da demonstração.

## Demonstração histórica sintética

A base local atingiu 20.000 pedidos. Reconciliação anterior: 14.998 pedidos faturados, 44.939 itens e R$ 14.420.828,23. São dados fictícios; não representam vendas reais. A execução automática anterior pelo Scheduler aprovou seis tasks em 45,415 s, sem novos dados. Os tempos são observações locais e não SLA.

Relatórios técnicos Markdown preservam o contexto de cada etapa. JSONs brutos, backups, dumps, datasets, credenciais e metadados privados de execução não fazem parte da distribuição. Não há CI configurada, e capturas reais da interface continuam pendentes.

## Revisão da distribuição

144 arquivos selecionados por manifesto, com 89 módulos Python e links locais revisados. Nenhum `.env`, dataset, backup, banco local, log, JSON bruto de execução ou objeto Git antigo foi incluído. SQLs foram preservados byte a byte para manter os checksums das migrações; linhas vazias finais originais em SQL não foram removidas por estética.

Varredura complementar Git/Python dos candidatos sem achados de credenciais reais: senha operacional e senha anterior ausentes. A URL com credenciais do teste negativo é sintética e intencional. Gitleaks/TruffleHog não estavam instalados; a revisão não é garantia de segurança absoluta. As evidências brutas de teste ficaram fora do repositório.

Repositório iniciado com um novo commit raiz, sem importação do Git anterior. Autoria e licença MIT preservadas. Capturas reais seguem pendentes; nenhuma imagem de demonstração foi fabricada.
