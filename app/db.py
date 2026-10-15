import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

def _default_database_url() -> str:
    # On Vercel the deployment filesystem is read-only, so SQLite must live in /tmp.
    # /tmp persists for warm function instances; set DATABASE_URL (Postgres) for
    # durable production storage.
    if os.getenv("VERCEL"):
        return "sqlite:////tmp/blogreach.db"
    return "sqlite:///./blogreach.db"


DATABASE_URL = os.getenv("DATABASE_URL", _default_database_url())

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
