from dataclasses import dataclass
from pathlib import Path
import os
import re

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "data"
    schema: str = "public"
    batch_size: int = 5000
    lookback_seconds: int = 900

    def __post_init__(self):
        object.__setattr__(self, "data_dir", Path(self.data_dir).resolve())
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", self.schema):
            raise ValueError("Schema inválido")
        if self.batch_size < 1 or self.lookback_seconds < 0:
            raise ValueError("Lote deve ser positivo e janela não negativa")


def default_engine():
    load_dotenv(ROOT / ".env")
    explicit_url = os.getenv("ETL_DATABASE_URL")
    password = os.getenv("POSTGRES_PASSWORD")
    if not explicit_url and (not password or password.startswith("SUBSTITUA_")):
        raise RuntimeError("Configure POSTGRES_PASSWORD ou ETL_DATABASE_URL antes de conectar.")
    url = explicit_url or URL.create(
        "postgresql+psycopg2", username=os.getenv("POSTGRES_USER", "pastelflow"),
        password=password,
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "pastelflow_oltp"))
    return create_engine(url, pool_pre_ping=True)
