"""Shared FastAPI dependencies: DB session, current user, roles, rate limit, `as_of` (D37).

Every router except health declares `require_role(...)` at router level, so a new route cannot
be left unauthenticated by accident (a test walks every route to check this).
"""

import datetime as dt
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request
from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from desk.api.auth import AuthError, ClerkVerifier, bearer_token
from desk.config import get_settings, load_app_settings
from desk.db import get_engine, session_factory
from desk.models import User

USER_CACHE_SECONDS = 60
ROLE_RANK = {"member": 0, "admin": 1}


# --- Database ---------------------------------------------------------------------------------


@lru_cache
def _engine() -> Engine:
    return get_engine()


@lru_cache
def _sessions() -> sessionmaker[Session]:
    return session_factory(_engine())


def open_session() -> Session:
    return _sessions()()


def get_session() -> Iterator[Session]:
    """A request-scoped session. Created lazily, so `/api/health` works without a database."""
    with open_session() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


# --- Auth -------------------------------------------------------------------------------------


@lru_cache
def get_verifier() -> ClerkVerifier:
    settings = get_settings()
    issuer = settings.clerk_issuer_url
    if issuer is None:
        raise RuntimeError(
            "Clerk is not configured: set CLERK_ISSUER or VITE_CLERK_PUBLISHABLE_KEY"
        )
    return ClerkVerifier(issuer, settings.cors_origins, settings.cors_origin_regex)


@dataclass(frozen=True)
class CurrentUser:
    id: int
    clerk_id: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


_user_cache: dict[str, tuple[float, CurrentUser]] = {}
_user_lock = threading.Lock()


def forget_user(clerk_id: str) -> None:
    """Drop a cached user (after a role change)."""
    with _user_lock:
        _user_cache.pop(clerk_id, None)


def _load_user(session: Session, clerk_id: str) -> CurrentUser:
    """Upsert the user on first sight; ADMIN_CLERK_IDS are (re)promoted to admin."""
    with _user_lock:
        hit = _user_cache.get(clerk_id)
        if hit and hit[0] > time.monotonic():
            return hit[1]
    forced_admin = clerk_id in get_settings().admin_clerk_ids
    # Plain column reads (not ORM objects), so a role changed elsewhere is never stale.
    query = select(User.id, User.role).where(User.clerk_id == clerk_id)
    row = session.execute(query).one_or_none()
    if row is None or (forced_admin and row.role != "admin"):
        stmt = insert(User).values(clerk_id=clerk_id, role="admin" if forced_admin else "member")
        if forced_admin:
            stmt = stmt.on_conflict_do_update(index_elements=["clerk_id"], set_={"role": "admin"})
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=["clerk_id"])
        session.execute(stmt)
        session.commit()
        row = session.execute(query).one()
    current = CurrentUser(id=row.id, clerk_id=clerk_id, role=row.role)
    with _user_lock:
        _user_cache[clerk_id] = (time.monotonic() + USER_CACHE_SECONDS, current)
    return current


def current_user(
    request: Request,
    session: SessionDep,
    verifier: Annotated[ClerkVerifier, Depends(get_verifier)],
    authorization: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> CurrentUser:
    try:
        claims = verifier.verify(bearer_token(authorization))
    except AuthError:
        raise HTTPException(
            401, "not authenticated", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    user = _load_user(session, claims.sub)
    rate_limiter().check(str(user.id))
    request.state.user_id = user.id
    return user


UserDep = Annotated[CurrentUser, Depends(current_user)]


def require_role(role: str) -> Callable[[CurrentUser], CurrentUser]:
    needed = ROLE_RANK[role]

    def check(user: UserDep) -> CurrentUser:
        if ROLE_RANK.get(user.role, -1) < needed:
            raise HTTPException(403, "forbidden")
        return user

    check.__name__ = f"require_{role}"
    return check


# --- Rate limit -------------------------------------------------------------------------------


class RateLimiter:
    """Sliding one-minute window per key. In memory and per instance (D37): with Cloud Run's
    max 2 instances a user can get up to twice the limit."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.per_minute = per_minute
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                retry = max(1, int(hits[0] + 60 - now) + 1)
                raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(retry)})
            hits.append(now)


@lru_cache
def rate_limiter() -> RateLimiter:
    api = load_app_settings().get("api") or {}
    return RateLimiter(int(api.get("rate_limit_per_minute", 120)))


# --- Query params -----------------------------------------------------------------------------


def as_of_param(
    as_of: Annotated[
        dt.date | None,
        Query(description="UTC date; data after it is excluded. Default: the latest data."),
    ] = None,
) -> dt.date | None:
    if as_of is not None and as_of > dt.datetime.now(dt.UTC).date():
        raise HTTPException(422, "as_of is in the future")
    return as_of


AsOfDep = Annotated[dt.date | None, Depends(as_of_param)]
