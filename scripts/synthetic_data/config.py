import calendar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID, NAMESPACE_URL, uuid5

from faker import VERSION

GENERATOR_VERSION = 1


def default_period():
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end.replace(year=end.year - 1, day=min(end.day, calendar.monthrange(end.year - 1, end.month)[1]))
    return start.isoformat(), end.isoformat()


def parse_date(value):
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc)


@dataclass(frozen=True)
class Config:
    clientes: int = 1000
    vendedores: int = 30
    produtos: int = 50
    pedidos: int = 20000
    start: str = ""
    end: str = ""
    seed: int = 42
    batch_size: int = 200

    def __post_init__(self):
        if not self.start or not self.end:
            start, end = default_period()
            object.__setattr__(self, "start", self.start or start)
            object.__setattr__(self, "end", self.end or end)
        for name in ("clientes", "vendedores", "produtos", "batch_size"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} deve ser maior que zero")
        if self.pedidos < 0 or self.pedidos > 1_000_000:
            raise ValueError("pedidos deve estar entre 0 e 1.000.000")
        if self.clientes > 1_000_000 or self.vendedores > 100_000 or self.produtos > 100_000:
            raise ValueError("Quantidade de cadastros acima do limite de segurança")
        start, end = parse_date(self.start), parse_date(self.end)
        if not start < end <= datetime.now(timezone.utc):
            raise ValueError("Período inválido: start < end <= agora é obrigatório")
        object.__setattr__(self, "start", start.isoformat())
        object.__setattr__(self, "end", end.isoformat())

    def identity(self):
        # O tamanho do lote não muda os dados lógicos nem o identificador.
        result = asdict(self)
        result.pop("batch_size")
        return {**result, "generator_version": GENERATOR_VERSION, "faker_version": VERSION}

    def run_id(self):
        return str(uuid5(NAMESPACE_URL, json.dumps(self.identity(), sort_keys=True)))

    def fingerprint(self):
        return sha256(json.dumps(self.identity(), sort_keys=True).encode()).hexdigest()

    def resolve_run_id(self, value=None):
        return str(UUID(value)) if value else self.run_id()
