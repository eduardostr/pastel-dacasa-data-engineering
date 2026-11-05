# Pastel da Casa — dados sintéticos (Etapa 06)

## Estado atual — Etapa 06.2

A base operacional já tem 1.000 clientes, 30 vendedores, 50 produtos e 20.000
pedidos. A ampliação foi executada pelo usuário e validada, preservando o piloto.
Relatório em [FULL_LOAD_RESULT.md](FULL_LOAD_RESULT.md). Não execute os exemplos
com outra identidade para atingir novamente essas metas; isso adicionaria mais dados.


Gerador local Python/Faker `pt_BR`, com preços e faturamento pelo serviço interno
`backend/app/services/pedidos.py`. Não usa HTTP, não implementa ETL e não altera
configuração da API, Docker Compose ou `.env`.

## Instalação

Na raiz do projeto, com PostgreSQL em execução:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r backend/requirements.txt -r scripts/synthetic_data/requirements.txt
```

Faker está fixado em 40.43.0. A mesma seed exige a mesma versão do Faker e do
gerador para reproduzir o plano. Nenhuma informação foi obtida de pessoas reais:
razões sociais têm identificação sintética, vendedores são equipes fictícias e
e-mails usam o domínio reservado `example.test`. CNPJs são fictícios gerados pelo Faker,
sem consulta ou vinculação a empresas reais.

## Teste pequeno isolado

```powershell
.\.venv314\Scripts\python.exe -m scripts.synthetic_data --isolated --execute --clientes 20 --vendedores 3 --produtos 8 --pedidos 40 --start 2025-11-05 --end 2026-11-05 --seed 42 --batch-size 10
```

O comando cria um schema `test_synthetic_<uuid>`, prepara somente esse ambiente,
gera os dados, valida e repete a execução para verificar idempotência. O schema
é removido ao terminar, inclusive em falhas. Não aparecerão novos clientes ou
pedidos no CRM. É necessária permissão CREATE SCHEMA no PostgreSQL.

Sem `--execute`, qualquer comando apenas apresenta o plano, sem conexão ou escrita
no banco. Sem `--development`, o destino é sempre isolado. Cargas acima de
1.000 pedidos exigem também `--allow-large-load`. Esse parâmetro é uma proteção
adicional; não representa autorização para executar uma carga completa.

## Configuração e identidade

| Parâmetro | Padrão | Significado |
| --- | --- | --- |
| `--clientes` | 1000 | Novos clientes sintéticos |
| `--vendedores` | 30 | Novos vendedores sintéticos |
| `--produtos` | 50 | Novos produtos sintéticos |
| `--pedidos` | 20000 | Novos pedidos históricos |
| `--start`, `--end` | Últimos 12 meses | Intervalo UTC: início inclusivo, fim exclusivo |
| `--seed` | 42 | Seed da geração |
| `--batch-size` | 200 | Tamanho dos lotes/checkpoints |
| `--run-id` | UUID determinístico | Identificador lógico da carga |
| `--log-dir` | `scripts/synthetic_data/logs` | Logs persistentes de cada tentativa |

Datas sem fuso são interpretadas como UTC. O fim padrão é 00:00 UTC do dia atual;
o início é a mesma data do ano anterior, com ajuste para ano bissexto. Para repetir
em outro dia, informe as mesmas datas explicitamente. Datas futuras são rejeitadas.

O `run_id` padrão deriva de volumes, período, seed e versões do gerador/Faker.
O lote não muda esse identificador. Cada tentativa tem um `attempt_id` aleatório.
Mesmo run_id/configuração retoma o progresso ou ignora dados concluídos. Reutilizar
run_id com configuração diferente é erro. Outro run_id significa outra carga,
mesmo usando a mesma seed: não crie IDs novos para retomar uma execução.

O plano de pedidos, itens, status e datas é determinístico. IDs de banco dependem
das sequências existentes; resolução de colisões de CNPJ depende dos dados presentes.
Cadastros confirmados são reutilizados na retomada, sem substituir dados existentes.

## Integridade, estoque e história

- Cada carga cria seus próprios clientes, vendedores e produtos; não utiliza nem
  atualiza cadastros reais ou de outras cargas.
- Aproximadamente 75% dos pedidos são faturados, 15% pendentes e 10% cancelados,
  com arredondamento para inteiros. As datas têm pesos mensais sazonais, com maior
  demanda em dezembro/verão; uma amostra pequena pode não preencher todos os meses.
- Os pedidos têm de um a cinco produtos distintos e quantidades positivas.
- Os preços do catálogo são capturados pelo serviço de pedidos e persistidos nos
  itens. Totais são calculados no backend em NUMERIC/Decimal; não há coluna de total
  a preencher nem valor arbitrário enviado pelo gerador.
- Antes das vendas, cada produto recebe uma ENTRADA igual à demanda faturada prevista
  mais 100 unidades de saldo. Cada entrada é rastreada e não é repetida na retomada.
- O serviço existente faz validações, bloqueios, baixa de estoque e registro de SAIDA.
  Pendentes e cancelados não têm saídas. Faturamento não é reimplementado.
- Criação e finalização são separadas por até 48 horas, respeitando o fim do período.

### Contexto histórico explícito

A migração **004_synthetic_runs.sql** cria tabelas de execução/proveniência
(`synthetic_runs`, `synthetic_records`, `synthetic_objects`) e um gatilho adicional
`zz_synthetic_history`. Nenhum gatilho existente é removido ou desabilitado.

Durante a geração, duas configurações PostgreSQL locais à transação indicam run_id
e relógio histórico. O gatilho adicional registra os INSERTs da carga, atribui suas
datas históricas e só permite UPDATE histórico em registros daquela execução.
Ele rejeita tentativas de alterar registros externos sob esse contexto.
`created_at` é preservado e `updated_at` não retrocede.

O gatilho `trg_updated_at` continua ativo. Sem o contexto, inclusive nas chamadas
normais da API, a auditoria segue usando o horário normal do banco. As configurações
são limpas por commit/rollback, não são aceitas pela API e não alteram registros
preexistentes. Os registros sintéticos criados nesta carga poderão, depois,
ser modificados pela API usando a auditoria normal.

É um mecanismo de demonstração para um banco local confiável, não uma barreira
contra administradores que tenham acesso direto de escrita ao PostgreSQL.

## Carga no banco de desenvolvimento — somente após autorização

A ampliação até 20.000 pedidos foi executada na Etapa 06.2. Os passos abaixo
são referência para novas cargas explicitamente autorizadas. Antes de qualquer
nova execução persistente, primeiro
aplique as migrações versionadas com `backend/migrate.py`. A migração 004 foi testada
em schemas temporários e aplicada ao operacional na Etapa 06.1.

Exemplo de simulação do plano completo (não grava nada):

```powershell
.\.venv314\Scripts\python.exe -m scripts.synthetic_data --development --clientes 1000 --vendedores 30 --produtos 50 --pedidos 20000 --start 2025-11-05 --end 2026-11-05 --seed 42
```

Depois de autorização explícita, as opções de execução são `--execute` e, para
mais de 1.000 pedidos, `--allow-large-load`. Não execute a carga completa
durante a validação desta etapa.

Cadastros e pedidos são persistidos em lotes; uma falha desfaz o lote atual, não
os anteriores. Checkpoint e pedidos são confirmados na mesma transação. Retome
com os mesmos parâmetros/run_id. Há bloqueio consultivo contra duas execuções
simultâneas do mesmo run_id. A carga não exclui registros nem oferece limpeza
automática dos dados persistidos.

Não modifique manualmente registros de uma execução incompleta. Alterações externas
nos dados sintéticos podem fazer a validação/reexecução falhar; o gerador não tenta
sobrescrever correções ou reconstituir registros removidos.

## Logs e validação

Os logs registram início/fim, run_id, attempt_id, lotes, quantidades por tabela,
registros ignorados, erros e duração. `synthetic_runs` mantém configuração,
progresso, estado, relatório e erro da última tentativa. Os logs têm o horário do
host; as datas dos dados são UTC. Falhas deixam log com stack trace e retorno não zero.

A validação verifica volumes/status, datas históricas, itens, saídas por pedido e
saldo por produto = entradas - saídas. FKs e restrições continuam ativas. Os testes
também verificam totais do serviço, reexecução, falha no meio de um lote,
retomada, preservação dos dados externos e comportamento normal da auditoria.

```powershell
.\.venv314\Scripts\python.exe -m unittest discover -s scripts/synthetic_data/tests -v
```

## Performance e limites

Não há milhares de chamadas HTTP: o gerador chama diretamente os serviços e confirma
em lotes. As consultas e os bloqueios do faturamento são preservados. O plano é
mantido em memória, com custo O(pedidos + itens); não é um gerador de streaming
ilimitado. A configuração limita a um milhão de pedidos. Os limites são de proteção,
não uma garantia de capacidade nessa escala. A ampliação de 19.496 pedidos foi medida em 508,270 segundos no ambiente local.
Consulte o relatório da Etapa 06.2; isso não é garantia de duração para outras cargas.

## Resultado da validação de 05/11/2026

Carga isolada de 20 clientes, 3 vendedores, 8 produtos e 40 pedidos, seed 42,
período UTC 05/11/2025 a 05/11/2026:

- 30 FATURADOS, 6 PENDENTES, 4 CANCELADOS.
- 131 itens de pedido.
- 110 movimentações: 8 entradas e 102 saídas.
- Soma dos pedidos: R$ 32.887,29, incluindo todos os status.
- Reexecução: zero novos registros.
- Hashes e contagens das seis tabelas do CRM idênticos antes e depois do teste.
- Schema temporário removido; nenhum dado sintético persistido no CRM.

Relatório resumido: `validation_report.json`.


> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../../docs/VALIDATION.md.
