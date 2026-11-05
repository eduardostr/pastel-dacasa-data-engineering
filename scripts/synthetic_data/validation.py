from decimal import Decimal
from sqlalchemy import text

from .config import parse_date

TABLES = {"clientes": "id_cliente", "vendedores": "id_vendedor", "produtos": "id_produto",
          "pedidos": "id_pedido", "itens_pedido": "id_item", "movimentacoes_estoque": "id_movimentacao"}


def validate(db, config, run_id):
    errors = []
    params = {"run": run_id, "start": parse_date(config.start), "end": parse_date(config.end)}
    for table, pk in TABLES.items():
        invalid = db.execute(text(f"""SELECT count(*) FROM {table} t
            JOIN synthetic_records r ON r.record_id=t.{pk} AND r.table_name=:table AND r.run_id=:run
            WHERE t.created_at < :start OR t.created_at >= :end OR t.updated_at < t.created_at
               OR t.updated_at >= :end"""), {**params, "table": table}).scalar_one()
        if invalid:
            errors.append(f"{table}: {invalid} datas inválidas")
    statuses = dict(db.execute(text("""SELECT p.status,count(*) FROM pedidos p
        JOIN synthetic_objects o ON o.record_id=p.id_pedido AND o.kind='pedidos' AND o.run_id=:run
        GROUP BY p.status"""), params).all())
    billed = round(config.pedidos * .75)
    pending = min(round(config.pedidos * .15), config.pedidos - billed)
    expected = {"FATURADO": billed, "PENDENTE": pending, "CANCELADO": config.pedidos - billed - pending}
    if any(statuses.get(s, 0) != n for s, n in expected.items()):
        errors.append("Distribuição de status divergente")
    for table in ("clientes", "vendedores", "produtos", "pedidos"):
        count = db.execute(text("SELECT count(*) FROM synthetic_objects WHERE run_id=:run AND kind=:kind"),
                           {"run": run_id, "kind": table}).scalar_one()
        if count != getattr(config, table):
            errors.append(f"{table}: esperado {getattr(config, table)}, obtido {count}")

    invalid_items = db.execute(text("""SELECT count(*) FROM pedidos p
        JOIN synthetic_objects o ON o.record_id=p.id_pedido AND o.kind='pedidos' AND o.run_id=:run
        WHERE NOT EXISTS (SELECT 1 FROM itens_pedido i WHERE i.id_pedido=p.id_pedido)
           OR p.data_pedido <> p.created_at
           OR EXISTS (SELECT 1 FROM itens_pedido i
               LEFT JOIN movimentacoes_estoque m ON m.id_pedido=p.id_pedido AND m.id_produto=i.id_produto AND m.tipo='SAIDA'
               WHERE i.id_pedido=p.id_pedido AND (
                  i.quantidade <= 0 OR i.preco_unitario <= 0 OR i.desconto <> 0
                  OR i.created_at <> p.created_at
                  OR (p.status='FATURADO' AND (m.id_movimentacao IS NULL OR m.quantidade<>i.quantidade OR m.data_movimentacao<>p.updated_at))
                  OR (p.status<>'FATURADO' AND m.id_movimentacao IS NOT NULL)))"""), params).scalar_one()
    if invalid_items:
        errors.append(f"{invalid_items} pedidos/itens/movimentações inconsistentes")

    # Saldo = entradas - saídas, restrito aos produtos sintéticos desta execução.
    stock_errors = db.execute(text("""SELECT count(*) FROM produtos p
        JOIN synthetic_objects o ON o.kind='produtos' AND o.record_id=p.id_produto AND o.run_id=:run
        WHERE p.estoque_atual < 0 OR p.estoque_atual <> COALESCE(
            (SELECT SUM(CASE WHEN m.tipo='ENTRADA' THEN m.quantidade ELSE -m.quantidade END)
             FROM movimentacoes_estoque m WHERE m.id_produto=p.id_produto),0)"""), params).scalar_one()
    if stock_errors:
        errors.append(f"{stock_errors} saldos de estoque inválidos")
    totals = db.execute(text("""SELECT count(DISTINCT p.id_pedido), COALESCE(SUM(i.quantidade*i.preco_unitario-i.desconto),0)
        FROM pedidos p JOIN synthetic_objects o ON o.kind='pedidos' AND o.record_id=p.id_pedido AND o.run_id=:run
        JOIN itens_pedido i ON i.id_pedido=p.id_pedido"""), params).one()
    report = {"status_counts": statuses, "orders": totals[0], "order_value": str(totals[1]),
              "errors": errors, "valid": not errors}
    if errors:
        raise ValueError("; ".join(errors))
    return report
