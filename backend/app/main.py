from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine
from app.routers import clientes, pedidos, produtos, vendedores


app = FastAPI(
    title="Pastel da Casa CRM API",
    description="API REST do CRM Pastel da Casa Alimentos",
    version="1.0.0",
)

app.include_router(produtos.router)
app.include_router(clientes.router)
app.include_router(vendedores.router)
app.include_router(pedidos.router)


@app.get("/")
def home():
    return {
        "sistema": "Pastel da Casa CRM",
        "status": "online",
        "versao": "1.0.0",
    }


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    return {
        "status": "healthy",
        "database": "connected",
    }
