import pyarrow as pa

I64, I32, TXT, BOOL = pa.int64(), pa.int32(), pa.string(), pa.bool_()
MONEY, TS = pa.decimal128(12, 2), pa.timestamp("us", tz="UTC")
META = [("_run_id", TXT), ("_extracted_at", TS), ("_source", TXT), ("_record_hash", TXT)]
AUDIT = [("created_at", TS), ("updated_at", TS)]
COLUMNS = {
    "clientes": [("id_cliente", I64), ("razao_social", TXT), ("cnpj", TXT), ("cidade", TXT), ("uf", TXT), ("ativo", BOOL)] + AUDIT,
    "produtos": [("id_produto", I64), ("nome", TXT), ("peso_gramas", I32), ("preco", MONEY), ("estoque_atual", I32), ("ativo", BOOL)] + AUDIT,
    "vendedores": [("id_vendedor", I64), ("nome", TXT), ("email", TXT), ("ativo", BOOL)] + AUDIT,
    "pedidos": [("id_pedido", I64), ("id_cliente", I64), ("id_vendedor", I64), ("status", TXT), ("data_pedido", TS)] + AUDIT,
    "itens_pedido": [("id_item", I64), ("id_pedido", I64), ("id_produto", I64), ("quantidade", I32), ("preco_unitario", MONEY), ("desconto", MONEY)] + AUDIT,
    "movimentacoes_estoque": [("id_movimentacao", I64), ("id_produto", I64), ("tipo", TXT), ("quantidade", I32), ("observacao", TXT), ("data_movimentacao", TS)] + AUDIT + [("id_pedido", I64)],
}
KEYS = {t: cols[0][0] for t, cols in COLUMNS.items()}
OPTIONAL = {"movimentacoes_estoque": {"observacao", "id_pedido"}}
SCHEMAS = {t: pa.schema(cols + META) for t, cols in COLUMNS.items()}
QUARANTINE = {t: pa.schema(cols + META + [("_rejection_reason", TXT)]) for t, cols in COLUMNS.items()}
SALES_COLUMNS = [
    ("id_item", I64), ("id_pedido", I64), ("id_produto", I64), ("id_cliente", I64), ("id_vendedor", I64),
    ("data_pedido", TS), ("status", TXT), ("produto", TXT), ("peso_gramas", I32),
    ("cliente", TXT), ("cnpj", TXT), ("cidade", TXT), ("uf", TXT), ("vendedor", TXT),
    ("email_vendedor", TXT), ("quantidade", I32), ("preco_unitario", MONEY), ("desconto", MONEY),
    ("subtotal", pa.decimal128(38, 2)), ("total_pedido", pa.decimal128(38, 2)),
    ("source_updated_at", TS),
]
SALES_SCHEMA = pa.schema(SALES_COLUMNS + META)
