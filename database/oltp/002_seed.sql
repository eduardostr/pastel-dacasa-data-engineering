INSERT INTO clientes (razao_social, cnpj, cidade, uf) VALUES
 ('Pastelaria Exemplo LTDA','00000000000001','Salvador','BA'),
 ('Mercado Modelo LTDA','00000000000002','Lauro de Freitas','BA')
ON CONFLICT (cnpj) DO NOTHING;
INSERT INTO vendedores (nome,email) VALUES
 ('Ana Souza','ana@example.test'),('Bruno Lima','bruno@example.test')
ON CONFLICT (email) DO NOTHING;
INSERT INTO produtos (nome,peso_gramas,preco,estoque_atual) VALUES
 ('Massa Tradicional 500g',500,8.90,200),
 ('Massa Profissional 1kg',1000,15.90,100),
 ('Massa para Feira 2kg',2000,27.90,80)
ON CONFLICT (nome) DO NOTHING;
