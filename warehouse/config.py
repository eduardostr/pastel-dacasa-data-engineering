from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    silver_root: Path = ROOT / "data"
    database: Path = ROOT / "data/warehouse/pastel_da_casa.duckdb"

    def __post_init__(self):
        object.__setattr__(self, "silver_root", Path(self.silver_root).resolve())
        object.__setattr__(self, "database", Path(self.database).resolve())
        if self.database.suffix != ".duckdb":
            raise ValueError("Use extensão .duckdb para o banco analítico")
        # Não colocar o banco dentro de uma publicação imutável da ETL.
        for layer in ("bronze", "silver", "quarantine"):
            if self.database.is_relative_to(self.silver_root / layer):
                raise ValueError("O DW não pode ficar dentro dos datasets da ETL")

    @property
    def control_dir(self):
        return self.database.parent / (self.database.name + ".control")
