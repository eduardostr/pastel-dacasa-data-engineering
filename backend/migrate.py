"""Aplica migrações pendentes, sem recriar o banco ou executar os seeds."""
from hashlib import sha256
from pathlib import Path

from sqlalchemy import text

from app.database import engine


def migrate():
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(724051903)"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                versao TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        for arquivo in sorted((Path(__file__).resolve().parents[1] / "database/migrations").glob("*.sql")):
            sql = arquivo.read_text(encoding="utf-8")
            checksum = sha256(sql.encode()).hexdigest()
            aplicado = connection.execute(text(
                "SELECT checksum FROM schema_migrations WHERE versao = :versao"
            ), {"versao": arquivo.name}).scalar_one_or_none()
            if aplicado:
                if aplicado != checksum:
                    raise RuntimeError(f"Migração já aplicada foi alterada: {arquivo.name}")
                print(f"Já aplicada: {arquivo.name}")
                continue
            # psycopg2 aceita os comandos SQL do arquivo na mesma transação.
            with connection.connection.cursor() as cursor:
                cursor.execute(sql)
            connection.execute(text(
                "INSERT INTO schema_migrations (versao, checksum) VALUES (:versao, :checksum)"
            ), {"versao": arquivo.name, "checksum": checksum})
            print(f"Aplicada: {arquivo.name}")


if __name__ == "__main__":
    migrate()
