# Pastel da Casa — validação da Etapa 07

Data: 05/11/2026. Estado: IMPLEMENTADO E VALIDADO EM AMBIENTE ISOLADO.

## Resultado

- 26 testes passaram, zero falhas, duração da suíte final: 119,606 segundos.
- PostgreSQL real em schemas temporários e arquivos Parquet em diretórios temporários.
- Nenhuma FULL persistente do CRM foi executada.
- data/ operacional não foi criada.
- Nenhum schema temporário permaneceu no PostgreSQL.
- Seis gatilhos originais de auditoria do CRM continuam ativos.
- Hashes dos registros comerciais comparados com o inventário anterior à ETL:
  preservados nas seis tabelas, incluindo piloto e carga histórica completa.

Contagens operacionais após os testes: 1000 clientes, 30 vendedores, 50 produtos,
20000 pedidos, 59791 itens e 44984 movimentações.

## Datasets dos testes

Uma fixture FULL representativa produziu:

| Dataset | Linhas |
| --- | ---: |
| clientes | 2 |
| produtos | 2 |
| vendedores | 1 |
| pedidos | 3 |
| itens_pedido | 3 |
| movimentacoes_estoque | 2 |
| vendas_detalhadas | 1 |

Bronze preservou Decimal(12,2), timestamps UTC com microssegundos, nulos opcionais e
metadados da extração. O catálogo tinha preço 100,00, mas o item histórico 9,90:
a venda manteve 9,90 e subtotal 18,80 (2 × 9,90 - 1,00 de desconto).

Foram criados seis arquivos de quarentena por versão, incluindo vazios tipados.
No teste com UF XX, um cliente foi rejeitado com invalid_uf, preservado no Bronze
e na quarentena, e recuperado por uma incremental após a correção da origem isolada.

As versões e datasets de teste foram criados somente em diretórios temporários;
não foram copiados para data/ nem publicados como dados operacionais.

## Cobertura

- FULL em lotes e preservação de tipos.
- Incremental com alterações, sem alterações e inserção retroativa.
- Igualdade de timestamp incluída na janela.
- Commit tardio com timestamp anterior ao watermark.
- Snapshot comum mesmo com commit concorrente entre leituras das tabelas.
- Duplicidades exatas, conflitos ambíguos e quarentena.
- FKs e propagação de rejeições, sem gerar vendas financeiras parciais.
- Nulos, valores monetários, status e normalização.
- Atualizações e inativos, com preço histórico preservado.
- Propagação de alterações de cliente/produto e status para vendas_detalhadas.
- Exclusões apenas nas fixtures, com tombstones auditados.
- Falha durante extração; falha depois da extração/transformação e retomada pelo Bronze.
- Watermark antigo preservado quando não há publicação.
- Recuperação de auditoria após commit do manifesto.
- Reuso idempotente, reprocessamento da execução ativa e rejeição de versão antiga.
- Detecção de Bronze corrompido e schema drift.
- Exclusão de escritores concorrentes.
- CLI sem escrita por padrão e bloqueio de FULL sem --allow-full.

## Arquivos e documentação

Módulos em etl/config, extract, transform, quality, load e control; orquestração em
etl/pipeline.py, CLI em etl/__main__.py e testes em etl/tests.
Dependências em etl/requirements.txt. Regras, arquitetura e comandos em etl/README.md.
README principal e .gitignore foram atualizados para documentação e proteção de dados.

Relatório estruturado: validation_report.json.

## Limitações e pendência

A reconciliação incremental lê todas as linhas para comparar hashes e cobrir
timestamps retroativos/commits tardios. A transformação mantém o snapshot em memória.
Publicação e lock são locais, não distribuídos. Não há benchmark de uma FULL
sobre os 20000 pedidos do CRM, pois essa execução aguarda autorização explícita.

Não houve alteração de API, Streamlit, .env ou Docker Compose. Não houve publicação
no GitHub, implementação de Gold ou DuckDB.


## Atualização posterior: FULL autorizada

A primeira FULL operacional foi autorizada e validada após os testes acima.
Consulte [FULL_RUN_RESULT.md](FULL_RUN_RESULT.md). O conteúdo anterior preserva
o relatório da fase de implementação e testes isolados.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../docs/VALIDATION.md.
