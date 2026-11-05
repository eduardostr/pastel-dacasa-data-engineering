# Pastel da Casa — Etapa 06.1: resultado do piloto

**Estado: CONCLUÍDO E VALIDADO PROGRAMATICAMENTE.** A migração e a primeira carga
foram executadas pelo usuário após autorização explícita. A verificação posterior
consultou o banco, comparou os dados antigos com o inventário e repetiu o mesmo run.

Run ID: 9ed5fecf-6550-543f-b3ef-9a3da8e25f39. Seed 42. Período UTC de
05/11/2025 a 05/11/2026, fim exclusivo. Configuração: 50 clientes, 5 vendedores,
10 produtos, 500 pedidos, lotes de 50.

| Tabela | Antes | Inseridos | Depois |
| --- | ---: | ---: | ---: |
| clientes | 3 | 50 | 53 |
| vendedores | 3 | 5 | 8 |
| produtos | 5 | 10 | 15 |
| pedidos | 4 | 500 | 504 |
| itens_pedido | 4 | 1499 | 1503 |
| movimentacoes_estoque | 1 | 1136 | 1137 |

## Migração e backup

003 e 004 aplicadas, com checksums correspondentes aos arquivos atuais.
O backup anterior permanece intacto, com SHA-256 conferido. A leitura integral
do arquivo foi verificada na preparação; não foi realizado ensaio de restauração.
Caminho: backups/etapa06_1/20261105_070326/operacional_antes_piloto.dump.

## Validações da carga

- 375 FATURADOS, 75 PENDENTES, 50 CANCELADOS; estado da execução COMPLETED,
  progresso 500, valid=true e lista de erros vazia.
- Integridade referencial conferida; nenhuma referência ausente ou saída duplicada.
- 10 ENTRADAS e 1126 SAIDAS, vinculadas aos produtos/pedidos da execução.
- Saldo final de 100 unidades em cada um dos dez produtos sintéticos, sem negativos.
- Itens mantêm preço histórico; total geral dos novos pedidos R$ 488.179,57.
- Valores por status: faturados R$ 365.780,06; pendentes R$ 77.209,60;
  cancelados R$ 45.189,91. O total geral não representa somente vendas faturadas.
- Datas coerentes com o período e atualizações não anteriores à criação.
  As primeiras criações são em 05/11/2025, últimas atualizações antes de 05/11/2026.
  O período tem 12 meses corridos, embora toque 13 agrupamentos de mês-calendário
  por começar/terminar no dia 5.
- Hashes de cada linha existente antes da carga foram comparados: todos os registros
  originais das seis tabelas estão preservados, incluindo seus timestamps.

## Idempotência e tempos

Carga inicial: 11,483 segundos no log do gerador. A tentativa inicial foi
b0810f39-5c85-4d8b-b779-e2ed80cc4dfb.

Reexecução com a mesma identidade: created={}, 3200 registros ignorados,
mesmos status/totais/contagens e hashes de todas as linhas comerciais inalterados.
Tempo interno: 0,047 segundo. Tempo total do processo, incluindo inicialização do
Python: 3,337 segundos. Tentativa: 0bc589fa-e2fe-4a2a-8d0b-62dbb9c616e5.

## Integração com CRM

API real local e Streamlit AppTest, somente leitura:

- Clientes: 53 linhas; vendedores: 8; produtos: 15; pedidos: 504.
- Dashboard: 53 clientes, 14 produtos ativos, 1413 unidades em estoque,
  valor estimado R$ 36.634,50.
- Pedido sintético faturado #544 consultado no CRM, com 3 movimentações visíveis.
- Nenhum erro ou exceção nas páginas. Nenhuma linha comercial alterada pelo teste.

A API estava desligada; foi iniciada temporariamente e encerrada ao fim do teste.
A aparência no navegador não foi inspecionada. Para conferência visual, mantenha
a API e o Streamlit abertos e clique em Atualizar dados.

## Comandos de acesso

Na raiz, inicie em terminais separados:

```powershell
.\.venv314\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

```powershell
.\.venv314\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1
```

CRM: http://127.0.0.1:8501. Swagger: http://127.0.0.1:8000/docs.

Não é preciso executar a carga novamente. Ela já está persistida e a reexecução foi
validada. A carga completa de 20.000 pedidos não foi executada e continua dependendo
de autorização própria. Não houve implementação de ETL/DuckDB nem publicação no GitHub.

Relatório estruturado: PILOT_500_RESULT.json.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../../docs/VALIDATION.md.
