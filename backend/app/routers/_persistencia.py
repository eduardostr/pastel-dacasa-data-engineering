from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def gravar(db: Session, sql: str, parametros: dict, conflito: str):
    """Confirma a escrita ou desfaz a transação, traduzindo apenas unicidade."""
    try:
        registro = db.execute(text(sql), parametros).mappings().first()
        db.commit()
        return registro
    except IntegrityError as erro:
        db.rollback()
        if getattr(erro.orig, "pgcode", None) == "23505":
            raise HTTPException(status_code=409, detail=conflito) from erro
        raise
    except Exception:
        db.rollback()
        raise
