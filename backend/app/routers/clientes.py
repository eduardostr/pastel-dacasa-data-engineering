from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers._persistencia import gravar
from app.schemas.clientes import ClienteEntrada, ClienteSaida


router = APIRouter(prefix="/clientes", tags=["Clientes"])
COLUNAS = "id_cliente, razao_social, cnpj, cidade, uf, ativo, created_at, updated_at"


def exigir_cliente(cliente):
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente


@router.get("/", response_model=list[ClienteSaida])
def listar_clientes(db: Session = Depends(get_db)):
    return db.execute(text(f"SELECT {COLUNAS} FROM clientes ORDER BY id_cliente")).mappings().all()


@router.get("/{id_cliente}", response_model=ClienteSaida)
def buscar_cliente(id_cliente: int, db: Session = Depends(get_db)):
    return exigir_cliente(db.execute(
        text(f"SELECT {COLUNAS} FROM clientes WHERE id_cliente = :id_cliente"),
        {"id_cliente": id_cliente},
    ).mappings().first())


@router.post("/", response_model=ClienteSaida, status_code=201)
def cadastrar_cliente(dados: ClienteEntrada, db: Session = Depends(get_db)):
    return gravar(db, f"""
        INSERT INTO clientes (razao_social, cnpj, cidade, uf, ativo)
        VALUES (:razao_social, :cnpj, :cidade, :uf, :ativo)
        RETURNING {COLUNAS}
    """, dados.model_dump(), "Já existe um cliente com esse CNPJ")


@router.put("/{id_cliente}", response_model=ClienteSaida)
def atualizar_cliente(id_cliente: int, dados: ClienteEntrada, db: Session = Depends(get_db)):
    return exigir_cliente(gravar(db, f"""
        UPDATE clientes SET razao_social = :razao_social, cnpj = :cnpj,
            cidade = :cidade, uf = :uf, ativo = :ativo
        WHERE id_cliente = :id_cliente RETURNING {COLUNAS}
    """, {**dados.model_dump(), "id_cliente": id_cliente}, "Já existe um cliente com esse CNPJ"))
