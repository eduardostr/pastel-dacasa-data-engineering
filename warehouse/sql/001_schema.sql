CREATE TABLE IF NOT EXISTS dw_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
    schema_version INTEGER NOT NULL,
    silver_version VARCHAR NOT NULL,
    silver_run_id VARCHAR NOT NULL,
    silver_fingerprint VARCHAR NOT NULL,
    silver_published_at TIMESTAMPTZ NOT NULL,
    silver_snapshot_at TIMESTAMPTZ NOT NULL,
    source_origin VARCHAR NOT NULL,
    dw_run_id VARCHAR NOT NULL,
    attempt_id VARCHAR NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS dw_runs (
    attempt_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL,
    mode VARCHAR NOT NULL,
    silver_version VARCHAR,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    duration_seconds DOUBLE,
    status VARCHAR NOT NULL,
    message VARCHAR,
    metrics_json VARCHAR,
    validations_json VARCHAR
);
CREATE TABLE IF NOT EXISTS dim_cliente (
    sk_cliente BIGINT PRIMARY KEY,
    id_cliente BIGINT UNIQUE NOT NULL,
    razao_social VARCHAR NOT NULL,
    cnpj VARCHAR NOT NULL,
    cidade VARCHAR NOT NULL,
    uf VARCHAR NOT NULL,
    ativo BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    row_hash VARCHAR NOT NULL,
    presente_na_silver BOOLEAN NOT NULL,
    loaded_version VARCHAR NOT NULL,
    dw_created_at TIMESTAMPTZ NOT NULL,
    dw_updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_produto (
    sk_produto BIGINT PRIMARY KEY,
    id_produto BIGINT UNIQUE NOT NULL,
    nome VARCHAR NOT NULL,
    peso_gramas INTEGER NOT NULL,
    preco_catalogo DECIMAL(12,2) NOT NULL,
    estoque_atual INTEGER NOT NULL,
    ativo BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    row_hash VARCHAR NOT NULL,
    presente_na_silver BOOLEAN NOT NULL,
    loaded_version VARCHAR NOT NULL,
    dw_created_at TIMESTAMPTZ NOT NULL,
    dw_updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_vendedor (
    sk_vendedor BIGINT PRIMARY KEY,
    id_vendedor BIGINT UNIQUE NOT NULL,
    nome VARCHAR NOT NULL,
    email VARCHAR NOT NULL,
    ativo BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    row_hash VARCHAR NOT NULL,
    presente_na_silver BOOLEAN NOT NULL,
    loaded_version VARCHAR NOT NULL,
    dw_created_at TIMESTAMPTZ NOT NULL,
    dw_updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_tempo (
    sk_tempo BIGINT PRIMARY KEY,
    data DATE UNIQUE NOT NULL,
    ano INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    dia INTEGER NOT NULL,
    trimestre INTEGER NOT NULL,
    ano_mes VARCHAR NOT NULL,
    mes_nome VARCHAR NOT NULL,
    dia_semana INTEGER NOT NULL,
    dia_semana_nome VARCHAR NOT NULL,
    fim_de_semana BOOLEAN NOT NULL,
    row_hash VARCHAR NOT NULL,
    presente_na_silver BOOLEAN NOT NULL,
    loaded_version VARCHAR NOT NULL,
    dw_created_at TIMESTAMPTZ NOT NULL,
    dw_updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS fato_vendas (
    id_item BIGINT PRIMARY KEY,
    id_pedido BIGINT NOT NULL,
    id_produto BIGINT NOT NULL,
    id_cliente BIGINT NOT NULL,
    id_vendedor BIGINT NOT NULL,
    sk_cliente BIGINT NOT NULL REFERENCES dim_cliente(sk_cliente),
    sk_produto BIGINT NOT NULL REFERENCES dim_produto(sk_produto),
    sk_vendedor BIGINT NOT NULL REFERENCES dim_vendedor(sk_vendedor),
    sk_tempo BIGINT NOT NULL REFERENCES dim_tempo(sk_tempo),
    data_pedido TIMESTAMPTZ NOT NULL,
    quantidade INTEGER NOT NULL CHECK (quantidade>0),
    preco_unitario DECIMAL(12,2) NOT NULL CHECK (preco_unitario>=0),
    desconto DECIMAL(12,2) NOT NULL CHECK (desconto>=0),
    valor_bruto DECIMAL(38,2) NOT NULL,
    valor_liquido DECIMAL(38,2) NOT NULL CHECK (valor_liquido>=0),
    source_updated_at TIMESTAMPTZ NOT NULL,
    row_hash VARCHAR NOT NULL,
    loaded_version VARCHAR NOT NULL,
    dw_created_at TIMESTAMPTZ NOT NULL,
    dw_updated_at TIMESTAMPTZ NOT NULL
);

