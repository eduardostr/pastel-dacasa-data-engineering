import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

password = os.getenv("POSTGRES_PASSWORD")
if not password or password.startswith("SUBSTITUA_"):
    raise RuntimeError("Configure POSTGRES_PASSWORD com uma senha local em .env ou no ambiente.")

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg2",
    username=os.getenv("POSTGRES_USER", "pastelflow"),
    password=password,
    host="localhost",
    port=5432,
    database=os.getenv("POSTGRES_DB", "pastelflow_oltp"),
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
