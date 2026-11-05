from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProdutoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nome: str = Field(min_length=1, max_length=150)
    peso_gramas: int = Field(gt=0, strict=True)
    preco: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    estoque_atual: int = Field(ge=0, strict=True)
    ativo: bool = True


class ProdutoSaida(BaseModel):
    id_produto: int
    nome: str
    peso_gramas: int
    preco: float
    estoque_atual: int
    ativo: bool
    created_at: datetime
    updated_at: datetime
