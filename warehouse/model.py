DIMENSIONS = {
    "dim_cliente": ("sk_cliente", "id_cliente", "clientes",
                    ["razao_social", "cnpj", "cidade", "uf", "ativo", "created_at", "updated_at"]),
    "dim_produto": ("sk_produto", "id_produto", "produtos",
                    ["nome", "peso_gramas", "preco_catalogo", "estoque_atual", "ativo", "created_at", "updated_at"]),
    "dim_vendedor": ("sk_vendedor", "id_vendedor", "vendedores",
                     ["nome", "email", "ativo", "created_at", "updated_at"]),
    "dim_tempo": ("sk_tempo", "data", "tempo",
                  ["ano", "mes", "dia", "trimestre", "ano_mes", "mes_nome", "dia_semana", "dia_semana_nome", "fim_de_semana"]),
}
FACT_FIELDS = ["id_item", "id_pedido", "id_produto", "id_cliente", "id_vendedor",
               "sk_cliente", "sk_produto", "sk_vendedor", "sk_tempo", "data_pedido",
               "quantidade", "preco_unitario", "desconto", "valor_bruto", "valor_liquido", "source_updated_at"]


def hash_expression(fields):
    return "sha256(to_json(struct_pack(" + ", ".join(f"{field} := {field}" for field in fields) + ")))"


def prepare_dimensions(c):
    c.execute("CREATE OR REPLACE TEMP VIEW v_clientes AS SELECT * FROM s_clientes")
    c.execute("CREATE OR REPLACE TEMP VIEW v_produtos AS SELECT *,preco AS preco_catalogo FROM s_produtos")
    c.execute("CREATE OR REPLACE TEMP VIEW v_vendedores AS SELECT * FROM s_vendedores")
    c.execute("""CREATE OR REPLACE TEMP VIEW v_tempo AS
        SELECT CAST(d AS DATE) AS data, year(d)::INTEGER AS ano, month(d)::INTEGER AS mes,
            day(d)::INTEGER AS dia, quarter(d)::INTEGER AS trimestre, strftime(d,'%Y-%m') AS ano_mes,
            CASE month(d) WHEN 1 THEN 'Janeiro' WHEN 2 THEN 'Fevereiro' WHEN 3 THEN 'Março'
                WHEN 4 THEN 'Abril' WHEN 5 THEN 'Maio' WHEN 6 THEN 'Junho' WHEN 7 THEN 'Julho'
                WHEN 8 THEN 'Agosto' WHEN 9 THEN 'Setembro' WHEN 10 THEN 'Outubro'
                WHEN 11 THEN 'Novembro' ELSE 'Dezembro' END AS mes_nome,
            isodow(d)::INTEGER AS dia_semana,
            CASE isodow(d) WHEN 1 THEN 'Segunda-feira' WHEN 2 THEN 'Terça-feira'
                WHEN 3 THEN 'Quarta-feira' WHEN 4 THEN 'Quinta-feira' WHEN 5 THEN 'Sexta-feira'
                WHEN 6 THEN 'Sábado' ELSE 'Domingo' END AS dia_semana_nome,
            isodow(d) IN (6,7) AS fim_de_semana
        FROM generate_series((SELECT min(data_pedido)::DATE FROM s_pedidos),
                             (SELECT max(data_pedido)::DATE FROM s_pedidos),INTERVAL '1 day') dates(d)
    """)
    for name, (_, key, source, attrs) in DIMENSIONS.items():
        columns = [key] + attrs
        c.execute(f"CREATE OR REPLACE TEMP TABLE st_{name} AS SELECT {', '.join(columns)}, {hash_expression(columns)} AS row_hash FROM v_{source}")


def sync_dimensions(c, version):
    metrics = {}
    for name, (sk, key, _, attrs) in DIMENSIONS.items():
        inserted = c.execute(f"SELECT count(*) FROM st_{name} s LEFT JOIN {name} d USING({key}) WHERE d.{sk} IS NULL").fetchone()[0]
        updated = c.execute(f"SELECT count(*) FROM st_{name} s JOIN {name} d USING({key}) WHERE d.row_hash IS DISTINCT FROM s.row_hash OR NOT d.presente_na_silver").fetchone()[0]
        absent = c.execute(f"SELECT count(*) FROM {name} d WHERE d.presente_na_silver AND NOT EXISTS(SELECT 1 FROM st_{name} s WHERE s.{key}=d.{key})").fetchone()[0]
        assignments = ", ".join(f"{field}=s.{field}" for field in attrs + ["row_hash"])
        c.execute(f"""UPDATE {name} d SET {assignments},presente_na_silver=true,
            loaded_version=?,dw_updated_at=current_timestamp FROM st_{name} s
            WHERE s.{key}=d.{key} AND (d.row_hash IS DISTINCT FROM s.row_hash OR NOT d.presente_na_silver)""", [version])
        c.execute(f"""UPDATE {name} d SET presente_na_silver=false,loaded_version=?,dw_updated_at=current_timestamp
            WHERE d.presente_na_silver AND NOT EXISTS(SELECT 1 FROM st_{name} s WHERE s.{key}=d.{key})""", [version])
        columns = [key] + attrs + ["row_hash"]
        c.execute(f"""INSERT INTO {name} ({sk},{', '.join(columns)},presente_na_silver,loaded_version,dw_created_at,dw_updated_at)
            SELECT (SELECT coalesce(max({sk}),0) FROM {name}) + row_number() OVER (ORDER BY s.{key}),
                {', '.join('s.'+field for field in columns)},true,?,current_timestamp,current_timestamp
            FROM st_{name} s WHERE NOT EXISTS(SELECT 1 FROM {name} d WHERE d.{key}=s.{key})""", [version])
        metrics[name] = {"processed": c.execute(f"SELECT count(*) FROM st_{name}").fetchone()[0],
                         "inserted": inserted, "updated": updated, "marked_absent": absent}
    return metrics


def prepare_fact(c):
    c.execute("""CREATE OR REPLACE TEMP VIEW v_fact AS
        SELECT v.id_item,v.id_pedido,v.id_produto,v.id_cliente,v.id_vendedor,
            dc.sk_cliente,dp.sk_produto,dv.sk_vendedor,dt.sk_tempo,v.data_pedido,
            v.quantidade,v.preco_unitario,v.desconto,
            CAST(CAST(v.quantidade AS DECIMAL(18,0))*v.preco_unitario AS DECIMAL(38,2)) AS valor_bruto,
            CAST(v.subtotal AS DECIMAL(38,2)) AS valor_liquido,v.source_updated_at
        FROM s_vendas_detalhadas v
        JOIN dim_cliente dc ON dc.id_cliente=v.id_cliente AND dc.presente_na_silver
        JOIN dim_produto dp ON dp.id_produto=v.id_produto AND dp.presente_na_silver
        JOIN dim_vendedor dv ON dv.id_vendedor=v.id_vendedor AND dv.presente_na_silver
        JOIN dim_tempo dt ON dt.data=CAST(v.data_pedido AS DATE) AND dt.presente_na_silver
        WHERE v.status='FATURADO'
    """)
    c.execute(f"CREATE OR REPLACE TEMP TABLE st_fato_vendas AS SELECT *,{hash_expression(FACT_FIELDS)} AS row_hash FROM v_fact")


def sync_fact(c, version):
    inserted = c.execute("SELECT count(*) FROM st_fato_vendas s LEFT JOIN fato_vendas f USING(id_item) WHERE f.id_item IS NULL").fetchone()[0]
    updated = c.execute("SELECT count(*) FROM st_fato_vendas s JOIN fato_vendas f USING(id_item) WHERE f.row_hash IS DISTINCT FROM s.row_hash").fetchone()[0]
    removed = c.execute("SELECT count(*) FROM fato_vendas f WHERE NOT EXISTS(SELECT 1 FROM st_fato_vendas s WHERE s.id_item=f.id_item)").fetchone()[0]
    # Exclusivamente a fato analítica; a Silver e o CRM nunca são alterados.
    c.execute("DELETE FROM fato_vendas f WHERE NOT EXISTS(SELECT 1 FROM st_fato_vendas s WHERE s.id_item=f.id_item)")
    assignments = ", ".join(f"{field}=s.{field}" for field in FACT_FIELDS[1:] + ["row_hash"])
    c.execute(f"""UPDATE fato_vendas f SET {assignments},loaded_version=?,dw_updated_at=current_timestamp
        FROM st_fato_vendas s WHERE s.id_item=f.id_item AND f.row_hash IS DISTINCT FROM s.row_hash""", [version])
    columns = FACT_FIELDS + ["row_hash"]
    c.execute(f"""INSERT INTO fato_vendas ({', '.join(columns)},loaded_version,dw_created_at,dw_updated_at)
        SELECT {', '.join('s.'+field for field in columns)},?,current_timestamp,current_timestamp
        FROM st_fato_vendas s WHERE NOT EXISTS(SELECT 1 FROM fato_vendas f WHERE f.id_item=s.id_item)""", [version])
    return {"processed": c.execute("SELECT count(*) FROM st_fato_vendas").fetchone()[0],
            "inserted": inserted, "updated": updated, "removed": removed}
