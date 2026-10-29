"""`/api/admin` routes (admin only): watchlist, invites (proxied to Clerk), users and roles.

Clerk Backend API (D37): `GET /v1/invitations`, `POST /v1/invitations` (`email_address`,
`redirect_url`, `notify`), `POST /v1/invitations/{id}/revoke`, with the secret key as a Bearer
token. Creating invitations is limited to 100 per hour per instance.
"""

import datetime as dt
import re
from collections.abc import Iterator
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from desk.api.deps import SessionDep, forget_user, require_role
from desk.config import get_settings
from desk.data.coins import load_coins_yaml, max_watchlist
from desk.models import Coin, User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])

CLERK_API = "https://api.clerk.com/v1"
SYMBOL = re.compile(r"^[A-Z0-9]{2,10}$")


# --- Watchlist --------------------------------------------------------------------------------


class WatchlistCoin(BaseModel):
    symbol: str
    name: str
    source_market: str
    aliases: list[str]
    active: bool
    added_at: dt.datetime


class WatchlistAdd(BaseModel):
    symbol: str = Field(pattern=SYMBOL.pattern)
    name: str = Field(min_length=1, max_length=64)
    aliases: list[Annotated[str, Field(min_length=2, max_length=32)]] = Field(
        default_factory=list, max_length=8
    )


def _watch(c: Coin) -> WatchlistCoin:
    return WatchlistCoin(symbol=c.symbol, name=c.name, source_market=c.source_market,
                         aliases=list(c.aliases), active=c.active, added_at=c.added_at)  # fmt: skip


@router.get("/watchlist", response_model=list[WatchlistCoin], operation_id="listWatchlist")
def list_watchlist(session: SessionDep) -> list[WatchlistCoin]:
    q = select(Coin).where(Coin.is_watchlist, Coin.active).order_by(Coin.symbol)
    return [_watch(c) for c in session.scalars(q)]


@router.post(
    "/watchlist", response_model=WatchlistCoin, status_code=201, operation_id="addWatchlistCoin"
)
def add_watchlist(body: WatchlistAdd, session: SessionDep) -> WatchlistCoin:
    """Add (or re-activate) a coin. The next daily job backfills its candles from Coinbase."""
    core = {c["symbol"] for c in load_coins_yaml() if not c["is_watchlist"]}
    if body.symbol in core:
        raise HTTPException(409, f"{body.symbol} is a core coin")
    active = session.scalar(
        select(func.count()).select_from(Coin).where(Coin.is_watchlist, Coin.active)
    )
    coin = session.get(Coin, body.symbol)
    if (coin is None or not coin.active) and (active or 0) >= max_watchlist():
        raise HTTPException(409, f"the watchlist is full (max {max_watchlist()})")
    aliases = sorted({a.lower() for a in [body.symbol, body.name, *body.aliases]})
    if coin is None:
        coin = Coin(symbol=body.symbol, name=body.name, aliases=aliases,
                    source_market=f"{body.symbol}/USD", is_watchlist=True, active=True)  # fmt: skip
        session.add(coin)
    else:
        coin.name, coin.aliases, coin.active, coin.is_watchlist = body.name, aliases, True, True
    session.commit()
    session.refresh(coin)
    return _watch(coin)


@router.delete(
    "/watchlist/{symbol}", status_code=204, response_class=Response,
    operation_id="removeWatchlistCoin",
)  # fmt: skip
def remove_watchlist(symbol: str, session: SessionDep) -> Response:
    """Deactivate a watchlist coin. Its candle history stays (re-adding resumes it)."""
    coin = session.get(Coin, symbol.upper())
    if coin is None or not coin.is_watchlist:
        raise HTTPException(404, f"{symbol.upper()} is not on the watchlist")
    coin.active = False
    session.commit()
    return Response(status_code=204)


# --- Invites (Clerk) --------------------------------------------------------------------------


class Invite(BaseModel):
    id: str
    email_address: str
    status: str  # pending | accepted | revoked | expired
    created_at: dt.datetime | None


class InviteCreate(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    redirect_url: str | None = Field(default=None, pattern=r"^https?://", max_length=512)


def clerk_client() -> Iterator[httpx.Client]:
    secret = get_settings().clerk_secret_key
    if secret is None:
        raise HTTPException(503, "CLERK_SECRET_KEY is not set")
    with httpx.Client(
        base_url=CLERK_API,
        headers={"Authorization": f"Bearer {secret.get_secret_value()}"},
        timeout=15,
    ) as client:
        yield client


ClerkDep = Annotated[httpx.Client, Depends(clerk_client)]


def _clerk(client: httpx.Client, method: str, path: str, **kwargs: Any) -> Any:
    try:
        r = client.request(method, path, **kwargs)
    except httpx.HTTPError:
        raise HTTPException(502, "Clerk is unreachable") from None
    if r.status_code >= 400:
        try:
            err = (r.json().get("errors") or [{}])[0]
        except ValueError:
            err = {}
        status = {400: 400, 404: 404, 409: 409, 422: 422, 429: 429}.get(r.status_code, 502)
        raise HTTPException(status, err.get("long_message") or err.get("message") or "Clerk error")
    return r.json()


def _invite(raw: dict) -> Invite:
    created = raw.get("created_at")
    return Invite(
        id=raw["id"],
        email_address=raw.get("email_address", ""),
        status=raw.get("status", "pending"),
        created_at=dt.datetime.fromtimestamp(created / 1000, dt.UTC) if created else None,
    )


@router.get("/invites", response_model=list[Invite], operation_id="listInvites")
def list_invites(
    client: ClerkDep, status: Literal["pending", "accepted", "revoked", "expired"] | None = None
) -> list[Invite]:
    params: dict[str, Any] = {"limit": 100}
    if status:
        params["status"] = status
    body = _clerk(client, "GET", "/invitations", params=params)
    items = body.get("data", []) if isinstance(body, dict) else body  # plain or paginated
    return [_invite(i) for i in items]


@router.post("/invites", response_model=Invite, status_code=201, operation_id="createInvite")
def create_invite(body: InviteCreate, client: ClerkDep) -> Invite:
    """Email an invitation (the app is invite-only in Clerk, D29)."""
    payload: dict[str, Any] = {"email_address": str(body.email), "notify": True}
    if body.redirect_url:
        payload["redirect_url"] = body.redirect_url
    return _invite(_clerk(client, "POST", "/invitations", json=payload))


@router.delete("/invites/{invite_id}", response_model=Invite, operation_id="revokeInvite")
def revoke_invite(
    invite_id: Annotated[str, Path(pattern=r"^inv_[A-Za-z0-9]{1,64}$")], client: ClerkDep
) -> Invite:
    return _invite(_clerk(client, "POST", f"/invitations/{invite_id}/revoke"))


# --- Users ------------------------------------------------------------------------------------


class UserOut(BaseModel):
    id: int
    clerk_id: str
    role: str
    created_at: dt.datetime


class RoleUpdate(BaseModel):
    role: Literal["admin", "member"]


def _user(u: User) -> UserOut:
    return UserOut(id=u.id, clerk_id=u.clerk_id, role=u.role, created_at=u.created_at)


@router.get("/users", response_model=list[UserOut], operation_id="listUsers")
def list_users(session: SessionDep) -> list[UserOut]:
    return [_user(u) for u in session.scalars(select(User).order_by(User.id))]


@router.patch("/users/{user_id}", response_model=UserOut, operation_id="updateUserRole")
def update_role(user_id: int, body: RoleUpdate, session: SessionDep) -> UserOut:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "unknown user")
    if body.role == "member":
        if user.clerk_id in get_settings().admin_clerk_ids:
            raise HTTPException(409, "this user is an admin through ADMIN_CLERK_IDS")
        admins = session.scalar(select(func.count()).select_from(User).where(User.role == "admin"))
        if user.role == "admin" and (admins or 0) <= 1:
            raise HTTPException(409, "cannot remove the last admin")
    user.role = body.role
    session.commit()
    forget_user(user.clerk_id)
    return _user(user)
