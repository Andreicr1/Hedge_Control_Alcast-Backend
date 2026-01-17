import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
assert DATABASE_URL, "DATABASE_URL não encontrada no .env"

engine = create_engine(DATABASE_URL)

with engine.begin() as conn:
    conn.execute(
        text(
            "ALTER TABLE alembic_version "
            "ALTER COLUMN version_num TYPE VARCHAR(64)"
        )
    )

print("OK: coluna alembic_version.version_num ajustada para VARCHAR(64)")
