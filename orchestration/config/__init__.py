from dataclasses import dataclass
import os
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "data"
    database: Path = ROOT / "data/warehouse/pastel_da_casa.duckdb"
    schema: str = "public"
    attempts: int = 3
    retry_seconds: float = 10

    def __post_init__(self):
        from etl.config import Settings as ETLSettings
        from warehouse.config import Settings as DWSettings
        object.__setattr__(self, "data_dir", Path(self.data_dir).resolve())
        object.__setattr__(self, "database", Path(self.database).resolve())
        ETLSettings(self.data_dir, self.schema)
        DWSettings(self.data_dir, self.database)
        if not 1 <= self.attempts <= 3 or self.retry_seconds < 0:
            raise ValueError("Use de uma a três tentativas e intervalo não negativo.")

    @classmethod
    def environment(cls):
        return cls(Path(os.getenv("PASTEL_DATA_DIR", ROOT / "data")),
                   Path(os.getenv("PASTEL_DW_PATH", ROOT / "data/warehouse/pastel_da_casa.duckdb")),
                   os.getenv("PASTEL_SOURCE_SCHEMA", "public"),
                   int(os.getenv("PASTEL_MAX_ATTEMPTS", "3")),
                   float(os.getenv("PASTEL_RETRY_SECONDS", "10")))


def identifiers(run_id=None):
    from uuid import uuid5
    parent = UUID(run_id) if run_id else uuid4()
    return {"run_id": str(parent), "etl_run_id": str(uuid5(parent, "etl")),
            "dw_run_id": str(uuid5(parent, "warehouse"))}


def plan(mode="incremental", validate_only=False, dry_run=False, allow_persistent=False, allow_full=False):
    mode = mode.lower()
    if mode not in ("full", "incremental"):
        raise ValueError("Modo inválido.")
    if validate_only and dry_run:
        raise ValueError("dry_run e validate_only são mutuamente exclusivos.")
    if not (dry_run or validate_only) and not allow_persistent:
        raise ValueError("Carga persistente exige autorização e allow_persistent=True.")
    if mode == "full" and not (dry_run or validate_only) and not allow_full:
        raise ValueError("FULL exige autorização adicional e allow_full=True.")
    return {"mode": mode, "dry_run": dry_run, "validate_only": validate_only,
            "steps": ["source", "silver", "gold"] if validate_only else
                     ["source", "etl", "silver", "warehouse", "gold", "finalize"]}
