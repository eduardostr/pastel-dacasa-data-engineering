from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers._persistencia import gravar
from app.schemas.produtos import ProdutoEntrada, ProdutoSaida


router = APIRouter(prefix="/produtos", tags=["Produtos"])
COLUNAS = "id_produto, nome, peso_gramas, preco, estoque_atual, ativo, created_at, updated_at"


def exigir_produto(produto):
    if produto is None:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return produto


@router.get("/", response_model=list[ProdutoSaida])
def listar_produtos(db: Session = Depends(get_db)):
    return db.execute(text(f"SELECT {COLUNAS} FROM produtos ORDER BY id_produto")).mappings().all()


@router.get("/{id_produto}", response_model=ProdutoSaida)
def buscar_produto(id_produto: int, db: Session = Depends(get_db)):
    return exigir_produto(db.execute(
        text(f"SELECT {COLUNAS} FROM produtos WHERE id_produto = :id_produto"),
        {"id_produto": id_produto},
    ).mappings().first())


@router.post("/", response_model=ProdutoSaida, status_code=201)
def cadastrar_produto(dados: ProdutoEntrada, db: Session = Depends(get_db)):
    return gravar(db, f"""
        INSERT INTO produtos (nome, peso_gramas, preco, estoque_atual, ativo)
        VALUES (:nome, :peso_gramas, :preco, :estoque_atual, :ativo)
        RETURNING {COLUNAS}
    """, dados.model_dump(), "Já existe um produto com esse nome")


@router.put("/{id_produto}", response_model=ProdutoSaida)
def atualizar_produto(id_produto: int, dados: ProdutoEntrada, db: Session = Depends(get_db)):
    return exigir_produto(gravar(db, f"""
        UPDATE produtos SET nome = :nome, peso_gramas = :peso_gramas,
            preco = :preco, estoque_atual = :estoque_atual, ativo = :ativo
        WHERE id_produto = :id_produto RETURNING {COLUNAS}
    """, {**dados.model_dump(), "id_produto": id_produto}, "Já existe um produto com esse nome"))


@router.patch("/{id_produto}/desativar", response_model=ProdutoSaida)
def desativar_produto(id_produto: int, db: Session = Depends(get_db)):
    return exigir_produto(gravar(db, f"""
        UPDATE produtos SET ativo = FALSE
        WHERE id_produto = :id_produto RETURNING {COLUNAS}
    """, {"id_produto": id_produto}, "Conflito ao desativar produto"))
