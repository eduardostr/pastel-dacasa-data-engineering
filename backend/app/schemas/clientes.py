import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


UFS = frozenset("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


class ClienteEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    razao_social: str = Field(min_length=1, max_length=150)
    cnpj: str
    cidade: str = Field(min_length=1, max_length=100)
    uf: str
    ativo: bool = True

    @field_validator("cnpj")
    @classmethod
    def normalizar_cnpj(cls, valor: str) -> str:
        if re.fullmatch(r"[0-9]{14}", valor):
            return valor
        if re.fullmatch(r"[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}", valor):
            return re.sub(r"[^0-9]", "", valor)
        raise ValueError("CNPJ deve conter 14 dígitos, com ou sem pontuação padrão")

    @field_validator("uf")
    @classmethod
    def normalizar_uf(cls, valor: str) -> str:
        valor = valor.upper()
        if valor not in UFS:
            raise ValueError("UF inválida")
        return valor


class ClienteSaida(BaseModel):
    id_cliente: int
    razao_social: str
    cnpj: str
    cidade: str
    uf: str
    ativo: bool
    created_at: datetime
    updated_at: datetime
