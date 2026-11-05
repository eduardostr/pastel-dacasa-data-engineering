from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.pedidos import ItemEntrada, MovimentacaoSaida, PedidoEntrada, PedidoResumo, PedidoSaida
from app.services import pedidos


router = APIRouter(prefix="/pedidos", tags=["Pedidos e vendas"])
PedidoId = Annotated[int, Path(gt=0, le=9223372036854775807)]


def executar(db, operacao, *args):
    try:
        resultado = operacao(db, *args)
        db.commit()
        return resultado
    except IntegrityError as erro:
        db.rollback()
        if getattr(erro.orig, "pgcode", None) == "23505":
            raise HTTPException(409, "Produto já incluído ou faturamento já registrado") from erro
        raise
    except OperationalError as erro:
        db.rollback()
        if getattr(erro.orig, "pgcode", None) in {"40P01", "40001", "55P03"}:
            raise HTTPException(409, "Operação concorrente; consulte o pedido e tente novamente") from erro
        raise
    except Exception:
        db.rollback()
        raise


@router.get("/", response_model=list[PedidoResumo])
def listar(db: Session = Depends(get_db)):
    return db.execute(text(pedidos.RESUMO + " ORDER BY p.id_pedido DESC")).mappings().all()


@router.post("/", response_model=PedidoSaida, status_code=201)
def criar(dados: PedidoEntrada, db: Session = Depends(get_db)):
    return executar(db, pedidos.criar, dados)


@router.get("/{id_pedido}", response_model=PedidoSaida)
def consultar(id_pedido: PedidoId, db: Session = Depends(get_db)):
    return pedidos.obter(db, id_pedido)


@router.post("/{id_pedido}/itens", response_model=PedidoSaida, status_code=201)
def adicionar_item(id_pedido: PedidoId, dados: ItemEntrada, db: Session = Depends(get_db)):
    return executar(db, pedidos.adicionar_item, id_pedido, dados)


@router.patch("/{id_pedido}/faturar", response_model=PedidoSaida)
def faturar(id_pedido: PedidoId, db: Session = Depends(get_db)):
    return executar(db, pedidos.faturar, id_pedido)


@router.patch("/{id_pedido}/cancelar", response_model=PedidoSaida)
def cancelar(id_pedido: PedidoId, db: Session = Depends(get_db)):
    return executar(db, pedidos.cancelar, id_pedido)


@router.get("/{id_pedido}/movimentacoes", response_model=list[MovimentacaoSaida])
def movimentacoes(id_pedido: PedidoId, db: Session = Depends(get_db)):
    pedidos.obter(db, id_pedido)
    return db.execute(text("""
        SELECT * FROM movimentacoes_estoque WHERE id_pedido = :id ORDER BY id_movimentacao
    """), {"id": id_pedido}).mappings().all()
