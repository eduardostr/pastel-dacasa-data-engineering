"""Gerador local; importa o serviço de negócios sem iniciar servidores HTTP."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
