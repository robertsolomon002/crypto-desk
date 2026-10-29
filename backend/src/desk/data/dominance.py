"""BTC and ETH dominance from CoinGecko Demo (Stage 1.2), stored as `dominance:btc|eth`.

The Demo plan has no dominance history (`/global/market_cap_chart` is PRO only, D23), so this
records a daily snapshot from `/global` (`data.market_cap_percentage`, in percent). The row's date
is the UTC day of `data.updated_at`; a later run on the same day overwrites it, so each day keeps
its latest snapshot. The key is sent in the `x-cg-demo-api-key` header.
"""

import datetime as dt

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from desk.data import http, series

BASE_URL = "https://api.coingecko.com/api/v3"
SOURCE = "coingecko"
COINS = ["btc", "eth"]


def key(coin: str) -> str:
    return f"dominance:{coin}"


def make_client(api_key: str) -> httpx.Client:
    return http.make_client(BASE_URL, headers={"x-cg-demo-api-key": api_key})


def parse_global(body: dict) -> tuple[dt.date, dict[str, float]]:
    data = body["data"]
    day = dt.datetime.fromtimestamp(int(data["updated_at"]), tz=dt.UTC).date()
    pct = data["market_cap_percentage"]
    return day, {c: float(pct[c]) for c in COINS if c in pct}


def update(session: Session, client: httpx.Client) -> dict[str, int]:
    """Store today's snapshot; returns new rows per coin (0 when the day was already stored)."""
    resp = client.get("/global")
    resp.raise_for_status()
    day, values = parse_global(resp.json())
    return {c: series.upsert_series(session, key(c), [(day, v)], SOURCE) for c, v in values.items()}


def load_dominance(session: Session, as_of: dt.date | None = None) -> pd.DataFrame:
    """Daily dominance snapshots in percent (columns `btc`, `eth`) up to `as_of`."""
    df = series.load_series(session, [key(c) for c in COINS], as_of=as_of)
    return df.set_axis(COINS, axis=1)
