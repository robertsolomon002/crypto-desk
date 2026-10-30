"""`/api/me` and `/api/coins` routes."""

import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from desk.api.deps import SessionDep, UserDep, require_role
from desk.api.schemas import Envelope, Source
from desk.config import get_settings, load_app_settings
from desk.data.coins import active_coins
from desk.models import CandleDaily

router = APIRouter(tags=["coins"], dependencies=[Depends(require_role("member"))])


class Features(BaseModel):
    """Which later-version tabs this deployment shows (`config/settings.yaml`, Decision 1)."""

    onchain_macro: bool
    mco: bool  # the tab: `features.mco_tab`, and MCO switched on (`MCO_ENABLED`, Decision 6)
    agent: bool
    signals: bool


class Me(BaseModel):
    clerk_id: str
    role: str
    features: Features


def features() -> Features:
    flags = load_app_settings().get("features", {})
    mco = bool(flags.get("mco_tab")) and bool(flags.get("mco")) and get_settings().mco_enabled
    return Features(onchain_macro=bool(flags.get("onchain_macro")), mco=mco,
                    agent=bool(flags.get("agent")), signals=bool(flags.get("signals")))  # fmt: skip


class CoinOut(BaseModel):
    symbol: str
    name: str
    is_watchlist: bool
    first_date: dt.date | None
    last_date: dt.date | None
    last_close: float | None


@router.get("/me", response_model=Me, operation_id="getMe")
def me(user: UserDep) -> Me:
    return Me(clerk_id=user.clerk_id, role=user.role, features=features())


@router.get("/coins", response_model=Envelope[list[CoinOut]], operation_id="listCoins")
def list_coins(session: SessionDep) -> Envelope[list[CoinOut]]:
    """Active coins (core first, then the watchlist) with their candle coverage."""
    bounds = {
        c: (lo, hi)
        for c, lo, hi in session.execute(
            select(CandleDaily.coin, func.min(CandleDaily.date), func.max(CandleDaily.date))
            .group_by(CandleDaily.coin)
        )
    }  # fmt: skip
    out = []
    for coin in active_coins(session):
        first, last = bounds.get(coin.symbol, (None, None))
        close = None
        if last is not None:
            close = session.scalar(
                select(CandleDaily.close).where(
                    CandleDaily.coin == coin.symbol, CandleDaily.date == last
                )
            )
        out.append(CoinOut(symbol=coin.symbol, name=coin.name, is_watchlist=coin.is_watchlist,
                           first_date=first, last_date=last, last_close=close))  # fmt: skip
    as_of = max((c.last_date for c in out if c.last_date), default=None)
    return Envelope(as_of=as_of, sources=[Source(name="coins", detail="config/coins.yaml + admin")],
                    data=out)  # fmt: skip
