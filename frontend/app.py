import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from frontend.analytics.ui import render as analytics
from frontend.api import ApiClient
from frontend.views import clientes, dashboard, produtos
from frontend.vendas import pedidos, vendedores


st.set_page_config(page_title="Pastel da Casa | CRM", page_icon="🥟", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #faf9f6; }
    [data-testid="stSidebar"] { background-color: #123b35; }
    [data-testid="stSidebar"] * { color: #fff8e9; }
    [data-testid="stSidebar"] button * { color: #123b35; }
    [data-testid="stMetric"] { background: #fff; padding: 1.2rem;
        border: 1px solid #e4e6df; border-radius: 12px; margin-bottom: 1rem; }
    h1, h2, h3 { color: #123b35; }
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
        background-color: #17634e; border-color: #17634e; color: white; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🥟 Pastel da Casa")
    st.caption("ALIMENTOS · GESTÃO COMERCIAL")
    st.divider()
    pagina = st.radio("Navegação", ["Dashboard", "Produtos", "Clientes", "Vendedores", "Pedidos", "Inteligência Comercial"])
    st.divider()
    st.button("Atualizar dados", width="stretch")
    st.caption("Seu catálogo e seus clientes, sempre à mão.")

if "sucesso" in st.session_state:
    st.success(st.session_state.pop("sucesso"))

if pagina == "Inteligência Comercial":
    analytics()
else:
    {"Dashboard": dashboard, "Produtos": produtos, "Clientes": clientes,
     "Vendedores": vendedores, "Pedidos": pedidos}[pagina](ApiClient())
