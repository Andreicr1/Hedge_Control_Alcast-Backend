import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {}
# Avoid long hangs on DB outages (psycopg3 supports connect_timeout in seconds).
if str(settings.database_url).startswith("postgresql"):
    connect_args = {"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "10"))}

engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
