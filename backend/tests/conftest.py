import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from desk.agents.llm import make_chat_model as REAL_MAKE_CHAT_MODEL
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


@contextmanager
def _migrated_database() -> Iterator[Engine]:
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


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    with _migrated_database() as engine:
        yield engine


@pytest.fixture
def pg_sessions(pg_engine: Engine) -> sessionmaker[Session]:
    """A session factory on an emptied test database."""
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with pg_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=pg_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def api_engine() -> Iterator[Engine]:
    """A separate database for the API tests, seeded once (seeding takes about 2 s)."""
    from tests import api_fakes

    with _migrated_database() as engine:
        with sessionmaker(bind=engine).begin() as s:
            api_fakes.seed(s)
        yield engine


@pytest.fixture
def api_sessions(api_engine: Engine) -> sessionmaker[Session]:
    """The seeded API database with everything the API can write reset: users other than the
    seeded admin, watchlist changes, the analytics cache and all unseeded tables."""
    from tests import api_fakes

    unseeded = [t.name for t in Base.metadata.sorted_tables if t.name not in api_fakes.SEEDED]
    with api_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(unseeded)} RESTART IDENTITY CASCADE"))
        conn.execute(text("DELETE FROM users WHERE clerk_id <> :a"), {"a": api_fakes.ADMIN})
        conn.execute(text("UPDATE users SET role = 'admin'"))
        conn.execute(text("DELETE FROM coins WHERE symbol <> ALL(:s)"), {"s": api_fakes.COINS})
        conn.execute(text("UPDATE coins SET active = true"))
    return sessionmaker(bind=api_engine, expire_on_commit=False)


@pytest.fixture
def api(api_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch):
    """A TestClient on the seeded API database with Clerk replaced by a local key.

    Patches the session factory (never DATABASE_URL), the verifier, the user cache and the
    rate limiter, so each test starts clean.
    """
    from fastapi.testclient import TestClient

    from desk.api import deps
    from desk.api.main import app
    from tests import api_fakes

    monkeypatch.setattr(deps, "_sessions", lambda: api_sessions)
    monkeypatch.setattr(deps, "_user_cache", {})
    monkeypatch.setattr(deps, "rate_limiter", lambda: deps.RateLimiter(10_000))
    app.dependency_overrides[deps.get_verifier] = api_fakes.verifier
    # No network: Coinbase and the LLM providers are fakes unless a test swaps them. The chat
    # model is a scripted fake too, so no test can reach a provider (or the server key in
    # `.env`) by accident; `real_llm` puts the real factory back for tests that mock HTTP.
    from desk.agents import llm
    from desk.api.routes import admin, agent
    from tests.agent_fakes import ScriptedModel, answer, ask

    script = [ask("list_coins"), answer]  # one tool call, so each answer leaves a snapshot
    monkeypatch.setattr(llm, "make_chat_model", lambda choice, key: ScriptedModel(script=script))

    app.dependency_overrides[admin.exchange_dep] = api_fakes.FakeExchange
    app.dependency_overrides[agent.provider_client] = lambda: httpx.Client(
        transport=api_fakes.provider_transport()
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def real_llm(api, monkeypatch: pytest.MonkeyPatch) -> None:
    """The real model factory (after `api` swapped in a fake); the test must mock HTTP."""
    from desk.agents import llm

    monkeypatch.setattr(llm, "make_chat_model", REAL_MAKE_CHAT_MODEL)
