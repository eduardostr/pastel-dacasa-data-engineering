from decimal import Decimal

import pandas as pd

from etl.config.schema import COLUMNS, KEYS, SCHEMAS, SALES_SCHEMA
from etl.load.files import as_table, digest, read_table


def merge_source(root, extraction):
    frames = {}
    import json
    deleted = json.loads((root / extraction["deleted_keys"]).read_text(encoding="utf-8"))
    for table in COLUMNS:
        delta = read_table(root / extraction["bronze"] / (table + ".parquet")).to_pandas(
            integer_object_nulls=True, timestamp_as_object=True)
        if extraction["mode"] == "full":
            frames[table] = delta
            continue
        base = read_table(root / extraction["parent"]["source_state"] / (table + ".parquet")).to_pandas(
            integer_object_nulls=True, timestamp_as_object=True)
        keys = set(delta[KEYS[table]].dropna()).union(int(k) for k in deleted[table])
        base = base.loc[~base[KEYS[table]].isin(keys)]
        frames[table] = pd.concat([base, delta], ignore_index=True)
    return frames


def sales_snapshot(valid, run_id, extracted_at, origin):
    if not valid["itens_pedido"] or not valid["pedidos"]:
        return as_table([], SALES_SCHEMA)
    items = pd.DataFrame(valid["itens_pedido"])[["id_item", "id_pedido", "id_produto", "quantidade",
          "preco_unitario", "desconto", "updated_at"]].rename(columns={"updated_at": "item_updated"})
    orders = pd.DataFrame(valid["pedidos"])
    orders = orders.loc[orders["status"] == "FATURADO", ["id_pedido", "id_cliente", "id_vendedor",
          "status", "data_pedido", "updated_at"]].rename(columns={"updated_at": "order_updated"})
    if orders.empty:
        return as_table([], SALES_SCHEMA)
    joined = items.merge(orders, on="id_pedido", validate="many_to_one")
    for table, key, fields, rename in (
        ("produtos", "id_produto", ["nome", "peso_gramas", "updated_at"], {"nome": "produto", "updated_at": "product_updated"}),
        ("clientes", "id_cliente", ["razao_social", "cnpj", "cidade", "uf", "updated_at"], {"razao_social": "cliente", "updated_at": "customer_updated"}),
        ("vendedores", "id_vendedor", ["nome", "email", "updated_at"], {"nome": "vendedor", "email": "email_vendedor", "updated_at": "seller_updated"}),
    ):
        frame = pd.DataFrame(valid[table])
        joined = joined.merge(frame[[key] + fields].rename(columns=rename), on=key, validate="many_to_one")
    rows, totals = [], {}
    for record in joined.to_dict("records"):
        subtotal = record["quantidade"] * record["preco_unitario"] - record["desconto"]
        record["subtotal"] = subtotal.quantize(Decimal(".01"))
        record["source_updated_at"] = max(record.pop(c) for c in
            ("item_updated", "order_updated", "product_updated", "customer_updated", "seller_updated"))
        totals[record["id_pedido"]] = totals.get(record["id_pedido"], Decimal("0.00")) + subtotal
        rows.append(record)
    for record in rows:
        record["total_pedido"] = totals[record["id_pedido"]].quantize(Decimal(".01"))
        record["_record_hash"] = digest(record)
        record.update({"_run_id": run_id, "_extracted_at": extracted_at, "_source": origin + ".vendas_detalhadas"})
    return as_table(rows, SALES_SCHEMA)


def mutation_counts(old, rows, key):
    previous = {row[key]: row["_record_hash"] for row in old}
    current = {row[key]: row["_record_hash"] for row in rows}
    return {"inserted": sum(k not in previous for k in current),
            "updated": sum(k in previous and previous[k] != v for k, v in current.items()),
            "removed_from_valid": sum(k not in current for k in previous)}
