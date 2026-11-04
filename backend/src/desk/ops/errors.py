"""Error counts (Stage 8.1, D53): one `app_errors` row per unhandled API exception or failed
agent run, with a place and a kind only. Messages stay out of the database because they can
quote a user's key, a prompt or MCO text; the full traceback goes to the structured log
(`ops/logs.py`), where Cloud Run keeps it for 30 days."""

import datetime as dt
import logging

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from desk.models import AppError

log = logging.getLogger(__name__)


def record(sessions: sessionmaker[Session], where: str, kind: str,
           status: int | None = None) -> None:  # fmt: skip
    """Write one row. Never raises: counting an error must not cause another one."""
    try:
        with sessions.begin() as s:
            s.add(AppError(where=where[:128], kind=kind[:64], status=status))
    except Exception as exc:  # the database may be the thing that is down
        log.warning("could not record an app error: %s", type(exc).__name__)


def counts(session: Session, since: dt.datetime) -> list[tuple[str, str, int, dt.datetime]]:
    """(where, kind, count, last seen) since `since`, most frequent first."""
    n = func.count()
    stmt = (
        select(AppError.where, AppError.kind, n, func.max(AppError.created_at))
        .where(AppError.created_at >= since)
        .group_by(AppError.where, AppError.kind)
        .order_by(n.desc(), AppError.where)
    )
    return [(w, k, int(c), last) for w, k, c, last in session.execute(stmt)]


def prune(session: Session, before: dt.datetime) -> int:
    """Delete rows older than `before`; returns how many."""
    result = session.execute(delete(AppError).where(AppError.created_at < before))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
