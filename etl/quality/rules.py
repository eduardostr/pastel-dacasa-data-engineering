from datetime import datetime, timezone
from decimal import Decimal
import re

import pandas as pd

from etl.config.schema import COLUMNS, KEYS, OPTIONAL

UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
LINKS = [
    ("pedidos", "id_cliente", "clientes"), ("pedidos", "id_vendedor", "vendedores"),
    ("itens_pedido", "id_pedido", "pedidos"), ("itens_pedido", "id_produto", "produtos"),
    ("movimentacoes_estoque", "id_produto", "produtos"),
    ("movimentacoes_estoque", "id_pedido", "pedidos"),
]


def missing(value):
    return value is None or value is pd.NA or value is pd.NaT or (isinstance(value, float) and pd.isna(value))


def plain(value):
    if missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def normalize(table, row):
    row = {k: plain(v) for k, v in row.items()}
    for key, value in list(row.items()):
        if isinstance(value, str) and not key.startswith("_"):
            row[key] = value.strip()
    if table == "clientes":
        row["uf"] = row["uf"].upper() if isinstance(row.get("uf"), str) else row.get("uf")
        value = row.get("cnpj")
        if isinstance(value, str) and re.fullmatch(r"[0-9]{14}|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}", value):
            row["cnpj"] = re.sub(r"[^0-9]", "", value)
    if table == "vendedores" and isinstance(row.get("email"), str):
        row["email"] = row["email"].lower()
    if table == "pedidos" and isinstance(row.get("status"), str):
        row["status"] = {"ABERTO": "PENDENTE"}.get(row["status"].upper(), row["status"].upper())
    if table == "movimentacoes_estoque" and isinstance(row.get("tipo"), str):
        row["tipo"] = row["tipo"].upper()
    for key in ("created_at", "updated_at", "data_pedido", "data_movimentacao", "_extracted_at"):
        if key in row and row[key] is not None:
            try:
                row[key] = pd.to_datetime(row[key], utc=True, errors="raise").to_pydatetime()
            except (ValueError, TypeError, OverflowError):
                pass
    return row


def row_errors(table, row):
    errors = []
    for col, _ in COLUMNS[table]:
        if col not in OPTIONAL.get(table, set()) and missing(row.get(col)):
            errors.append("required:" + col)
        if isinstance(row.get(col), str) and not row[col] and col != "observacao":
            errors.append("empty:" + col)
    for col, _ in COLUMNS[table]:
        value = row.get(col)
        if col.startswith("id_") and not missing(value) and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
            errors.append("invalid_id:" + col)
    for col in ("created_at", "updated_at", "data_pedido", "data_movimentacao"):
        if col in row and not isinstance(row[col], datetime):
            errors.append("invalid_timestamp:" + col)
    if isinstance(row.get("created_at"), datetime) and isinstance(row.get("updated_at"), datetime) and row["updated_at"] < row["created_at"]:
        errors.append("updated_before_created")
    if "ativo" in row and not isinstance(row["ativo"], bool):
        errors.append("invalid_boolean:ativo")
    for col in ("preco", "preco_unitario", "desconto"):
        if col in row:
            value = row[col]
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0 or value != value.quantize(Decimal(".01")):
                errors.append("invalid_money:" + col)
    if table == "clientes":
        if not isinstance(row.get("cnpj"), str) or not re.fullmatch(r"[0-9]{14}", row["cnpj"]):
            errors.append("invalid_cnpj")
        if row.get("uf") not in UFS:
            errors.append("invalid_uf")
    if table == "vendedores" and (not isinstance(row.get("email"), str) or not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", row["email"])):
        errors.append("invalid_email")
    for col in ("quantidade", "peso_gramas"):
        if col in row and (not isinstance(row[col], int) or isinstance(row[col], bool) or row[col] <= 0):
            errors.append("invalid_positive_integer:" + col)
    if table == "produtos":
        if not isinstance(row.get("estoque_atual"), int) or row["estoque_atual"] < 0:
            errors.append("negative_or_invalid_stock")
        if isinstance(row.get("preco"), Decimal) and row["preco"].is_finite() and row["preco"] <= 0:
            errors.append("nonpositive_product_price")
    if table == "pedidos" and row.get("status") not in {"PENDENTE", "FATURADO", "CANCELADO"}:
        errors.append("invalid_status")
    if table == "movimentacoes_estoque" and row.get("tipo") not in {"ENTRADA", "SAIDA"}:
        errors.append("invalid_movement_type")
    if table == "itens_pedido" and all(isinstance(row.get(c), Decimal) for c in ("preco_unitario", "desconto")) and isinstance(row.get("quantidade"), int):
        if row["desconto"].is_finite() and row["preco_unitario"].is_finite() and row["desconto"] > row["preco_unitario"] * row["quantidade"]:
            errors.append("discount_exceeds_gross")
    return errors


def clean_snapshot(frames):
    valid, quarantine = {}, {table: [] for table in COLUMNS}
    originals = {}
    for table in COLUMNS:
        valid[table] = []
        records = frames[table].to_dict("records")
        normalized = [normalize(table, record) for record in records]
        # Guardar o original para rejeições por regras/relacionamentos.
        originals[table] = {}
        candidates = []
        for index, (original, row) in enumerate(zip(records, normalized)):
            originals[table][id(row)] = {k: plain(v) for k, v in original.items()}
            errors = row_errors(table, row)
            if errors:
                quarantine[table].append({**originals[table][id(row)], "_rejection_reason": "|".join(errors)})
            else:
                candidates.append(row)
        by_key = {}
        for row in candidates:
            by_key.setdefault(row[KEYS[table]], []).append(row)
        for group in by_key.values():
            if len(group) == 1:
                valid[table].append(group[0])
                continue
            hashes = {r.get("_record_hash") for r in group}
            group.sort(key=lambda r: r["updated_at"], reverse=True)
            if len(hashes) == 1:
                valid[table].append(group[0])
                rejected = [(row, "exact_duplicate") for row in group[1:]]
            elif group[0]["updated_at"] > group[1]["updated_at"]:
                valid[table].append(group[0])
                rejected = [(row, "superseded_duplicate") for row in group[1:]]
            else:
                rejected = [(row, "ambiguous_duplicate") for row in group]
            for row, reason in rejected:
                quarantine[table].append({**originals[table][id(row)], "_rejection_reason": reason})

    def reject(table, predicate, reason):
        kept = []
        for row in valid[table]:
            if predicate(row):
                quarantine[table].append({**originals[table][id(row)], "_rejection_reason": reason})
            else:
                kept.append(row)
        valid[table] = kept

    # Colisões de chaves naturais após normalização: todas ficam em quarentena.
    for table, fields in (("clientes", ["cnpj"]), ("produtos", ["nome"]), ("vendedores", ["email"]), ("itens_pedido", ["id_pedido", "id_produto"])):
        frame = pd.DataFrame(valid[table])
        if not frame.empty:
            duplicated = frame.duplicated(fields, keep=False)
            bad = set(frame.loc[duplicated, KEYS[table]])
            reject(table, lambda r: r[KEYS[table]] in bad, "duplicate_natural_key")

    def links():
        before = sum(len(v) for v in valid.values())
        for table, field, parent in LINKS:
            allowed = {r[KEYS[parent]] for r in valid[parent]}
            reject(table, lambda r: r.get(field) is not None and r[field] not in allowed, "missing_parent:" + field)
        return before != sum(len(v) for v in valid.values())

    while links():
        pass
    orders = {p["id_pedido"]: p for p in valid["pedidos"]}
    # Nesta etapa, SAIDA vinculada a pedido somente é válida em faturados.
    reject("movimentacoes_estoque", lambda m: m["id_pedido"] is not None and m["tipo"] == "SAIDA" and orders[m["id_pedido"]]["status"] != "FATURADO",
           "output_for_non_billed_order")
    output_rows = [m for m in valid["movimentacoes_estoque"] if m["tipo"] == "SAIDA" and m["id_pedido"] is not None]
    outputs = {}
    for m in output_rows:
        outputs.setdefault((m["id_pedido"], m["id_produto"]), []).append(m)
    invalid_orders = {
        r.get("id_pedido") for r in quarantine["itens_pedido"]
        if r["_rejection_reason"] not in {"exact_duplicate", "superseded_duplicate"}
    }
    with_items = {i["id_pedido"] for i in valid["itens_pedido"]}
    invalid_orders.update(set(orders) - with_items)
    for item in valid["itens_pedido"]:
        if orders[item["id_pedido"]]["status"] == "FATURADO":
            movements = outputs.get((item["id_pedido"], item["id_produto"]), [])
            if len(movements) != 1 or movements[0]["quantidade"] != item["quantidade"]:
                invalid_orders.add(item["id_pedido"])
    # Saída que não corresponde a nenhum item é rejeitada.
    item_keys = {(i["id_pedido"], i["id_produto"]) for i in valid["itens_pedido"]}
    reject("movimentacoes_estoque", lambda m: m["tipo"] == "SAIDA" and m["id_pedido"] is not None and
           (m["id_pedido"], m["id_produto"]) not in item_keys, "output_without_order_item")
    reject("pedidos", lambda p: p["id_pedido"] in invalid_orders, "order_items_or_outputs_inconsistent")
    while links():
        pass
    for table in valid:
        valid[table].sort(key=lambda row: row[KEYS[table]])
    return valid, quarantine
