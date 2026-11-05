-- Executado transacionalmente por backend/migrate.py.
-- Os gatilhos de auditoria existentes permanecem ativos.
ALTER TABLE pedidos DROP CONSTRAINT pedidos_status_check;
UPDATE pedidos SET status = 'PENDENTE' WHERE status = 'ABERTO';
ALTER TABLE pedidos ALTER COLUMN status SET DEFAULT 'PENDENTE';
ALTER TABLE pedidos ADD CONSTRAINT pedidos_status_check
    CHECK (status IN ('PENDENTE', 'FATURADO', 'CANCELADO'));

-- Nullable para preservar movimentações históricas sem pedido associado.
ALTER TABLE movimentacoes_estoque ADD COLUMN id_pedido BIGINT REFERENCES pedidos(id_pedido);
CREATE INDEX idx_movimentacoes_pedido ON movimentacoes_estoque(id_pedido);
CREATE UNIQUE INDEX uq_saida_pedido_produto
    ON movimentacoes_estoque(id_pedido, id_produto)
    WHERE id_pedido IS NOT NULL AND tipo = 'SAIDA';
