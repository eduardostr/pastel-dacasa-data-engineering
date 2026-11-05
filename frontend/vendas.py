import re
from decimal import Decimal

import streamlit as st

from frontend.api import ApiError
from frontend.domain import moeda
from frontend.ui import carregar, salvar


def vendedores(api):
    st.title("Vendedores")
    st.caption("Equipe comercial da Pastel da Casa.")
    registros = carregar(api, "vendedores")
    if registros:
        st.dataframe([{"ID": v["id_vendedor"], "Nome": v["nome"], "E-mail": v["email"],
                       "Status": "Ativo" if v["ativo"] else "Inativo"} for v in registros],
                     hide_index=True, width="stretch")
    else:
        st.info("Nenhum vendedor cadastrado.")
    st.subheader("Cadastrar vendedor")
    with st.form("novo_vendedor"):
        nome = st.text_input("Nome do vendedor", max_chars=120)
        email = st.text_input("E-mail do vendedor", max_chars=180)
        enviado = st.form_submit_button("Cadastrar vendedor", type="primary")
    if enviado:
        if not nome.strip():
            st.error("Informe o nome do vendedor.")
        elif not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", email.strip()):
            st.error("Informe um e-mail válido.")
        else:
            salvar(api, "POST", "/vendedores/", {"nome": nome.strip(), "email": email.strip(), "ativo": True},
                   "Vendedor cadastrado com sucesso.")


def novo_pedido(api, clientes, vendedores_lista, produtos):
    clientes_ativos = {c["id_cliente"]: c for c in clientes if c["ativo"]}
    vendedores_ativos = {v["id_vendedor"]: v for v in vendedores_lista if v["ativo"]}
    produtos_ativos = {p["id_produto"]: p for p in produtos if p["ativo"]}
    if not clientes_ativos or not vendedores_ativos or not produtos_ativos:
        st.info("Para criar pedidos, cadastre pelo menos um cliente, vendedor e produto ativos.")
        return
    with st.container(border=True):
        a, b = st.columns(2)
        cliente = a.selectbox("Cliente do pedido", list(clientes_ativos),
            format_func=lambda id: f"#{id} · {clientes_ativos[id]['razao_social']}")
        vendedor = b.selectbox("Vendedor responsável", list(vendedores_ativos),
            format_func=lambda id: f"#{id} · {vendedores_ativos[id]['nome']}")
        selecionados = st.multiselect("Produtos do pedido", list(produtos_ativos),
            format_func=lambda id: f"#{id} · {produtos_ativos[id]['nome']}")
        itens = []
        total = Decimal("0")
        for id in selecionados:
            produto = produtos_ativos[id]
            quantidade = st.number_input(f"Quantidade · {produto['nome']}", min_value=1,
                                         max_value=2147483647, value=1, step=1, key=f"pedido_qtd_{id}")
            subtotal = Decimal(str(produto["preco"])) * quantidade
            total += subtotal
            st.caption(f"Preço unitário: {moeda(produto['preco'])} · Estoque atual: {produto['estoque_atual']} · Subtotal: {moeda(subtotal)}")
            itens.append({"id_produto": id, "quantidade": quantidade})
        st.metric("Total prévio", moeda(total))
        st.caption("Estimativa pelos preços atuais. A API confirma os preços no cadastro. O estoque só é baixado no faturamento.")
        with st.form("criar_pedido"):
            st.caption("Confira cliente, vendedor e quantidades acima antes de criar.")
            enviar = st.form_submit_button("Criar pedido", type="primary")
        if enviar:
            if not itens:
                st.error("Selecione pelo menos um produto.")
            else:
                salvar(api, "POST", "/pedidos/", {"id_cliente": cliente, "id_vendedor": vendedor, "itens": itens},
                       "Pedido criado como PENDENTE. Consulte os valores confirmados abaixo.")


def detalhe_pedido(api, pedido, produtos):
    id = pedido["id_pedido"]
    a, b = st.columns(2)
    a.metric("Status", pedido["status"])
    b.metric("Total confirmado", moeda(pedido["total"]))
    st.write(f"Cliente: {pedido['cliente']} · Vendedor: {pedido['vendedor']}")
    st.caption(f"Criado: {pedido['created_at']} · Atualizado: {pedido['updated_at']}")
    st.dataframe([{"Produto": i["nome"], "Quantidade": i["quantidade"],
                   "Preço unitário (R$)": i["preco_unitario"], "Desconto (R$)": i["desconto"],
                   "Subtotal (R$)": i["subtotal"]} for i in pedido["itens"]],
                 hide_index=True, width="stretch")
    if pedido["status"] == "PENDENTE":
        incluidos = {i["id_produto"] for i in pedido["itens"]}
        disponiveis = {p["id_produto"]: p for p in produtos if p["ativo"] and p["id_produto"] not in incluidos}
        if disponiveis:
            with st.expander("Adicionar outro produto"):
                with st.form(f"adicionar_item_{id}"):
                    produto = st.selectbox("Produto adicional", list(disponiveis),
                        format_func=lambda pid: f"{disponiveis[pid]['nome']} · {moeda(disponiveis[pid]['preco'])}")
                    quantidade = st.number_input("Quantidade adicional", min_value=1, max_value=2147483647, value=1, step=1)
                    adicionar = st.form_submit_button("Adicionar ao pedido")
                if adicionar:
                    salvar(api, "POST", f"/pedidos/{id}/itens", {"id_produto": produto, "quantidade": quantidade},
                           "Produto adicionado ao pedido.")
        a, b = st.columns(2)
        with a:
            with st.form(f"faturar_{id}"):
                st.warning("O faturamento baixa o estoque e preserva os preços do pedido. Não pode ser desfeito nesta etapa.")
                confirma = st.checkbox("Confirmo o faturamento", key=f"confirmar_faturar_{id}")
                faturar = st.form_submit_button("Faturar pedido", type="primary")
            if faturar:
                if confirma:
                    salvar(api, "PATCH", f"/pedidos/{id}/faturar", None, "Pedido faturado. Estoque e movimentações atualizados.")
                else:
                    st.error("Confirme o faturamento antes de continuar.")
        with b:
            with st.form(f"cancelar_{id}"):
                st.warning("Somente pedidos pendentes podem ser cancelados. Não haverá movimentação de estoque.")
                confirma = st.checkbox("Confirmo o cancelamento", key=f"confirmar_cancelar_{id}")
                cancelar = st.form_submit_button("Cancelar pedido")
            if cancelar:
                if confirma:
                    salvar(api, "PATCH", f"/pedidos/{id}/cancelar", None, "Pedido cancelado.")
                else:
                    st.error("Confirme o cancelamento antes de continuar.")
    st.subheader("Movimentações de estoque deste pedido")
    try:
        movimentacoes = api.request("GET", f"/pedidos/{id}/movimentacoes")
    except ApiError as erro:
        st.error(str(erro))
        return
    if movimentacoes:
        st.dataframe([{"Movimentação": m["id_movimentacao"], "Pedido": m["id_pedido"],
                       "Produto (ID)": m["id_produto"], "Tipo": m["tipo"],
                       "Quantidade": m["quantidade"], "Data": m["data_movimentacao"],
                       "Observação": m["observacao"]} for m in movimentacoes],
                     hide_index=True, width="stretch")
        atuais = {p["id_produto"]: p for p in produtos}
        st.caption("Estoque atual dos produtos do pedido")
        st.dataframe([{"Produto": atuais[i["id_produto"]]["nome"],
                       "Estoque atual": atuais[i["id_produto"]]["estoque_atual"]}
                      for i in pedido["itens"] if i["id_produto"] in atuais],
                     hide_index=True, width="stretch")
    else:
        st.info("Nenhuma movimentação registrada para este pedido.")


def pedidos(api):
    st.title("Pedidos e vendas")
    st.caption("Da criação ao faturamento, com histórico e controle de estoque.")
    registros = carregar(api, "pedidos")
    clientes = carregar(api, "clientes")
    vendedores_lista = carregar(api, "vendedores")
    produtos = carregar(api, "produtos")
    with st.expander("Criar novo pedido", expanded=not registros):
        novo_pedido(api, clientes, vendedores_lista, produtos)
    st.subheader("Pedidos cadastrados")
    filtro = st.selectbox("Status do pedido", ["Todos", "PENDENTE", "FATURADO", "CANCELADO"])
    filtrados = [p for p in registros if filtro == "Todos" or p["status"] == filtro]
    if not filtrados:
        st.info("Nenhum pedido encontrado.")
        return
    st.dataframe([{"Pedido": p["id_pedido"], "Cliente": p["cliente"], "Vendedor": p["vendedor"],
                   "Status": p["status"], "Total (R$)": p["total"], "Data": p["data_pedido"]}
                  for p in filtrados], hide_index=True, width="stretch")
    por_id = {p["id_pedido"]: p for p in filtrados}
    id = st.selectbox("Consultar pedido", list(por_id),
        format_func=lambda pid: f"#{pid} · {por_id[pid]['cliente']} · {por_id[pid]['status']}")
    try:
        pedido = api.request("GET", f"/pedidos/{id}")
    except ApiError as erro:
        st.error(str(erro))
        return
    detalhe_pedido(api, pedido, produtos)
