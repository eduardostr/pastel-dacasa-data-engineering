from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers._persistencia import gravar
from app.schemas.vendedores import VendedorEntrada, VendedorSaida


router = APIRouter(prefix="/vendedores", tags=["Vendedores"])


@router.get("/", response_model=list[VendedorSaida])
def listar_vendedores(db: Session = Depends(get_db)):
    return db.execute(text("SELECT * FROM vendedores ORDER BY id_vendedor")).mappings().all()


@router.post("/", response_model=VendedorSaida, status_code=201)
def cadastrar_vendedor(dados: VendedorEntrada, db: Session = Depends(get_db)):
    return gravar(db, """
        INSERT INTO vendedores (nome, email, ativo) VALUES (:nome, :email, :ativo)
        RETURNING *
    """, dados.model_dump(), "Já existe um vendedor com esse e-mail")
