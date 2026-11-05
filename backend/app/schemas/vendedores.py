import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VendedorEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nome: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=180)
    ativo: bool = True

    @field_validator("email")
    @classmethod
    def email_valido(cls, valor):
        if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", valor):
            raise ValueError("Informe um e-mail válido")
        return valor.lower()


class VendedorSaida(BaseModel):
    id_vendedor: int
    nome: str
    email: str
    ativo: bool
    created_at: datetime
    updated_at: datetime
