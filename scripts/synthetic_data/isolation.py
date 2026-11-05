from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
import re

from sqlalchemy import create_engine, text


@contextmanager
def isolated_database(base_engine):
    schema = "test_synthetic_" + uuid4().hex
    if not re.fullmatch(r"test_synthetic_[0-9a-f]{32}", schema):
        raise ValueError("Schema de teste inválido")
    with base_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    target = create_engine(base_engine.url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        root = Path(__file__).resolve().parents[2]
        files = [root / "database/oltp/001_schema.sql"]
        files += sorted((root / "database/migrations").glob("*.sql"))
        with target.begin() as connection:
            with connection.connection.cursor() as cursor:
                for path in files:
                    cursor.execute(path.read_text(encoding="utf-8-sig"))
        yield target, schema
    finally:
        target.dispose()
        # Exclusivamente o schema temporário criado acima, jamais public.
        with base_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
