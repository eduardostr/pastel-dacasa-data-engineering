# Pastel da Casa — Etapa 06.2: resultado da ampliação histórica

**Estado: CONCLUÍDA E VALIDADA PROGRAMATICAMENTE.**

O usuário executou a ampliação com a configuração preparada. A validação posterior
não executou uma nova carga: consultou os dados persistidos, repetiu a mesma
identidade concluída e confirmou created={}.

## Configuração e duração

- Run ID: cda39340-14de-5e10-9694-9e5c28c70937.
- 947 clientes, 22 vendedores, 35 produtos e 19496 pedidos adicionais.
- Período UTC de 05/11/2025 inclusivo a 05/11/2026 exclusivo.
- Seed 42; Faker pt_BR 40.43.0; gerador versão 1; lotes de 200.
- Estado COMPLETED, progresso 19496, valid=true, errors=[].
- Carga inicial: 508,270 segundos (8 minutos e 28,270 segundos), conforme log.
- Tentativa inicial: 781b2469-21f9-4919-9247-4996240ef71d.

## Contagens confirmadas

| Tabela | Antes | Inseridos | Total |
| --- | ---: | ---: | ---: |
| clientes | 53 | 947 | 1000 |
| vendedores | 8 | 22 | 30 |
| produtos | 15 | 35 | 50 |
| pedidos | 504 | 19496 | 20000 |
| itens_pedido | 1503 | 58288 | 59791 |
| movimentacoes_estoque | 1137 | 43847 | 44984 |

Não usar o maior ID como contagem: sequências não foram reiniciadas, e podem ter
lacunas de testes/transações anteriores. Os totais acima foram conferidos por COUNT.

## Status e valores financeiros

| Status | Nova carga | Total global | Valor da nova carga | Valor global |
| --- | ---: | ---: | ---: | ---: |
| FATURADO | 14622 | 14998 | R$ 14.055.028,17 | R$ 14.420.828,23 |
| PENDENTE | 2924 | 3000 | R$ 2.757.690,89 | R$ 2.834.989,49 |
| CANCELADO | 1950 | 2002 | R$ 1.814.010,22 | R$ 1.859.380,13 |

Soma de todos os novos pedidos: R$ 18.626.729,28, incluindo pendentes/cancelados.
Esse valor não é o faturamento; faturamento corresponde à linha FATURADO.

## Integridade e auditoria

- Nenhuma FK ausente, nenhum CNPJ repetido, nenhum item repetido por produto/pedido
  e nenhuma saída de estoque duplicada por pedido/produto.
- Movimentações e quantidades conferidas para pedidos faturados; pendentes e
  cancelados não têm saídas de faturamento.
- Datas da nova carga dentro do período: primeiras criações em 05/11/2025,
  últimas atualizações antes de 05/11/2026; updated_at >= created_at.
- Hashes de CADA linha das seis tabelas existentes antes da ampliação foram
  comparados com o inventário do backup: todos preservados, incluindo o piloto.
- O piloto de 500 pedidos foi revalidado e continua COMPLETED/valid=true.
- Nenhuma migração nova foi necessária; sequências não foram reiniciadas.

## Estoque

- Nova carga: 35 ENTRADAS, 465677 unidades recebidas.
- Nova carga: 43812 SAIDAS, 462177 unidades baixadas.
- Os 35 produtos novos têm saldo de 100 unidades cada: 3500 remanescentes.
- Estoque global: 4913 unidades. Nenhum produto negativo.
- Entradas têm data, produto, quantidade e origem com run_id.
- Saídas têm pedido e produto, com quantidade igual ao item faturado.
- A conciliação integral dos produtos sintéticos passou. Os cinco produtos
  legados mantêm os saldos iniciais sem movimento de entrada descritos no plano;
  nenhum movimento retroativo foi inventado.

## Idempotência

Reexecução do mesmo run: created={}, 122635 registros ignorados e hashes de todas
as linhas comerciais inalterados. Nenhum novo cadastro, pedido, item ou movimento.

Tempo interno: 0,586 segundo; tempo do processo incluindo inicialização Python:
3,721 segundos. Tentativa: 6a1135ae-635f-42fd-be27-5cf157edd594.

Não é necessário executar o comando novamente. Não usar um novo run_id com essa
configuração: ele representaria outra carga e ultrapassaria as metas atuais.

## CRM e API

Testes somente leitura com API real HTTP e Streamlit AppTest:

- Produtos: 50 linhas; clientes: 1000; vendedores: 30; pedidos: 20000.
- Dashboard: 1000 clientes, 49 produtos ativos, 4913 unidades de estoque,
  valor estimado de estoque R$ 143.294,50.
- Pedido faturado #20040 consultado com 4 movimentações visíveis.
- Nenhum erro ou exceção nas páginas; nenhuma alteração de dados.
- GET /pedidos/ levou cerca de 0,444 segundo nesta medição local; renderização
  programática da página Pedidos, cerca de 0,615 segundo. Isso não é benchmark
  de navegador nem garantia de desempenho sob concorrência.

A API foi iniciada temporariamente para testar e encerrada ao final. Não houve
inspeção visual no navegador. Para conferir visualmente, iniciar a API e o
Streamlit, abrir http://127.0.0.1:8501 e clicar em Atualizar dados.

## Backup

O backup anterior à ampliação permanece intacto:
backups/etapa06_2/20261105_081419/operacional_antes_ampliacao.dump.
SHA-256: eb023a00faf7d25df88a0685a4c3ea3202d64d0b05d8fe1687de3eaf462ee2c1.
Leitura integral verificada na preparação; não foi feito ensaio de restauração.

Este backup representa a base com o piloto, antes da ampliação. Não confundir com
um backup posterior dos 20000 pedidos. Nenhuma restauração foi realizada.

## Entrega

Resultado estruturado em FULL_LOAD_RESULT.json. FULL_LOAD_PLAN.md preserva o plano
prévio e aponta para este resultado. README principal e README do gerador foram
atualizados. Não houve alteração na lógica comercial, publicação no GitHub,
ETL ou DuckDB.

A Etapa 06.2 está concluída nas validações programáticas. A conferência visual
do CRM pelo usuário é a única verificação de interface ainda não realizada.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../../docs/VALIDATION.md.
