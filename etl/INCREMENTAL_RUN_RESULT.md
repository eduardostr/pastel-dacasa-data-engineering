# Pastel da Casa — validações INCREMENTAL e IDEMPOTÊNCIA

**Estado: CONCLUÍDAS E VALIDADAS NO AMBIENTE OPERACIONAL.**

A FULL anterior permanece preservada. Foram publicados três incrementais e testado
o reuso do segundo run. Nenhuma FULL nova foi executada.

## Alteração controlada no CRM

Foi criado pela API um único cliente fictício:
- ID: 1074.
- Razão social: Cliente de Validação ETL — Etapa 07.
- CNPJ: 00000007000001.
- Situação: INATIVO, sem pedidos vinculados.
- Cadastro inicial: Salvador/BA.
- Atualização posterior: Recife/PE.
- created_at preservado; updated_at avançou na atualização.

O cadastro foi mantido no CRM, sem exclusão. Consequentemente, o total de clientes
passou de 1000 para 1001.
Nenhum registro anterior foi alterado: hashes das seis tabelas originais conferidos.

## Execuções

| Teste | Run ID | Duração |
| --- | --- | ---: |
| Inclusão | f025ee10-7313-4d42-bb6d-d50a1854cedb | 36.974 s |
| Atualização | b75a95e1-110a-4ee5-b074-6d34d8d10627 | 37.16 s |
| Sem novas alterações | 0d42d17e-5bea-4501-b912-2b509bd1ae3e | 36.962 s |

### Inclusão

Bronze clientes: 1 linha, source_changed=1. Silver clientes: inserted=1,
updated=0, total=1001, rejected=0.
Demais tabelas sem inclusões/atualizações. O cliente inativo foi preservado.

### Atualização do mesmo cliente

Bronze clientes: 1 linha, source_changed=1. Silver clientes: inserted=0,
updated=1, sem duplicar ID/CNPJ. Cadastro final conferido como Recife/PE.
Datas de auditoria do teste conferidas e demais registros anteriores preservados.

### Reexecução da mesma carga

Mesmo run_id de atualização reutilizou a mesma versão: True.
Duração da verificação/reuso: 0.106 s.
Nenhuma nova extração, versão ou avanço de watermark nessa repetição.

### Novo incremental sem alterações

As sete tabelas Silver, incluindo vendas_detalhadas, tiveram inserted=0,
updated=0 e removed_from_valid=0.
A linha recente de cliente pode ser extraída novamente por pertencer à janela
inclusiva; isso não representa alteração indevida nem duplicação na Silver.

## Estado final

- Clientes: 1001.
- Produtos: 50.
- Vendedores: 30.
- Pedidos: 20000.
- Itens: 59791.
- Movimentações: 44984.
- vendas_detalhadas: 44939 linhas.
- Valor faturado: R$ 14.420.828,23, sem alteração.
- Quarentena: zero registros.
- Publicação ativa: 30f2e92e-d92e-4df9-b303-5e2e43e79bea.
- Run ativo: 0d42d17e-5bea-4501-b912-2b509bd1ae3e.
- Watermarks e referências atualizados somente após publicação validada.

## Processamento incremental e limites

A Bronze recebeu as linhas novas/alteradas e os candidatos da janela de segurança.
O pipeline atual continua lendo as linhas da origem para reconciliação por hash
e revalidando a Silver completa, como documentado em etl/README.md. Portanto, não
se deve interpretar o teste como prova de CDC ou processamento físico exclusivo
de uma única linha. As durações acima incluem essa reconciliação/transformação.

A API foi usada para o cadastro e a atualização; a extração ETL permaneceu somente
leitura. A API iniciada temporariamente pelo teste foi encerrada ao final, caso
não houvesse uma instância existente. O teste não fez inspeção visual do navegador.

Não é necessário executar novamente esses comandos para concluir a validação.
Os três testes principais da Etapa 07 estão concluídos: FULL, INCREMENTAL e
IDEMPOTÊNCIA. Não houve implementação de Gold/DuckDB ou publicação no GitHub.

Relatório estruturado: INCREMENTAL_RUN_RESULT.json.

> Arquivos JSON de resultados citados são artefatos locais não distribuídos. O alcance da validação está resumido em ../docs/VALIDATION.md.
