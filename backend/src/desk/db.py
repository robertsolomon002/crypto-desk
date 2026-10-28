"""Database engine and sessions (SQLAlchemy 2.0, psycopg v3)."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from desk.config import get_settings


def normalize_url(url: str) -> str:
    """Neon and docker-compose give `postgresql://...`; SQLAlchemy needs the psycopg v3 driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


def get_engine(url: str | None = None) -> Engine:
    if url is None:
        secret = get_settings().database_url
        if secret is None:
            raise RuntimeError("DATABASE_URL is not set (see .env.example)")
        url = secret.get_secret_value()
    return create_engine(normalize_url(url), pool_pre_ping=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
