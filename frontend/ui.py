import streamlit as st

from frontend.api import ApiError
from frontend.domain import UFS, validar_cliente, validar_produto


def carregar(api, recurso):
    try:
        return api.listar(recurso)
    except ApiError as error:
        st.error(str(error))
        st.info("Inicie a API e use Atualizar dados para tentar novamente.")
        st.stop()


def salvar(api, method, path, dados, mensagem):
    try:
        api.request(method, path, dados)
    except ApiError as error:
        st.error(str(error))
        return
    st.session_state["sucesso"] = mensagem
    st.rerun()


def tabela_produtos(produtos):
    if not produtos:
        st.info("Nenhum produto encontrado.")
        return
    st.dataframe([
        {"ID": p["id_produto"], "Produto": p["nome"], "Peso (g)": p["peso_gramas"],
         "Preço (R$)": p["preco"], "Estoque": p["estoque_atual"],
         "Status": "Ativo" if p["ativo"] else "Inativo"} for p in produtos
    ], hide_index=True, width="stretch",
        column_config={"Preço (R$)": st.column_config.NumberColumn(format="R$ %.2f")})


def formulario_produto(api, produto=None):
    p = produto or {}
    identificador = p.get("id_produto")
    with st.form(f"produto_{identificador or 'novo'}"):
        nome = st.text_input("Nome do produto", value=p.get("nome", ""), max_chars=150)
        a, b = st.columns(2)
        peso = a.number_input("Peso em gramas", min_value=1, value=p.get("peso_gramas", 500), step=1)
        preco = b.number_input("Preço (R$)", min_value=0.01, max_value=9999999999.99,
                               value=float(p.get("preco", 0.01)), step=0.01, format="%.2f")
        estoque = st.number_input("Quantidade em estoque", min_value=0, value=p.get("estoque_atual", 0), step=1)
        ativo = st.checkbox("Produto ativo", value=p.get("ativo", True))
        enviado = st.form_submit_button("Salvar alterações" if produto else "Cadastrar produto", type="primary")
    if enviado:
        dados = {"nome": nome.strip(), "peso_gramas": int(peso), "preco": round(preco, 2),
                 "estoque_atual": int(estoque), "ativo": ativo}
        erro = validar_produto(dados)
        if erro:
            st.error(erro)
        else:
            salvar(api, "PUT" if produto else "POST",
                   f"/produtos/{identificador}" if produto else "/produtos/", dados,
                   "Produto atualizado com sucesso." if produto else "Produto cadastrado com sucesso.")


def formulario_cliente(api, cliente=None):
    c = cliente or {}
    identificador = c.get("id_cliente")
    with st.form(f"cliente_{identificador or 'novo'}"):
        razao = st.text_input("Razão social", value=c.get("razao_social", ""), max_chars=150)
        cnpj = st.text_input("CNPJ", value=c.get("cnpj", ""), max_chars=18,
                             help="14 dígitos, com ou sem pontuação padrão.")
        a, b = st.columns([3, 1])
        cidade = a.text_input("Cidade", value=c.get("cidade", ""), max_chars=100)
        uf = b.selectbox("UF", UFS, index=UFS.index(c.get("uf", "BA")))
        ativo = st.checkbox("Cliente ativo", value=c.get("ativo", True))
        enviado = st.form_submit_button("Salvar alterações" if cliente else "Cadastrar cliente", type="primary")
    if enviado:
        dados = {"razao_social": razao.strip(), "cnpj": cnpj.strip(), "cidade": cidade.strip(),
                 "uf": uf, "ativo": ativo}
        erro = validar_cliente(dados)
        if erro:
            st.error(erro)
        else:
            salvar(api, "PUT" if cliente else "POST",
                   f"/clientes/{identificador}" if cliente else "/clientes/", dados,
                   "Cliente atualizado com sucesso." if cliente else "Cliente cadastrado com sucesso.")
