"""Operações comerciais. O chamador controla commit/rollback da transação."""
from fastapi import HTTPException
from sqlalchemy import text


RESUMO = """
    SELECT p.*, c.razao_social AS cliente, v.nome AS vendedor,
           COALESCE((SELECT SUM(i.quantidade * i.preco_unitario - i.desconto)
                     FROM itens_pedido i WHERE i.id_pedido = p.id_pedido), 0) AS total
    FROM pedidos p
    JOIN clientes c ON c.id_cliente = p.id_cliente
    JOIN vendedores v ON v.id_vendedor = p.id_vendedor
"""


def obter(db, id_pedido):
    pedido = db.execute(text(RESUMO + " WHERE p.id_pedido = :id"), {"id": id_pedido}).mappings().first()
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado")
    itens = db.execute(text("""
        SELECT i.*, pr.nome, (i.quantidade * i.preco_unitario - i.desconto) AS subtotal
        FROM itens_pedido i JOIN produtos pr ON pr.id_produto = i.id_produto
        WHERE i.id_pedido = :id ORDER BY i.id_produto
    """), {"id": id_pedido}).mappings().all()
    return {**pedido, "itens": itens}


def pendente(db, id_pedido):
    pedido = db.execute(text("SELECT * FROM pedidos WHERE id_pedido = :id FOR UPDATE"), {"id": id_pedido}).mappings().first()
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado")
    if pedido["status"] != "PENDENTE":
        raise HTTPException(409, "Somente pedidos pendentes permitem esta operação")
    return pedido


def validar_participantes(db, id_cliente, id_vendedor):
    # Identificadores SQL são constantes internas; valores sempre parametrizados.
    for tabela, chave, identificador, rotulo in [
        ("clientes", "id_cliente", id_cliente, "Cliente"),
        ("vendedores", "id_vendedor", id_vendedor, "Vendedor"),
    ]:
        registro = db.execute(text(f"SELECT ativo FROM {tabela} WHERE {chave} = :id FOR SHARE"), {"id": identificador}).mappings().first()
        if registro is None:
            raise HTTPException(404, f"{rotulo} não encontrado")
        if not registro["ativo"]:
            raise HTTPException(409, f"{rotulo} inativo")


def produto_bloqueado(db, id_produto):
    produto = db.execute(text("SELECT * FROM produtos WHERE id_produto = :id FOR UPDATE"), {"id": id_produto}).mappings().first()
    if produto is None:
        raise HTTPException(404, f"Produto {id_produto} não encontrado")
    if not produto["ativo"]:
        raise HTTPException(409, f"Produto {id_produto} inativo")
    if produto["preco"] <= 0:
        raise HTTPException(409, f"Produto {id_produto} sem preço válido")
    return produto


def inserir_item(db, id_pedido, item, produto):
    db.execute(text("""
        INSERT INTO itens_pedido (id_pedido, id_produto, quantidade, preco_unitario)
        VALUES (:pedido, :produto, :quantidade, :preco)
    """), {"pedido": id_pedido, "produto": item.id_produto,
           "quantidade": item.quantidade, "preco": produto["preco"]})


def criar(db, dados):
    validar_participantes(db, dados.id_cliente, dados.id_vendedor)
    id_pedido = db.execute(text("""
        INSERT INTO pedidos (id_cliente, id_vendedor, status)
        VALUES (:cliente, :vendedor, 'PENDENTE') RETURNING id_pedido
    """), {"cliente": dados.id_cliente, "vendedor": dados.id_vendedor}).scalar_one()
    # Todos os caminhos bloqueiam produtos na mesma ordem para evitar deadlocks.
    for item in sorted(dados.itens, key=lambda i: i.id_produto):
        inserir_item(db, id_pedido, item, produto_bloqueado(db, item.id_produto))
    return obter(db, id_pedido)


def adicionar_item(db, id_pedido, item):
    pedido = pendente(db, id_pedido)
    validar_participantes(db, pedido["id_cliente"], pedido["id_vendedor"])
    produto = produto_bloqueado(db, item.id_produto)
    inserir_item(db, id_pedido, item, produto)
    db.execute(text("UPDATE pedidos SET updated_at = NOW() WHERE id_pedido = :id"), {"id": id_pedido})
    return obter(db, id_pedido)


def faturar(db, id_pedido):
    pedido = pendente(db, id_pedido)
    validar_participantes(db, pedido["id_cliente"], pedido["id_vendedor"])
    itens = db.execute(text("SELECT * FROM itens_pedido WHERE id_pedido = :id ORDER BY id_produto"), {"id": id_pedido}).mappings().all()
    if not itens:
        raise HTTPException(409, "Não é possível faturar pedido sem itens")
    for item in itens:
        produto = produto_bloqueado(db, item["id_produto"])
        if produto["estoque_atual"] < item["quantidade"]:
            raise HTTPException(409, f"Estoque insuficiente para {produto['nome']}")
    for item in itens:
        db.execute(text("""
            UPDATE produtos SET estoque_atual = estoque_atual - :quantidade
            WHERE id_produto = :produto
        """), {"quantidade": item["quantidade"], "produto": item["id_produto"]})
        db.execute(text("""
            INSERT INTO movimentacoes_estoque (id_produto, id_pedido, tipo, quantidade, observacao)
            VALUES (:produto, :pedido, 'SAIDA', :quantidade, :observacao)
        """), {"produto": item["id_produto"], "pedido": id_pedido,
               "quantidade": item["quantidade"], "observacao": f"Faturamento do pedido #{id_pedido}"})
    db.execute(text("UPDATE pedidos SET status = 'FATURADO' WHERE id_pedido = :id"), {"id": id_pedido})
    return obter(db, id_pedido)


def cancelar(db, id_pedido):
    pendente(db, id_pedido)
    db.execute(text("UPDATE pedidos SET status = 'CANCELADO' WHERE id_pedido = :id"), {"id": id_pedido})
    return obter(db, id_pedido)
