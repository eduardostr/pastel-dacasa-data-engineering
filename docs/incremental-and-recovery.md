# Incremental, idempotência e recuperação

## ETL

A extração usa transação de snapshot consistente e somente leitura. A janela updated_at >= watermark − lookback
é inclusiva (padrão 900 segundos). Em paralelo, uma reconciliação integral de IDs e hashes identifica
inserções retroativas, mudanças fora da janela e ausências. Portanto não se trata de CDC nem de leitura apenas das linhas novas.

A Bronze incremental recebe candidatos/diferenças; a Silver aplica upsert por PK e revalida o snapshot.
Ausências são auditadas em deleted_keys.json. Alterações em entidades relacionadas propagam para vendas_detalhadas.
Campos Decimal e UTC são preservados. Rejeições financeiras/referenciais não devem publicar uma venda parcial.

Arquivos são versionados; hashes e legibilidade são conferidos antes de trocar atomicamente current.json.
Esse manifesto publica referências e watermarks juntos; SQLite auxilia a auditoria, mas não é o commit lógico.

| Falha | Estado válido / recuperação |
| --- | --- |
| Antes do checkpoint Bronze | Publicação anterior continua válida; repetir run_id extrai outro snapshot |
| Após checkpoint Bronze | Mesmo run_id reutiliza a fotografia original validada |
| Antes de publicar current.json | Watermarks/publicação anteriores preservados |
| Depois de publicar, antes da auditoria | Mesmo run_id reconcilia auditoria sem duplicar |
| Hash/schema incompatível | Falhar sem publicar; investigar origem/artefato, não editar manifesto manualmente |
| Execução antiga versus publicação nova | Rejeitar retrocesso; iniciar nova execução |

--reprocess permite reconstruir a execução atual a partir da Bronze original; não autoriza republicar uma execução antiga
sobre versões novas. Exemplos executáveis no runbook e etl/README.md.

## Warehouse

Fixa uma publicação Silver, confere hashes, contratos e contagens. FULL cria a base; incremental exige baseline.
Dimensões e fato são reconciliadas em uma transação; SKs existentes permanecem. Fato contém apenas faturados.
Mesma versão retorna REUSED e pode publicar extensões Gold; o dashboard não altera tabelas.
Rollback preserva dados anteriores em falhas antes do commit. Auditoria pós-commit pode ser reconciliada na retomada.

Feche leitores durante escrita DuckDB. Locks são locais, não um coordenador distribuído.
Backups devem ser feitos com leitores/escritores coordenados; não copie arquivos no meio de uma transação de escrita.
Não restaure backups automaticamente sobre o arquivo ativo.

## Limites

Sem CDC, SCD2, streaming, orquestração ou retenção automática. Não remova Bronze ou versões ainda referenciadas.
Retomada não significa que mudanças posteriores na origem entram na fotografia original; um novo incremental as captura.


> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em VALIDATION.md.
