# Operação local e reprodutibilidade

Siga primeiro o guia completo no [README](../README.md): ambiente Python, agregador requirements.txt, .env, volume externo, Docker, migrações e dois servidores. Os comandos são executados na raiz; o ambiente é .venv314. Não há script de provisionamento remoto.

## Configuração

| Variável | Consumidor / padrão |
| --- | --- |
| POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB | Compose, backend e ETL; defina em .env antes do primeiro volume |
| POSTGRES_HOST, POSTGRES_PORT | ETL; localhost e 5432 |
| ETL_DATABASE_URL | Alternativa opcional para conexão da ETL (psycopg2); não configura a API |
| API_BASE_URL | Frontend operacional; http://127.0.0.1:8000 |
| WAREHOUSE_DB_PATH | Frontend analítico; data/warehouse/pastel_da_casa.duckdb |

O backend usa localhost:5432 e constrói sua URL com psycopg2; DATABASE_URL não é lida.
Variáveis do frontend devem ser exportadas no terminal que inicia o Streamlit, por exemplo:

```powershell
$env:API_BASE_URL = "http://127.0.0.1:8000"
$env:WAREHOUSE_DB_PATH = (Join-Path (Get-Location) "data/warehouse/pastel_da_casa.duckdb")
```

O Compose usa o volume externo pastelflow-crm_postgres_data para preservar instalações existentes.
Criá-lo não apaga um volume já existente. Seeds não são reaplicados em volume preenchido.
Nunca use recriação/apagamento de volume para corrigir migrações. Mudança de senha em .env não altera um banco já inicializado.

## Backup PostgreSQL

Antes de persistir dados ou aplicar migrações em base existente, faça backup. Exemplo para os identificadores demonstrativos
(adapte -U e -d se os tiver alterado):

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
docker compose exec -T postgres pg_dump -U pastelflow -d pastelflow_oltp -Fc -f /tmp/pastel_backup.dump
docker compose cp postgres:/tmp/pastel_backup.dump "backups/pastel_$stamp.dump"
```

O dump é binário: docker compose cp evita corrompê-lo por redirecionamento de PowerShell.
Confira os códigos de saída e valide o arquivo antes de prosseguir. Backups são locais, ignorados pelo Git.
Não restaure automaticamente sobre a base atual.

## Planos sem carga

```powershell
.\.venv314\Scripts\python.exe -m etl --mode full
.\.venv314\Scripts\python.exe -m warehouse --mode full
.\.venv314\Scripts\python.exe -m scripts.synthetic_data --isolated --clientes 20 --vendedores 3 --produtos 8 --pedidos 40 --start 2025-11-05 --end 2026-11-05 --seed 42
```

## FULL e atualização

Uma instalação nova recebe schema/seed, migrações e opcionalmente geração persistente pequena antes da ETL.
Consulte [gerador](../scripts/synthetic_data/README.md); isolated descarta os registros ao concluir,
development persiste no banco atual. Cargas acima de 1.000 pedidos têm guarda adicional --allow-large-load.
Não execute novamente a geração de 20.000 pedidos sobre o ambiente de demonstração já preenchido.

Depois de aprovar a persistência local:

```powershell
$etlRun = [guid]::NewGuid().ToString()
.\.venv314\Scripts\python.exe -m etl --mode full --execute --allow-full --run-id $etlRun
.\.venv314\Scripts\python.exe -m warehouse --mode full --execute --allow-persistent
```

Depois de alterações no CRM, repita com novo run_id incremental:

```powershell
$incrementalRun = [guid]::NewGuid().ToString()
.\.venv314\Scripts\python.exe -m etl --mode incremental --execute --run-id $incrementalRun --lookback-seconds 900
.\.venv314\Scripts\python.exe -m warehouse --mode incremental --execute --allow-persistent
```

Feche leitores DuckDB durante a escrita. Reabra Streamlit e clique Atualizar indicadores.
Uma migração SQL do operacional não substitui a carga ETL/DW.
O dashboard é uma fotografia da última publicação, não a operação em tempo real.

## Falha e retomada

Preserve o run_id original e o modo. Após verificar a causa, reexecute a linha original da ETL com o mesmo run_id.
Depois do checkpoint, reutiliza Bronze validada; antes dele, pode extrair novo snapshot.
Não troque current.json manualmente. Para reconstruir a execução FULL atual com sua Bronze:

```powershell
# $etlRun deve ser o run_id real da execução atual, não um UUID novo.
.\.venv314\Scripts\python.exe -m etl --mode full --execute --allow-full --run-id $etlRun --reprocess
```

No DW, repita o modo/run_id autorizado; fonte já aplicada pode retornar REUSED.
Verifique dw_runs e dw_state em conexão somente leitura. Não edite dimensões ou fato manualmente.
[Detalhes de recuperação](incremental-and-recovery.md).

## Problemas frequentes

- Docker não encontrado: instale/inicie Docker Desktop, configure WSL2 e reabra o terminal.
- Python global não encontrado: use o executável explícito de .venv314.
- API indisponível: verifique /health e docker compose ps; veja as mensagens do terminal da API.
- Migração com checksum divergente: não edite migração já aplicada; investigue e proponha nova migração.
- DW ausente: execute FULL autorizada; frontend não cria arquivo vazio.
- DuckDB bloqueado: feche conexões/leitores e aguarde o escritor; não apague arquivos de lock/WAL durante a execução.
- Sem vendas no recorte: confira filtros e se existem pedidos faturados na última carga.


> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em VALIDATION.md.
