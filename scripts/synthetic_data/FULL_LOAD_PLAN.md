# Pastel da Casa — Etapa 06.2: ampliação histórica

**Estado: EXECUTADO PELO USUÁRIO E VALIDADO.**
Consulte [FULL_LOAD_RESULT.md](FULL_LOAD_RESULT.md) para os resultados e a
reexecução idempotente. Não é necessário repetir a carga.

O conteúdo abaixo preserva o plano apresentado antes da execução.

## Contagens verificadas e adicionais

| Tabela | Atual | Adicionar | Total projetado |
| --- | ---: | ---: | ---: |
| clientes | 53 | 947 | 1000 |
| vendedores | 8 | 22 | 30 |
| produtos | 15 | 35 | 50 |
| pedidos | 504 | 19496 | 20000 |
| itens_pedido | 1503 | 58288 | 59791 |
| movimentacoes_estoque | 1137 | 43847 | 44984 |

As metas são TOTAIS, e não novos registros. Não executar com os argumentos
1000/30/50/20000: esses números criariam uma carga adicional e ultrapassariam
as metas. Revalidar as contagens antes da execução: mudanças feitas no CRM após
esta preparação podem exigir novo cálculo e um plano atualizado.

## Execuções anteriores e migrações

Existe uma execução sintética operacional:
- Run ID: 9ed5fecf-6550-543f-b3ef-9a3da8e25f39.
- Estado COMPLETED, 500 pedidos.
- Configuração: 50 clientes, 5 vendedores e 10 produtos próprios.
- Validação de status, datas, movimentos e saldo passou novamente na preparação.

As migrações 003 e 004 estão aplicadas e seus checksums correspondem aos arquivos.
Não é necessária nova migração para esta ampliação. A nova carga terá identidade
diferente do piloto; não alterar a configuração nem reaproveitar o run_id do piloto.

## Configuração fixada da nova execução

- Run ID: cda39340-14de-5e10-9694-9e5c28c70937.
- Faker pt_BR 40.43.0, gerador versão 1, seed 42.
- Período UTC: 05/11/2025 inclusivo a 05/11/2026 exclusivo.
- Lotes de 200 pedidos, com retomada idempotente pelo mesmo run_id.
- Cadastros e produtos novos e exclusivos desta execução; os anteriores não
  serão utilizados para as novas vendas nem terão estoques ou datas alterados.
- Preços capturados pelo serviço de pedidos e preservados nos itens.
- Faturamento reutiliza o serviço existente, com transações e bloqueios.

## Previsões de status e valores

| Status | Novos pedidos | Total global projetado |
| --- | ---: | ---: |
| FATURADO | 14622 | 14998 |
| PENDENTE | 2924 | 3000 |
| CANCELADO | 1950 | 2002 |

A proporção final é aproximadamente 75%/15%/10%. A diferença de dois pedidos
em relação à divisão exata de 20.000 preserva os status dos registros existentes.

Valores previstos da nova carga, calculados em memória a partir do plano e preços:
- FATURADO: R$ 14.055.028,17.
- PENDENTE: R$ 2.757.690,89.
- CANCELADO: R$ 1.814.010,22.
- Faturado global atual: R$ 365.800,06.
- Faturado global após a carga: R$ 14.420.828,23.

São projeções, não resultados já gravados. Conferir os valores por SQL após a
execução, sempre distinguindo faturamento de pedidos pendentes/cancelados.

## Estratégia de estoque

Os 35 produtos novos receberão 35 movimentos ENTRADA no início do período
(05/11/2025 00:00:00 UTC). Quantidade por produto = demanda dos seus pedidos
faturados + 100 unidades. As quantidades individuais estão em
FULL_LOAD_PLAN.json, plan.stock_entries.

- Entradas previstas: 465677 unidades em 35 movimentos.
- Saídas previstas: 462177 unidades em 43812 movimentos vinculados aos pedidos.
- Movimentações novas totais: 43847.
- Saldo final por novo produto: 100 unidades; total novo remanescente: 3500.
- Estoque global atual: 1413; total final previsto: 4913 unidades.

Cada entrada informa produto, quantidade, data histórica e observação
'Estoque inicial sintético da execução <run_id>'. A proveniência também fica em
synthetic_records/synthetic_objects. A entrada inicial não tem id_pedido, pois é
um recebimento de estoque; cada saída de faturamento tem id_pedido e id_produto.

O recebimento é confirmado antes das vendas e rastreado para não se repetir na
retomada. O serviço de faturamento impede estoque negativo e faturamento repetido.
Pendentes/cancelados não provocam saídas.

### Limitação dos saldos anteriores

Nenhum estoque atual está negativo. Os produtos sintéticos do piloto conciliam
com entradas menos saídas e as movimentações dos pedidos existentes estão coerentes.

Cinco produtos legados têm estoque inicial cadastrado diretamente, sem ENTRADA:
IDs 1, 2, 3, 14 e 68, com saldos iniciais inferidos de 200, 100, 80, 25 e 10.
O produto 68 possui saída de 2 e saldo atual 8. Não é correto exigir saldo igual
ao movimento líquido desde zero para esses cinco produtos. Nenhuma entrada
retroativa será inventada e nenhum dado antigo será alterado para essa ampliação.
Para os novos produtos, a conciliação integral desde a entrada inicial é obrigatória.

## Backup novo, antes da ampliação

Caminho: backups/etapa06_2/20261105_081419/operacional_antes_ampliacao.dump.
Formato custom PostgreSQL, 86568 bytes.
SHA-256: eb023a00faf7d25df88a0685a4c3ea3202d64d0b05d8fe1687de3eaf462ee2c1.

Foram conferidos pg_restore --list, presença das tabelas comerciais e das tabelas
de controle sintético, leitura integral por pg_restore --file=- e checksum.
Contagens/hashes das linhas comerciais ficaram iguais antes e depois da preparação.
Duração do backup e verificação: 2,807 segundos.

O dump inclui o piloto e a migração 004. Não inclui papéis globais; ownership/ACL
foram omitidos para restauração pelo usuário do ambiente. Não foi feito ensaio de
restauração. Inventário completo e hashes por ID estão no preflight.json junto ao
backup. A pasta backups já é ignorada pelo Git.

## Comandos preparados — não executados

Na raiz do projeto. Primeiro, é possível exibir o plano sem gravação:

```powershell
.\.venv314\Scripts\python.exe -m scripts.synthetic_data --development --clientes 947 --vendedores 22 --produtos 35 --pedidos 19496 --start 2025-11-05 --end 2026-11-05 --seed 42 --batch-size 200 --run-id cda39340-14de-5e10-9694-9e5c28c70937
```

**Somente depois de autorização explícita e nova conferência das contagens:**

```powershell
Measure-Command {
    .\.venv314\Scripts\python.exe -m scripts.synthetic_data --development --execute --allow-large-load --clientes 947 --vendedores 22 --produtos 35 --pedidos 19496 --start 2025-11-05 --end 2026-11-05 --seed 42 --batch-size 200 --run-id cda39340-14de-5e10-9694-9e5c28c70937
    if ($LASTEXITCODE -ne 0) { throw "Carga não concluída; confira o log antes de retomar." }
}
```

Após a validação, repetir o mesmo comando/identidade para verificar idempotência:
esperado created={}, nenhuma nova linha/saída e mesmas contagens e valores.
Não trocar parâmetros ou run_id em caso de falha. Logs ficam em
scripts/synthetic_data/logs e o estado/progresso em synthetic_runs.

## Estimativa e limitações

Extrapolação simples do piloto: 19496 / 500 × 11,483 = aproximadamente 447,7
segundos (7,5 minutos). É uma referência, não uma medição desta carga. Reservar
uma janela maior, por exemplo 10–20 minutos, dependendo de disco, Docker e
concorrência. Tempo real e ritmo dos lotes serão registrados após autorização.

O plano é mantido em memória (O(pedidos + itens)); o backend executa consultas por
pedido/itens, embora commits sejam em lotes e não haja chamadas HTTP do gerador.
Não há promessa de throughput linear. O Streamlit/API atuais listam todos os
pedidos, sem paginação; a experiência pode ficar mais lenta com 20.000 registros.
Essa preparação não muda os endpoints nem a interface.

Uma falha pode deixar lotes anteriores confirmados. A retomada é idempotente,
mas não existe rollback global automático da carga. Não apagar dados nem restaurar
o backup sobre o banco em uso sem avaliação/autorização específica. Enquanto
executar e validar, evitar alterações manuais nos registros da carga. O backup
é o estado da preparação: revalidar sua atualidade antes da execução.

## Validações previstas após autorização

- Contagens globais e por run_id, sem inferir quantidades pelo maior ID.
- Status global e da execução; FKs, unicidade e integridade das movimentações.
- Totais financeiros por status, com preços históricos.
- Entradas/saídas/saldos por produto novo e ausência de estoque negativo.
- Comparação de hashes de TODOS os registros anteriores, incluindo o piloto.
- Datas dentro do período, created_at preservado e updated_at coerente.
- Reexecução da mesma identidade sem duplicação.
- Tempo total e consumo pelo CRM, distinguindo AppTest de inspeção visual.

Não foram aplicadas migrações, executadas cargas ou resetadas sequências.
Não houve publicação no GitHub, ETL ou DuckDB. Aguardando autorização.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../../docs/VALIDATION.md.
