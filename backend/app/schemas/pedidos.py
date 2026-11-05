from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Id = Annotated[int, Field(gt=0, le=9223372036854775807, strict=True)]


class ItemEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_produto: Id
    quantidade: int = Field(gt=0, le=2147483647, strict=True)


class PedidoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_cliente: Id
    id_vendedor: Id
    itens: list[ItemEntrada] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def produtos_unicos(self):
        if len({item.id_produto for item in self.itens}) != len(self.itens):
            raise ValueError("Inclua cada produto uma única vez no pedido")
        return self


class ItemSaida(BaseModel):
    id_item: int
    id_produto: int
    nome: str
    quantidade: int
    preco_unitario: float
    desconto: float
    subtotal: float
    created_at: datetime
    updated_at: datetime


class PedidoResumo(BaseModel):
    id_pedido: int
    id_cliente: int
    cliente: str
    id_vendedor: int
    vendedor: str
    status: Literal["PENDENTE", "FATURADO", "CANCELADO"]
    data_pedido: datetime
    created_at: datetime
    updated_at: datetime
    total: float


class PedidoSaida(PedidoResumo):
    itens: list[ItemSaida]


class MovimentacaoSaida(BaseModel):
    id_movimentacao: int
    id_pedido: int
    id_produto: int
    tipo: str
    quantidade: int
    observacao: str | None
    data_movimentacao: datetime
    created_at: datetime
    updated_at: datetime
