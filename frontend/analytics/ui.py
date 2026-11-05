"""Área analítica independente da API operacional."""
import math
import pandas as pd
import plotly.express as px
import streamlit as st

from frontend.analytics import reader
from frontend.domain import moeda


@st.cache_data(ttl=300, max_entries=32, show_spinner=False)
def cached_options(path, version, refresh):
    return reader.options(path, version)


@st.cache_data(ttl=300, max_entries=64, show_spinner=False)
def cached_summary(path, version, filters, refresh):
    return reader.summary(path, version, filters)


@st.cache_data(ttl=300, max_entries=128, show_spinner=False)
def cached_details(path, version, filters, page, size, refresh):
    return reader.details(path, version, filters, page, size)


def integer(value):
    return f"{int(value):,}".replace(",", ".")


def chart(records, x, y, title, horizontal=False):
    st.subheader(title)
    if not records:
        st.info("Sem registros para este recorte.")
        return
    frame = pd.DataFrame(records)
    # Conversão apenas para renderizar gráficos; cálculos financeiros permanecem Decimal.
    frame[y] = frame[y].map(float)
    id_column = {"produto": "id_produto", "vendedor": "id_vendedor", "cliente": "id_cliente"}.get(x)
    if id_column and id_column in frame:
        frame[x] = frame[x] + " · #" + frame[id_column].astype(str)
    if horizontal:
        fig = px.bar(frame, x=y, y=x, orientation="h", color_discrete_sequence=["#17634e"],
                     hover_data=[c for c in frame if c.startswith("id_")])
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
    else:
        fig = px.bar(frame, x=x, y=y, color_discrete_sequence=["#17634e"])
    fig.update_layout(height=340, margin=dict(l=5,r=5,t=15,b=5),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font_color="#163b35", xaxis_title=None, yaxis_title=None,
                      separators=",.", showlegend=False)
    if y == "faturamento":
        fig.update_layout(**({"xaxis_tickprefix": "R$ "} if horizontal else {"yaxis_tickprefix": "R$ "}))
    st.plotly_chart(fig, width="stretch")


def render():
    st.title("Inteligência Comercial")
    st.caption("Vendas faturadas · valores históricos · Data Warehouse")
    if st.button("Atualizar indicadores", key="analytics_refresh"):
        st.session_state["analytics_revision"] = st.session_state.get("analytics_revision", 0) + 1
    refresh = st.session_state.get("analytics_revision", 0)
    try:
        path = str(reader.database_path())
        version = reader.publication(path)
        opts = cached_options(path, version, refresh)
        st.caption(f"Publicação Silver: {version[0]} · Carga DW (UTC): {version[1]}")
        if opts["bounds"][0] is None:
            st.info("O Data Warehouse está publicado, mas ainda não possui vendas faturadas.")
            return
        with st.container(border=True):
            st.markdown("**Filtros de análise**")
            cols = st.columns(2)
            start = cols[0].date_input("Data inicial", opts["bounds"][0], key="analytics_start")
            end = cols[1].date_input("Data final", opts["bounds"][1], key="analytics_end")
            cols = st.columns(3)
            sellers = {r["id_vendedor"]: f'{r["vendedor"]} · #{r["id_vendedor"]}' for r in opts["sellers"]}
            products = {r["id_produto"]: f'{r["produto"]} · #{r["id_produto"]}' for r in opts["products"]}
            seller = cols[0].selectbox("Vendedor", [None,*sellers], format_func=lambda k: sellers.get(k,"Todos"), key="analytics_seller")
            product = cols[1].selectbox("Produto", [None,*products], format_func=lambda k: products.get(k,"Todos"), key="analytics_product")
            uf = cols[2].selectbox("UF", [None,*opts["ufs"]], format_func=lambda k: k or "Todas", key="analytics_uf")
        filters = reader.Filters(start,end,seller,product,uf)
        data = cached_summary(path,version,filters,refresh)
        k = data["kpi"]
        if not k["itens_faturados"]:
            st.info("Nenhuma venda faturada encontrada para os filtros selecionados.")
            return
        for col, label, value in zip(st.columns(4),
            ["Faturamento total","Pedidos faturados","Ticket médio","Itens faturados"],
            [moeda(k["faturamento_total"]),integer(k["pedidos_faturados"]),moeda(k["ticket_medio"]),integer(k["itens_faturados"])]):
            col.metric(label,value)
        st.caption(f'{integer(k["unidades_vendidas"])} unidades vendidas. Itens = linhas faturadas; pedidos são contados uma única vez. Com filtro de produto, receita e ticket consideram somente os itens selecionados.')
        cols=st.columns(2)
        with cols[0]: chart(data["monthly"],"ano_mes","faturamento","Evolução mensal")
        with cols[1]: chart(data["products"],"produto","unidades","10 produtos mais vendidos",True)
        cols=st.columns(2)
        with cols[0]: chart(data["sellers"],"vendedor","faturamento","Faturamento por vendedor",True)
        with cols[1]: chart(data["ufs"],"uf","faturamento","Faturamento por UF")
        recurring=data["recurrence"][0]
        st.caption(f'{integer(recurring["clientes_recorrentes"])} clientes recorrentes entre {integer(recurring["clientes_com_compras"])} clientes com compras neste recorte.')
        chart(data["recurring"],"cliente","pedidos","Clientes recorrentes · até 20",True)
        st.caption("Recorrência: pelo menos dois pedidos distintos no período e filtros selecionados.")
        st.subheader("Detalhamento das vendas")
        size=st.selectbox("Linhas por página",[25,50,100],index=1,key="analytics_size")
        pages=max(1,math.ceil(k["itens_faturados"]/size))
        # O identificador muda com o recorte para reiniciar a paginação.
        page=int(st.number_input("Página",min_value=1,max_value=pages,value=1,
                                 key=f"analytics_page_{filters}_{size}"))
        detail=cached_details(path,version,filters,page,size,refresh)
        frame=pd.DataFrame(detail)
        for name in ["preco_unitario","desconto","valor_liquido"]:
            if name in frame: frame[name]=frame[name].map(moeda)
        st.dataframe(frame,hide_index=True,width="stretch")
        st.caption(f'Página {page} de {pages} · {integer(k["itens_faturados"])} itens. Datas de venda em UTC.')
    except reader.AnalyticsError as error:
        st.warning(str(error))
        st.info("Consulte frontend/analytics/README.md. A interface não executa cargas ou alterações no DW.")
