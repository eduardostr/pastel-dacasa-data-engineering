CREATE TABLE IF NOT EXISTS clientes (
 id_cliente BIGSERIAL PRIMARY KEY, razao_social VARCHAR(150) NOT NULL,
 cnpj VARCHAR(14) UNIQUE NOT NULL, cidade VARCHAR(100) NOT NULL, uf CHAR(2) NOT NULL,
 ativo BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS vendedores (
 id_vendedor BIGSERIAL PRIMARY KEY, nome VARCHAR(120) NOT NULL,
 email VARCHAR(180) NOT NULL UNIQUE, ativo BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS produtos (
 id_produto BIGSERIAL PRIMARY KEY, nome VARCHAR(150) NOT NULL UNIQUE,
 peso_gramas INTEGER NOT NULL CHECK (peso_gramas > 0),
 preco NUMERIC(12,2) NOT NULL CHECK (preco >= 0),
 estoque_atual INTEGER NOT NULL DEFAULT 0 CHECK (estoque_atual >= 0),
 ativo BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS pedidos (
 id_pedido BIGSERIAL PRIMARY KEY, id_cliente BIGINT NOT NULL REFERENCES clientes(id_cliente),
 id_vendedor BIGINT NOT NULL REFERENCES vendedores(id_vendedor),
 status VARCHAR(20) NOT NULL DEFAULT 'ABERTO' CHECK (status IN ('ABERTO','FATURADO','CANCELADO')),
 data_pedido TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS itens_pedido (
 id_item BIGSERIAL PRIMARY KEY, id_pedido BIGINT NOT NULL REFERENCES pedidos(id_pedido),
 id_produto BIGINT NOT NULL REFERENCES produtos(id_produto),
 quantidade INTEGER NOT NULL CHECK (quantidade > 0),
 preco_unitario NUMERIC(12,2) NOT NULL CHECK (preco_unitario >= 0),
 desconto NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (desconto >= 0),
 CONSTRAINT ck_desconto_valido CHECK (desconto <= quantidade * preco_unitario),
 UNIQUE(id_pedido,id_produto),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS movimentacoes_estoque (
 id_movimentacao BIGSERIAL PRIMARY KEY, id_produto BIGINT NOT NULL REFERENCES produtos(id_produto),
 tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('ENTRADA','SAIDA')),
 quantidade INTEGER NOT NULL CHECK (quantidade > 0),
 observacao TEXT, data_movimentacao TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['clientes','vendedores','produtos','pedidos','itens_pedido','movimentacoes_estoque'] LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS trg_updated_at ON %I', t);
  EXECUTE format('CREATE TRIGGER trg_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION touch_updated_at()', t);
 END LOOP;
END $$;
CREATE INDEX IF NOT EXISTS idx_pedidos_updated_at ON pedidos(updated_at);
CREATE INDEX IF NOT EXISTS idx_pedidos_data ON pedidos(data_pedido);
CREATE INDEX IF NOT EXISTS idx_itens_pedido ON itens_pedido(id_pedido);
