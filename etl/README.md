# Pastel da Casa — Etapa 07: ETL Bronze e Silver

Pipeline local Python/SQLAlchemy/Pandas/PyArrow. Não modifica a API, o Streamlit
ou o PostgreSQL operacional. Não inclui DuckDB nem Gold.

**A primeira FULL persistente foi autorizada e publicada em 05/11/2026.**
Resultado em [FULL_RUN_RESULT.md](FULL_RUN_RESULT.md). Não é necessário repeti-la.
Os testes automatizados continuam usando apenas schemas e diretórios temporários.

## Instalação

Na raiz do projeto:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r etl/requirements.txt
```

A conexão lê as variáveis POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB do .env
existente, sem sobrescrevê-lo. POSTGRES_HOST/POSTGRES_PORT são opcionais.
ETL_DATABASE_URL pode configurar explicitamente outra origem PostgreSQL.
Não grave essa URL com senha em comandos compartilhados ou versionados.

## Organização

| Módulo | Responsabilidade |
| --- | --- |
| config/ | Conexão, contrato Arrow e parâmetros |
| extract/ | Snapshot PostgreSQL somente leitura, em lotes |
| quality/ | Regras, duplicidades, FKs e quarentena |
| transform/ | Merge da origem e vendas detalhadas |
| load/ | Parquet, hashes, manifestos e leitores |
| control/ | Exclusão de escritores e auditoria SQLite local |
| pipeline.py | Orquestração, retomada e publicação |
| tests/ | Testes isolados com PostgreSQL real |

```text
data/
  bronze/<run_id>/<extraction_id>/
    clientes.parquet ... movimentacoes_estoque.parquet
    fingerprints.json
    deleted_keys.json
  silver/<run_id>/<version>/
    clientes.parquet ... movimentacoes_estoque.parquet
    vendas_detalhadas.parquet
  quarantine/<run_id>/<version>/
    clientes.parquet ... movimentacoes_estoque.parquet
  control/
    current.json
    manifests/<version>.json
    runs/<run_id>/extraction.json
    versions/<version>/source/*.parquet
    audit.sqlite
    logs/<attempt_id>.log
    writer.lock
  .staging/
```

Arquivos versionados não são sobrescritos. current.json é a única referência de
publicação atual; não tratar diretórios listados manualmente como resultados
definitivos. .staging e versões órfãs não são publicações. Não há limpeza automática
de históricos nesta etapa.

## FULL — somente após autorização

Primeiro, mostre o plano sem gerar arquivos ou consultar dados:

```powershell
.\.venv314\Scripts\python.exe -m etl --mode full
```

**Após autorização explícita**, gere um ID e execute:

```powershell
$fullRunId = [guid]::NewGuid().ToString()
.\.venv314\Scripts\python.exe -m etl --mode full --execute --allow-full --run-id $fullRunId --batch-size 5000
```

Mantenha o valor de fullRunId para retomar em caso de falha. A CLI bloqueia FULL
com --execute sem --allow-full. A flag é uma confirmação técnica, não substitui
a autorização do usuário. Também é possível configurar --data-dir e --schema.
O padrão é data/ na raiz e schema public.

A FULL extrai as seis tabelas completas. O snapshot comum é REPEATABLE READ e
READ ONLY, com cursor em lotes, e contém metadados _run_id, _extracted_at, _source e
_record_hash. O SQL não executa INSERT, UPDATE, DELETE, DDL ou alterações de sessões
do CRM; o fuso é definido somente na transação de extração.

## INCREMENTAL

Exige uma FULL já publicada na mesma raiz:

```powershell
$incrementalRunId = [guid]::NewGuid().ToString()
.\.venv314\Scripts\python.exe -m etl --mode incremental --execute --run-id $incrementalRunId --lookback-seconds 900
```

A extração combina:
1. updated_at >= watermark anterior - janela de segurança, de forma inclusiva.
2. Reconciliação de IDs e hashes de TODAS as linhas no mesmo snapshot.
3. Registro de IDs ausentes como tombstones em deleted_keys.json.

Isso captura timestamps iguais, commits tardios e registros sintéticos recém-
inseridos com datas históricas, mesmo anteriores à janela. Não depende de
updated_at > watermark. O custo é uma leitura completa de reconciliação por
execução; apenas candidatos/diferenças/janela vão para a Bronze incremental.

Cada watermark é a fronteira temporal do snapshot, e não o maior ID nem um
timestamp futuro de um registro. O estado técnico guarda hashes por ID. A Silver
faz upsert por PK sobre o estado bruto anterior e revalida o snapshot inteiro;
inativos e mudanças de status são preservados. Uma versão bruta técnica retém
também registros rejeitados, permitindo correções em incrementais posteriores.

Remoções físicas na origem são detectadas por comparação de IDs e refletidas no
snapshot Silver; os dados antigos continuam nas versões imutáveis e os IDs são
auditados. A ETL nunca exclui registros no CRM.

As seis tabelas atuais têm updated_at. Para uma origem futura sem esse campo,
a estratégia segura é a comparação integral de snapshots/hashes, já usada para
reconciliação; é necessário definir seu contrato antes de habilitá-la. Mudanças
não previstas no contrato das seis tabelas fazem a execução falhar sem publicação,
em vez de inventar colunas ou perder tipos silenciosamente.

## Tipos, qualidade e nulos

Bronze mantém valores da origem. TIMESTAMPTZ vira timestamp[us, UTC] (mesmo instante);
NUMERIC(12,2) vira decimal128(12,2); IDs são int64, quantidades int32, booleanos
continuam booleanos e CNPJ permanece string com zeros iniciais.

Silver:
- Nomes de colunas snake_case seguem o contrato real existente.
- Textos cadastrais são aparados; UF e status normalizados em maiúsculas; e-mail
  em minúsculas; CNPJ válido com pontuação padrão é normalizado para 14 dígitos.
- ABERTO legado é mapeado para PENDENTE. Não são inventados status desconhecidos.
- Não há preenchimento de preço/quantidade nulos com zero.
- Apenas observacao e id_pedido das movimentações aceitam nulos; id_pedido nulo
  representa recebimento ou movimento sem pedido, não uma FK quebrada.
- Datas obrigatórias devem ser válidas, com updated_at >= created_at.
- IDs devem ser positivos; quantidades/peso positivos; estoque não negativo.
- Preço de produto deve ser > 0; preço unitário histórico e desconto devem ser >= 0.
  Desconto não pode ultrapassar quantidade × preço histórico.
- Valores monetários são calculados com Decimal, nunca float.
- PKs e chaves naturais são verificadas; FKs são validadas sobre os pais aceitos.
- Duplicata exata mantém uma ocorrência e audita as extras na quarentena. Se há
  versões conflitantes, só há vencedor quando updated_at é estritamente maior.
  Empate ambíguo e colisões de chave natural rejeitam todas as linhas conflitantes.
- Linhas rejeitadas vão para Parquet de quarentena com original, metadados e
  _rejection_reason. Pais rejeitados fazem filhos dependentes serem rejeitados.
- Pedido com itens inválidos ou saídas de faturamento incoerentes não produz uma
  venda parcial. SAIDA vinculada a pendente/cancelado é rejeitada.

Schema drift, arquivo corrompido e valores que não possam ser representados pelo
contrato Arrow interrompem a execução e ficam no log; não são convertidos
silenciosamente para outro tipo. A origem não é corrigida pela ETL.

Não se exige saldo = movimentos desde zero para todos os produtos legados:
alguns foram cadastrados com saldo inicial sem ENTRADA nas fases anteriores.
São validados estoque não negativo e consistência das saídas de vendas. Não são
fabricadas entradas retroativas.

## vendas_detalhadas

Grão: uma linha por id_item de pedido FATURADO, com pedido, produto, cliente e
vendedor válidos. Contém quantidade, preco_unitario histórico, desconto, subtotal,
total_pedido e dados cadastrais. O preço atual do catálogo NÃO substitui o histórico.

Subtotal e total usam decimal128(38,2). total_pedido se repete nas linhas do mesmo
pedido: para somar vendas, use subtotal; não some total_pedido por item.

A visão é reconstruída integralmente a cada publicação para propagar mudanças em
clientes/produtos/vendedores e status de pedidos, mesmo quando o item não mudou.
source_updated_at considera as entidades relacionadas; _record_hash identifica
mudanças do conteúdo derivado.

## Publicação, auditoria e watermarks

Cada tentativa registra run_id, attempt_id, modo, início/fim UTC, status, duração,
erros e métricas por tabela em control/audit.sqlite e nos logs locais.
Métricas distinguem scanned/extracted, candidate_rows, valid/rejected,
inserted/updated/removed_from_valid e source_changed. Quantidades válidas/rejeitadas
referem-se ao snapshot candidato, e não apenas à janela incremental.

Bronze completo é fechado e recebe checksums antes do checkpoint de extração.
Silver/quarentena/estado bruto são escritos em staging, movidos para versões novas,
e todos os Parquets são lidos integralmente para validação de hashes/legibilidade.
Só depois um os.replace de current.json publica TODAS as referências e watermarks
juntos. O SQLite é auditoria auxiliar; o manifesto é o commit lógico autoritativo.

Falha antes do manifesto: publicação/watermarks antigos continuam ativos.
Falha após o manifesto, antes da auditoria: dados completos já estão visíveis;
repetir a mesma execução reconcilia o status sem duplicar resultados.
Leitores verificam hashes e não seguem arquivos parciais. Para leitura conjunta,
fixe um manifesto único:

```python
from pathlib import Path
from etl.load.files import current_manifest, dataset

root = Path("data").resolve()
snapshot = current_manifest(root)
clientes = dataset(root, "clientes", manifest=snapshot)
vendas = dataset(root, "vendas_detalhadas", manifest=snapshot)
```

## Retomada, reexecução e reprocessamento

- Repetir modo e run_id atualmente publicados retorna a versão existente, sem
  extrair de novo.
- Se falhar depois da extração, repetir o MESMO run_id reutiliza o Bronze validado.
  O banco pode ter mudado: a retomada continua a fotografia original; um novo
  incremental captura alterações posteriores.
- Se falhar antes do checkpoint, a tentativa seguinte extrai outro snapshot; o
  primeiro não foi publicado.
- Se outra execução publicou uma versão posterior, uma extração antiga não pode
  sobrescrevê-la. Preserve a Bronze e inicie um novo run_id.
- Para reconstruir a execução ATUAL com o mesmo Bronze, use --reprocess com seu
  modo e run_id. Não permite republicar um run antigo sobre versões mais novas.

Exemplo, após uma FULL já autorizada/publicada:

```powershell
.\.venv314\Scripts\python.exe -m etl --mode full --execute --allow-full --run-id $fullRunId --reprocess
```

A raiz de dados é vinculada à origem/contrato. Não reutilize a mesma raiz para
outro banco/schema. Alterações de batch-size são permitidas; outra janela,
contrato ou modo exige configuração/execução compatível ou outra raiz.

## Testes isolados

```powershell
.\.venv314\Scripts\python.exe -m unittest discover -s etl/tests -v
```

Os testes criam schemas PostgreSQL test_synthetic_<uuid> usando o helper de isolamento
já existente e diretórios do sistema temporários. Só essas tabelas de fixture são
modificadas. São necessárias permissão CREATE SCHEMA e as dependências das etapas
anteriores para o helper. Schemas e diretórios são removidos ao final.

São exercitados FULL/incremental, Decimal/UTC, janela inclusiva, commits concorrentes,
inserções retroativas, quarentena, duplicidades, relações, finanças, preços históricos,
alterações relacionadas, exclusões de fixture, falhas, retomada, checksum, publicação
e bloqueio de escritores. Nenhuma FULL persistente operacional é executada pelos testes.

## Limites desta etapa

- Incrementais reconciliam todas as linhas, e a transformação/joins mantêm o snapshot
  em memória. Não é CDC/WAL nem processamento distribuído/streaming ilimitado.
- Lock e publicação são locais, em um único host/filesystem; não são lock distribuído
  ou commit em armazenamento de objetos. Preferir disco local e uma única máquina.
  Sincronizadores como OneDrive não constituem protocolo de publicação distribuída.
- os.replace oferece troca de referência local, com flush/fsync de arquivos;
  não se promete recuperação de queda de energia para qualquer volume/provedor.
- Não há agendamento, retenção automática, paginação, Gold ou DuckDB.
- A primeira FULL autorizada sobre os 20.000 pedidos foi medida em 36,635 segundos
  no ambiente local. Isso não é garantia de desempenho para outras execuções.


## Validação incremental operacional concluída

Inclusão/atualização de um cliente fictício inativo, reexecução do mesmo run e
novo incremental sem alterações foram validados após a FULL. O cadastro de teste
permanece no CRM, que agora tem 1.001 clientes. Registros anteriores preservados.
Resultado: [INCREMENTAL_RUN_RESULT.md](INCREMENTAL_RUN_RESULT.md).

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../docs/VALIDATION.md.
