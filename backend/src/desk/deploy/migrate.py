"""Alembic migrations on deploy, against Neon's direct host (D31, D38).

Neon's pooler is PgBouncer in transaction mode, and Neon says migration tools need a direct
connection, so the pooled hostname loses its `-pooler` suffix here. The deploy workflow runs this
as its own step before the new revision goes live; the app never migrates on start.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from desk.db import normalize_url

# src/desk/deploy/migrate.py -> deploy -> desk -> src -> backend
ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def direct_url(url: str) -> str:
    """`ep-x-pooler.region.aws.neon.tech` -> `ep-x.region.aws.neon.tech`; other hosts unchanged."""
    parsed = make_url(normalize_url(url))
    first, dot, rest = (parsed.host or "").partition(".")
    if first.endswith("-pooler"):
        parsed = parsed.set(host=first.removesuffix("-pooler") + dot + rest)
    return parsed.render_as_string(hide_password=False)


def upgrade(url: str, revision: str = "head") -> tuple[str | None, str | None]:
    """Upgrade to `revision` in one transaction; returns the revisions before and after."""
    engine = create_engine(direct_url(url), poolclass=NullPool)
    try:
        with engine.begin() as conn:
            before = MigrationContext.configure(conn).get_current_revision()
            cfg = Config(str(ALEMBIC_INI))
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, revision)
            after = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    return before, after
