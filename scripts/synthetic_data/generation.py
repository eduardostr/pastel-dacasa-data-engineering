from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
import random

from faker import Faker

from .config import parse_date


@dataclass(frozen=True)
class Order:
    ordinal: int
    cliente: int
    vendedor: int
    itens: tuple
    status: str
    created: object
    finished: object


def fake_for(config, label, ordinal):
    fake = Faker("pt_BR")
    fake.seed_instance(f"{config.seed}:{label}:{ordinal}")
    return fake


def plan(config):
    start, end = parse_date(config.start), parse_date(config.end)
    rng = random.Random(config.seed)
    # Pico no verão/festas e menor demanda no meio do ano; pesos por dia.
    seasonal = (1.25, 1.15, 1.0, 0.95, 0.9, 0.85, 0.9, 0.95, 1.0, 1.1, 1.25, 1.5)
    days = []
    current = start
    while current < end:
        days.append(current)
        current += timedelta(days=1)
    # Evita viés no último dia parcial.
    weights = [seasonal[d.month - 1] * min(86400, (end - d).total_seconds()) for d in days]
    dates = []
    for day in rng.choices(days, weights=weights, k=config.pedidos):
        available = min(86400, int((end - day).total_seconds()))
        dates.append(day + timedelta(seconds=rng.randrange(max(1, available))))
    dates.sort()
    billed = round(config.pedidos * 0.75)
    pending = round(config.pedidos * 0.15)
    pending = min(pending, config.pedidos - billed)
    statuses = ["FATURADO"] * billed + ["PENDENTE"] * pending
    statuses += ["CANCELADO"] * (config.pedidos - len(statuses))
    rng.shuffle(statuses)
    for index, (created, status) in enumerate(zip(dates, statuses)):
        local = random.Random(f"{config.seed}:order:{index}")
        products = sorted(local.sample(range(config.produtos), local.randint(1, min(5, config.produtos))))
        itens = tuple((pid, local.randint(1, 20)) for pid in products)
        finished = min(created + timedelta(hours=local.randint(1, 48)), end - timedelta(microseconds=1))
        yield Order(index, local.randrange(config.clientes), local.randrange(config.vendedores),
                    itens, status, created, max(created, finished))


def product(config, ordinal, tag):
    fake = fake_for(config, "produto", ordinal)
    weights = (250, 500, 1000, 2000, 5000)
    weight = weights[ordinal % len(weights)]
    flavors = ("Tradicional", "Integral", "Profissional", "Feira", "Artesanal",
               "Disco", "Rolo", "Mini pastel", "Pastel de forno", "Especial")
    price = (Decimal(weight) / 100 * Decimal("1.65") + Decimal(fake.random_int(10, 300)) / 100).quantize(Decimal("0.01"))
    return {"nome": f"Massa {flavors[ordinal % len(flavors)]} {weight}g · Sintético {tag}-{ordinal}",
            "peso_gramas": weight, "preco": price, "estoque_atual": 0, "ativo": True}


def customer(config, ordinal, tag):
    fake = fake_for(config, "cliente", ordinal)
    return {"razao_social": f"Comércio Sintético {tag}-{ordinal} {fake.company()}"[:150],
            "cnpj": fake.cnpj().replace(".", "").replace("/", "").replace("-", ""),
            "cidade": fake.city()[:100], "uf": fake.estado_sigla(), "ativo": True}


def seller(config, ordinal, tag):
    fake = fake_for(config, "vendedor", ordinal)
    return {"nome": f"Equipe Comercial Sintética {ordinal + 1} · {fake.city()}"[:120],
            "email": f"sintetico.{tag}.{ordinal}@example.test", "ativo": True}
