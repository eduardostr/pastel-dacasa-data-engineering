# Pastel da Casa — primeira FULL persistente da Etapa 07

**Estado: PUBLICADA E VALIDADA, após autorização explícita do usuário.**

- Run ID: 120e4450-3239-430a-a3bd-c9fca7d69f2b.
- Versão: b64f6faa-5123-4c19-8236-66b3cf5c069a.
- Snapshot UTC: 2026-11-05T12:49:08.278908+00:00.
- Duração registrada no controle: 36,635 segundos.
- Modo FULL, lote de 5000, PostgreSQL REPEATABLE READ e READ ONLY.
- Nenhum registro, schema ou gatilho do CRM foi modificado.

## Datasets publicados

| Dataset | Bronze | Silver | Quarentena |
| --- | ---: | ---: | ---: |
| clientes | 1000 | 1000 | 0 |
| produtos | 50 | 50 | 0 |
| vendedores | 30 | 30 | 0 |
| pedidos | 20000 | 20000 | 0 |
| itens_pedido | 59791 | 59791 | 0 |
| movimentacoes_estoque | 44984 | 44984 | 0 |

vendas_detalhadas: 44939 linhas, correspondentes a 14998 pedidos FATURADOS.
Valor financeiro conferido: **R$ 14.420.828,23**.

Os pedidos pendentes e cancelados permanecem na Silver de pedidos/itens, mas não
fazem parte de vendas_detalhadas. O preço atual do produto não substituiu o preço
histórico do item.

## Verificações executadas

- 28 arquivos de publicação conferidos por checksum; todos os Parquets lidos.
- Schema Arrow das seis tabelas conferido na Bronze e Silver.
- Valores originais da Bronze comparados com seus hashes de origem.
- Decimal(12,2) para preços/descontos e Decimal(38,2) para totais derivados.
- Timestamps em UTC com precisão de microssegundos.
- PKs únicas e FKs válidas na Silver.
- Quantidade × preço histórico - desconto igual ao subtotal de cada venda.
- Totais por pedido conferidos e soma financeira igual ao SQL da origem.
- Nenhum produto com estoque negativo.
- Hashes de todas as linhas comerciais do CRM idênticos antes/depois.
- Watermarks publicados junto com o manifesto após os arquivos validados.
- Reexecução do mesmo run reutilizou a mesma versão, sem novos datasets e sem
  alterar watermarks (verificação de reuso: 0,126 segundo).

## Onde estão os dados

Ponto de entrada: **data/control/current.json**. Esse arquivo contém referências
para Bronze, Silver, quarentena, métricas, watermarks e checksums.

Silver atual:
data/silver/120e4450-3239-430a-a3bd-c9fca7d69f2b/b64f6faa-5123-4c19-8236-66b3cf5c069a/

Bronze:
data/bronze/120e4450-3239-430a-a3bd-c9fca7d69f2b/e0dd6fe2205943fcb18bd239382084bd/

Quarentena:
data/quarantine/120e4450-3239-430a-a3bd-c9fca7d69f2b/b64f6faa-5123-4c19-8236-66b3cf5c069a/

Tamanho total da raiz data/, incluindo controles/cópias técnicas/logs no momento
da validação: 33281008 bytes. A pasta é ignorada pelo Git.

Exemplo de leitura com manifesto fixado:

```python
from pathlib import Path
from etl.load.files import current_manifest, dataset
root = Path("data").resolve()
snapshot = current_manifest(root)
vendas = dataset(root, "vendas_detalhadas", manifest=snapshot)
print(vendas.num_rows)
```

## Próximas operações

Não é necessário repetir a FULL. O próximo passo de validação operacional pode ser
uma INCREMENTAL, que ainda não foi executada sobre o CRM. O comando documentado é:

```powershell
.\.venv314\Scripts\python.exe -m etl --mode incremental --execute
```

Ele cria outra publicação e audita as alterações visíveis na origem, preservando
esta versão. Sem alterações no CRM, não deve duplicar entidades nem vendas.
A etapa de implementação já validou incrementais em schemas temporários.

Não houve mudança de API/Streamlit/.env/Docker Compose, implementação de Gold ou
DuckDB ou publicação no GitHub. Relatório estruturado em FULL_RUN_RESULT.json.

## Validação posterior de incrementais

Os testes incrementais operacionais foram concluídos após esta FULL. Consulte
[INCREMENTAL_RUN_RESULT.md](INCREMENTAL_RUN_RESULT.md). O estado descrito nesta
FULL continua preservado como versão histórica; current.json aponta para a
publicação incremental mais recente.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../docs/VALIDATION.md.
