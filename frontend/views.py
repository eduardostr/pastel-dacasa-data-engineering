import streamlit as st

from frontend.domain import filtrar_clientes, filtrar_produtos, indicadores, moeda
from frontend.ui import carregar, formulario_cliente, formulario_produto, salvar, tabela_produtos


def dashboard(api):
    st.title("Visão geral")
    st.caption("Clientes, produtos e estoque em um só lugar.")
    produtos = carregar(api, "produtos")
    clientes = carregar(api, "clientes")
    totais = indicadores(produtos, clientes)
    a, b = st.columns(2)
    a.metric("Clientes cadastrados", totais["clientes"])
    b.metric("Produtos ativos", totais["ativos"])
    c, d = st.columns(2)
    c.metric("Unidades em estoque", totais["estoque"])
    d.metric("Valor estimado do estoque", moeda(totais["valor"]))
    st.caption("Estoque e valor consideram todos os produtos, inclusive inativos. Valor estimado pelo preço cadastrado × quantidade.")
    st.subheader("Catálogo de produtos")
    tabela_produtos(produtos)


def produtos(api):
    st.title("Produtos")
    st.caption("Organize seu catálogo e acompanhe a disponibilidade.")
    registros = carregar(api, "produtos")
    a, b = st.columns([3, 1])
    busca = a.text_input("Pesquisar por nome", placeholder="Digite o nome do produto")
    status = b.selectbox("Status", ["Todos", "Ativos", "Inativos"])
    filtrados = filtrar_produtos(registros, busca, status)
    st.caption(f"{len(filtrados)} de {len(registros)} produtos")
    tabela_produtos(filtrados)
    novo, editar, desativar = st.tabs(["Cadastrar", "Editar", "Desativar"])
    with novo:
        formulario_produto(api)
    with editar:
        if registros:
            por_id = {p["id_produto"]: p for p in registros}
            escolhido = st.selectbox("Produto para editar", list(por_id),
                format_func=lambda id: f"#{id} · {por_id[id]['nome']}")
            formulario_produto(api, por_id[escolhido])
        else:
            st.info("Cadastre um produto para começar.")
    with desativar:
        ativos = {p["id_produto"]: p for p in registros if p["ativo"]}
        if ativos:
            escolhido = st.selectbox("Produto para desativar", list(ativos),
                format_func=lambda id: f"#{id} · {ativos[id]['nome']}")
            with st.form(f"desativar_{escolhido}"):
                st.warning(f"O produto {ativos[escolhido]['nome']} será marcado como inativo. Seu histórico será preservado.")
                confirmar = st.checkbox("Confirmo a desativação deste produto")
                enviar = st.form_submit_button("Desativar produto")
            if enviar:
                if confirmar:
                    salvar(api, "PATCH", f"/produtos/{escolhido}/desativar", None, "Produto desativado com sucesso.")
                else:
                    st.error("Confirme a desativação antes de continuar.")
        else:
            st.info("Nenhum produto ativo para desativar.")


def clientes(api):
    st.title("Clientes")
    st.caption("Mantenha os cadastros comerciais sempre atualizados.")
    registros = carregar(api, "clientes")
    a, b = st.columns([3, 1])
    busca = a.text_input("Pesquisar por razão social ou CNPJ")
    uf = b.selectbox("Filtrar por UF", ["Todas"] + sorted({c["uf"] for c in registros}))
    filtrados = filtrar_clientes(registros, busca, uf)
    st.caption(f"{len(filtrados)} de {len(registros)} clientes")
    if filtrados:
        st.dataframe([{"ID": c["id_cliente"], "Razão social": c["razao_social"],
                       "CNPJ": c["cnpj"], "Cidade": c["cidade"], "UF": c["uf"],
                       "Status": "Ativo" if c["ativo"] else "Inativo"} for c in filtrados],
                     hide_index=True, width="stretch")
    else:
        st.info("Nenhum cliente encontrado.")
    novo, editar = st.tabs(["Cadastrar", "Editar"])
    with novo:
        formulario_cliente(api)
    with editar:
        if registros:
            por_id = {c["id_cliente"]: c for c in registros}
            escolhido = st.selectbox("Cliente para editar", list(por_id),
                format_func=lambda id: f"#{id} · {por_id[id]['razao_social']} · {por_id[id]['cnpj']}")
            formulario_cliente(api, por_id[escolhido])
        else:
            st.info("Cadastre um cliente para começar.")
