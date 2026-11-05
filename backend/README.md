# API Pastel da Casa

## Pedidos e vendas

Antes de iniciar a API com esta etapa, execute na raiz:

```powershell
.\.venv314\Scripts\python.exe backend/migrate.py
```

Vendedores: GET/POST `/vendedores/`. Pedidos: GET/POST `/pedidos/`,
GET `/pedidos/{id_pedido}`, POST `/pedidos/{id_pedido}/itens`,
PATCH `/pedidos/{id_pedido}/faturar`, PATCH `/pedidos/{id_pedido}/cancelar`
e GET `/pedidos/{id_pedido}/movimentacoes`.

Pedidos são criados como PENDENTE com preços definidos pela API. Somente pendentes
podem receber novos itens, ser faturados ou cancelados. O faturamento utiliza
bloqueios de linha e transação única para status, saldo e movimentações, sem
recalcular preços históricos. Consulte o README principal para exemplos e testes.

Na raiz do projeto, com PostgreSQL em execução:

```powershell
.\.venv314\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv314\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Swagger: http://127.0.0.1:8000/docs

| Recurso | Operações |
| --- | --- |
| `/produtos/` | GET, POST |
| `/produtos/{id_produto}` | GET, PUT |
| `/produtos/{id_produto}/desativar` | PATCH |
| `/clientes/` | GET, POST |
| `/clientes/{id_cliente}` | GET, PUT |

POST retorna 201; dados inválidos retornam 422; registros inexistentes retornam
404; conflitos de nome de produto ou CNPJ retornam 409. PUT substitui os dados
cadastrais: envie todos os campos obrigatórios. `ativo` tem valor padrão `true`.

Exemplo de produto:

```json
{"nome": "Massa Especial 750g", "peso_gramas": 750, "preco": 12.90, "estoque_atual": 20, "ativo": true}
```

Exemplo de cliente fictício:

```json
{"razao_social": "Pastelaria Demonstração", "cnpj": "00000000000003", "cidade": "Salvador", "uf": "ba", "ativo": true}
```

CNPJ aceita 14 dígitos ou pontuação padrão, sendo persistido somente com dígitos.
A validação é de formato, sem cálculo de dígitos verificadores, compatível com
os CNPJs fictícios do seed. UF é validada e convertida para maiúsculas.
A tabela existente de clientes não possui e-mail: esse campo não é aceito nem
persistido. Campos desconhecidos são rejeitados, evitando perda silenciosa de dados.

`created_at` e `updated_at` são retornados com fuso horário, mas não são aceitos
nas entradas. Defaults e gatilhos existentes do PostgreSQL controlam as datas;
nenhuma rota atribui datas manualmente ou exclui registros.

## Testes

```powershell
.\.venv314\Scripts\python.exe -m unittest discover -s backend/tests -v
```

Os testes exercitam HTTP via ASGI com o PostgreSQL real e isolam as gravações
com transações e savepoints. Os registros temporários são desfeitos ao final;
sequências de IDs podem avançar, como é normal no PostgreSQL mesmo com rollback.
