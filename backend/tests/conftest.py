import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from desk.db import normalize_url
from desk.models import Base

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("RUN_LIVE") == "1":
        return
    skip_live = pytest.mark.skip(reason="live test; set RUN_LIVE=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    """A throwaway database on TEST_DATABASE_URL's server, migrated with `alembic upgrade head`.

    Never DATABASE_URL: tests must not touch Neon. Skipped when TEST_DATABASE_URL is unset
    (for example on the Windows CI runner, which has no Linux service containers).
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Postgres test; set TEST_DATABASE_URL (see docker-compose.yml)")
    admin = create_engine(normalize_url(url), isolation_level="AUTOCOMMIT")
    name = f"desk_test_{uuid.uuid4().hex[:8]}"
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(admin.url.set(database=name))
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def pg_sessions(pg_engine: Engine) -> sessionmaker[Session]:
    """A session factory on an emptied test database."""
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with pg_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=pg_engine, expire_on_commit=False)
