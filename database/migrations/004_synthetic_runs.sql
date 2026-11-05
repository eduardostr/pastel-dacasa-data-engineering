-- Contexto explícito de demonstração. Nenhum gatilho existente é removido.
CREATE TABLE synthetic_runs (
    run_id UUID PRIMARY KEY,
    config JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'FAILED', 'COMPLETED')),
    progress INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error TEXT,
    report JSONB
);
CREATE TABLE synthetic_records (
    run_id UUID NOT NULL REFERENCES synthetic_runs(run_id),
    table_name TEXT NOT NULL,
    record_id BIGINT NOT NULL,
    PRIMARY KEY (table_name, record_id)
);
CREATE INDEX idx_synthetic_records_run ON synthetic_records(run_id, table_name);
CREATE TABLE synthetic_objects (
    run_id UUID NOT NULL REFERENCES synthetic_runs(run_id),
    kind TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    record_id BIGINT NOT NULL,
    PRIMARY KEY (run_id, kind, ordinal),
    UNIQUE (kind, record_id)
);

CREATE FUNCTION synthetic_history_context() RETURNS TRIGGER AS $$
DECLARE
    execution_id UUID;
    historical_time TIMESTAMPTZ;
    key_name TEXT;
    row_id BIGINT;
BEGIN
    IF NULLIF(current_setting('pasteldacasa.synthetic_run', TRUE), '') IS NULL THEN
        RETURN NEW;
    END IF;
    execution_id := current_setting('pasteldacasa.synthetic_run')::UUID;
    historical_time := NULLIF(current_setting('pasteldacasa.synthetic_clock', TRUE), '')::TIMESTAMPTZ;
    IF historical_time IS NULL OR historical_time > clock_timestamp() OR
       NOT EXISTS (SELECT 1 FROM synthetic_runs WHERE run_id = execution_id AND status = 'RUNNING') THEN
        RAISE EXCEPTION 'Contexto histórico sintético inválido';
    END IF;
    key_name := CASE TG_TABLE_NAME
        WHEN 'clientes' THEN 'id_cliente' WHEN 'vendedores' THEN 'id_vendedor'
        WHEN 'produtos' THEN 'id_produto' WHEN 'pedidos' THEN 'id_pedido'
        WHEN 'itens_pedido' THEN 'id_item'
        WHEN 'movimentacoes_estoque' THEN 'id_movimentacao' END;
    row_id := (to_jsonb(NEW)->>key_name)::BIGINT;
    IF TG_OP = 'INSERT' THEN
        INSERT INTO synthetic_records(run_id, table_name, record_id)
        VALUES (execution_id, TG_TABLE_NAME, row_id);
        NEW.created_at := historical_time;
        NEW.updated_at := historical_time;
        IF TG_TABLE_NAME = 'pedidos' THEN
            NEW.data_pedido := historical_time;
        ELSIF TG_TABLE_NAME = 'movimentacoes_estoque' THEN
            NEW.data_movimentacao := historical_time;
        END IF;
    ELSIF EXISTS (SELECT 1 FROM synthetic_records
                  WHERE run_id = execution_id AND table_name = TG_TABLE_NAME AND record_id = row_id) THEN
        NEW.created_at := OLD.created_at;
        NEW.updated_at := GREATEST(OLD.updated_at, historical_time);
    ELSE
        RAISE EXCEPTION 'Contexto sintético não pode alterar registro externo à execução';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- BEFORE triggers são executados alfabeticamente: trg_updated_at permanece ativo;
-- zz_synthetic_history só aplica o relógio explícito a registros da execução.
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['clientes','vendedores','produtos','pedidos','itens_pedido','movimentacoes_estoque'] LOOP
        EXECUTE format('CREATE TRIGGER zz_synthetic_history BEFORE INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION synthetic_history_context()', t);
    END LOOP;
END $$;

