# Regras de qualidade

| Camada | Verificações |
| --- | --- |
| API | Campos obrigatórios, preço/peso positivos, estoque não negativo, UF, unicidade de CNPJ |
| Pedidos | Participantes/produtos ativos, quantidade positiva, preço histórico, estado pendente e estoque revalidados |
| PostgreSQL | PK/FK, unicidades, checks, gatilhos created_at/updated_at preservados |
| ETL | Tipos e schema esperados, nulos, chaves duplicadas, referências, status, quantidades e finanças |
| Silver | Quarentena com motivo, relacionamento coerente, total do pedido e itens sem publicação parcial |
| Warehouse | Arquivos publicados e hashes, contratos Silver, FK dimensionais, medidas históricas e reconciliação |
| Gold/BI | Pedidos distintos, Decimal, filtros comuns parametrizados, limites e estados vazios explícitos |

Duplicidades exatas e conflitantes têm tratamento explícito nos testes da ETL; registros rejeitados não viram silenciosamente dados válidos.
Status é normalizado segundo o contrato, preservando a Bronze. Mudança de schema desconhecida aborta publicação.
ETL não corrige estoque operacional. Faturamento e controle transacional pertencem à API/serviços comerciais.

Fonte das regras: etl/quality/, warehouse/quality.py e schemas/serviços do backend.
Resultados dos testes desta revisão constam em FINAL_REVIEW.md; relatórios anteriores são evidência histórica, não testes recém-executados.
