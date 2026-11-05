# Pastel da Casa — Etapa 06.1: plano do piloto persistente

**Estado: AUTORIZADO E EXECUTADO PELO USUÁRIO.**
A validação posterior e a reexecução idempotente foram concluídas. Consulte
[PILOT_500_RESULT.md](PILOT_500_RESULT.md). Os números previstos abaixo foram confirmados.

O conteúdo a seguir preserva o plano apresentado antes da autorização.

## Parâmetros fixados

- 50 clientes, 5 vendedores, 10 produtos e 500 pedidos NOVOS.
- Período UTC: 05/11/2025 (inclusivo) a 05/11/2026 (exclusivo).
- Seed 42, Faker 40.43.0, gerador versão 1, lotes de 50.
- Run ID: `9ed5fecf-6550-543f-b3ef-9a3da8e25f39`.
- Previsão: 375 FATURADOS, 75 PENDENTES, 50 CANCELADOS.
- Sem carga de 20.000 pedidos, ETL ou DuckDB.

O plano foi calculado em memória, reutilizando config.py, generation.py e os
preços do gerador existente. Nenhuma chamada de criação/faturamento foi feita.

## Estado encontrado e projeção

| Tabela | Antes | Novos previstos | Depois esperado |
| --- | ---: | ---: | ---: |
| clientes | 3 | 50 | 53 |
| vendedores | 3 | 5 | 8 |
| produtos | 5 | 10 | 15 |
| pedidos | 4 | 500 | 504 |
| itens_pedido | 4 | 1499 | 1503 |
| movimentacoes_estoque | 1 | 1136 | 1137 |

Os números finais pressupõem que não haja alterações concorrentes feitas pelo CRM.
Os quatro pedidos atuais têm 1 FATURADO, 1 PENDENTE e 2 CANCELADOS. A carga acrescenta
somente dados sintéticos próprios. Não substitui os registros existentes.

Previsões para os novos dados, sujeitas à validação após a carga:

- Movimentações: 10 ENTRADAS + 1126 SAIDAS.
- Valor dos pedidos faturados: R$ 365.780,06.
- Valor dos pedidos pendentes: R$ 77.209,60.
- Valor dos pedidos cancelados: R$ 45.189,91.
- Valor de todos os pedidos sintéticos: R$ 488.179,57.
- Saldo final esperado dos produtos sintéticos: 100 unidades em cada produto,
  1000 unidades ao todo; pendentes e cancelados não baixam nem reservam estoque.

## Migração revisada

A 003 está aplicada, com checksum correspondente ao arquivo atual.
A 004 está pendente. synthetic_runs, synthetic_records e synthetic_objects ainda
não existem no schema operacional. Os seis gatilhos trg_updated_at estão ativos.

A 004 é aditiva: cria três tabelas de auditoria/proveniência, índices, uma função e
seis gatilhos adicionais. Não contém DROP, TRUNCATE ou exclusão/reescrita dos registros
existentes. Mantém os gatilhos anteriores. O contexto histórico usa configurações
locais à transação e só altera datas de registros pertencentes à execução sintética;
sem esse contexto, a API mantém a auditoria normal.

O executor de migrações aplica tudo que estiver pendente: hoje, somente a 004.
Antes de executá-lo após a autorização, conferir novamente os arquivos e checksums.
Aplicar a migração pode requerer um breve bloqueio de DDL: evitar gravações no CRM
durante essa operação e a validação do piloto.

## Backup

O diretório exato, SHA-256, tamanho e duração estão em `backups/etapa06_1/`,
no `preflight.json` desta preparação. O dump é formato custom do PostgreSQL 16,
com dados, esquema, sequências e gatilhos do banco operacional. Não inclui
papéis globais do cluster; ownership e ACL foram omitidos para restauração pelo
usuário do ambiente.

A verificação fez:
1. pg_dump com captura binária direta, sem redirecionamento de texto do PowerShell.
2. pg_restore --list e presença dos dados das seis tabelas comerciais.
3. Leitura integral do arquivo por pg_restore --file=-, sem conexão de restauração.
4. SHA-256 e comparação dos hashes das linhas antes/depois.

Nenhuma restauração foi feita: validação de leitura do arquivo não equivale a um
ensaio completo de restauração. Backups são locais e ignorados pelo Git.

## Comandos preparados — NÃO executados

Na raiz do projeto, após autorização:

### 1. Aplicar somente as migrações pendentes

```powershell
.\.venv314\Scripts\python.exe backend/migrate.py
```

### 2. Executar o piloto persistente e medir a duração

```powershell
Measure-Command {
    .\.venv314\Scripts\python.exe -m scripts.synthetic_data --development --execute --clientes 50 --vendedores 5 --produtos 10 --pedidos 500 --start 2025-11-05 --end 2026-11-05 --seed 42 --batch-size 50 --run-id 9ed5fecf-6550-543f-b3ef-9a3da8e25f39
    if ($LASTEXITCODE -ne 0) { throw "Carga piloto não concluída; conferir os logs." }
}
```

### 3. Após conferir a primeira carga, repetir o MESMO comando

```powershell
.\.venv314\Scripts\python.exe -m scripts.synthetic_data --development --execute --clientes 50 --vendedores 5 --produtos 10 --pedidos 500 --start 2025-11-05 --end 2026-11-05 --seed 42 --batch-size 50 --run-id 9ed5fecf-6550-543f-b3ef-9a3da8e25f39
```

Esperado na repetição: `created: {}`, mesmas contagens/status/totais e nenhum
novo movimento de estoque. Não trocar seed, período, volumes ou run_id na retomada.
O tamanho do lote pode mudar sem modificar a identidade lógica.

## Validações depois da execução autorizada

- Comparar contagens e hashes de CADA registro anterior, usando preflight.json.
- Comparar números criados com as projeções e separar as linhas pelo run_id.
- Conferir FKs de pedidos/itens/movimentações e unicidade de CNPJ/itens/saídas.
- Calcular totais a partir de quantidade × preço histórico, por status.
- Conferir 375/75/50 e datas de criação/atualização/movimentação dentro do período UTC.
- Conferir entradas menos saídas = saldo, ausência de negativos e ausência de
  saídas em pedidos pendentes/cancelados.
- Reexecutar o run, medir tempos e confirmar zero duplicação.
- No Streamlit, Atualizar dados: clientes 53; produtos totais 15; pedidos totais 504.
  Verificar as listagens, pedidos e movimentos da carga. O número de produtos
  ativos dependerá também dos cinco registros anteriores.
- Verificar consumo dos dados pela API real e AppTest, distinguindo testes
  programáticos de uma conferência visual no navegador.
- Registrar relatório final com resultados e quaisquer divergências.

O gerador confirma lotes, e não a carga inteira em uma única transação. Uma falha
pode deixar os lotes anteriores gravados: a retomada usa o mesmo run_id e mantém
o provisionamento de estoque sem repetir entradas. Não apagar registros para tentar
retomar. O backup serve para recuperação planejada; não restaurá-lo sobre o banco
em uso sem uma autorização específica e avaliação das alterações posteriores.

## Pendências registradas na preparação (histórico)

- Autorização explícita para aplicar a migração e executar/reexecutar o piloto.
- Migração 004 e carga persistente ainda não executadas.
- Quantidades depois, tempo de carga, resultados pós-carga e aparição no CRM ainda
  não medidos; os valores desta preparação são projeções.
- Nenhuma autorização para a carga completa de 20.000 pedidos.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../../docs/VALIDATION.md.
