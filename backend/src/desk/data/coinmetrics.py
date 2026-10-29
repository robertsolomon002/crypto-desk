"""Coin Metrics community API (no key). Stage 1.1 uses `fetch_asset_metric` for the early BTC
price backfill (D20); Stage 1.2 stores the on-chain metrics in `series` as `cm:<COIN>:<metric>`.

Limits and catalog: `docs/DATA_SOURCES.md` (6,000 requests per 20 s; `CapRealUSD` is not free, so
realized cap is derived as market cap / MVRV, D21). A value dated D covers the whole UTC day D,
so only days before today are stored. Missing values come back as null and are skipped (ETH
`HashRate` stops at the Merge, 2022-09-14).
"""

import datetime as dt
from collections.abc import Sequence

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from desk.data import http, series

BASE_URL = "https://community-api.coinmetrics.io/v4"
PAGE_SIZE = 10_000
SOURCE = "coinmetrics"
OVERLAP_DAYS = 3
HISTORY_START = dt.date(2009, 1, 1)

# Assets with free on-chain data (Decision 3: cycle and on-chain tools cover BTC and ETH).
ASSETS = {"BTC": "btc", "ETH": "eth"}
METRICS = ["CapMrktCurUSD", "CapMVRVCur", "SplyCur", "AdrActCnt", "HashRate"]


def make_client() -> httpx.Client:
    return http.make_client(BASE_URL)


def key(coin: str, metric: str) -> str:
    return f"cm:{coin}:{metric}"


def fetch_asset_metrics(
    client: httpx.Client,
    asset: str,
    metrics: Sequence[str],
    start: dt.date,
    end: dt.date | None = None,
) -> dict[str, list[tuple[dt.date, float]]]:
    """Daily values per metric for one asset, oldest first, `start` and `end` inclusive.

    Follows `next_page_url` until the range is exhausted. Missing values are skipped.
    """
    params: dict[str, str | int] | None = {
        "assets": asset,
        "metrics": ",".join(metrics),
        "frequency": "1d",
        "start_time": start.isoformat(),
        "paging_from": "start",
        "page_size": PAGE_SIZE,
    }
    if end is not None:
        params["end_time"] = end.isoformat()
    url = "/timeseries/asset-metrics"
    out: dict[str, list[tuple[dt.date, float]]] = {m: [] for m in metrics}
    while url:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()
        for row in body.get("data", []):
            day = dt.date.fromisoformat(row["time"][:10])
            for m in metrics:
                value = row.get(m)
                if value is not None:
                    out[m].append((day, float(value)))
        url = body.get("next_page_url")
        params = None  # next_page_url already carries the query
    return out


def fetch_asset_metric(
    client: httpx.Client, asset: str, metric: str, start: dt.date, end: dt.date
) -> list[tuple[dt.date, float]]:
    """Daily values of one metric for one asset, oldest first, `start` and `end` inclusive."""
    return fetch_asset_metrics(client, asset, [metric], start, end)[metric]


def update_onchain(
    session: Session, client: httpx.Client, coin: str, now: dt.datetime
) -> dict[str, int]:
    """Fetch new days of every metric for one coin; returns new rows per metric.

    Metrics already stored are refetched from (the coin's latest stored day - 3 days), so a
    metric that stopped (ETH hash rate) does not drag the start back. Metrics with no rows yet
    are fetched from the start of history.
    """
    asset = ASSETS[coin]
    yesterday = now.date() - dt.timedelta(days=1)
    lasts = {m: series.last_date(session, key(coin, m)) for m in METRICS}
    stored = [d for d in lasts.values() if d is not None]
    groups: list[tuple[list[str], dt.date]] = []
    if stored:
        since = max(stored) - dt.timedelta(days=OVERLAP_DAYS)
        groups.append(([m for m in METRICS if lasts[m] is not None], since))
    if new := [m for m in METRICS if lasts[m] is None]:
        groups.append((new, HISTORY_START))

    added: dict[str, int] = {}
    for metrics, since in groups:
        if since > yesterday:
            continue
        for metric, points in fetch_asset_metrics(client, asset, metrics, since, yesterday).items():
            closed = [(d, v) for d, v in points if d <= yesterday]
            added[metric] = series.upsert_series(session, key(coin, metric), closed, SOURCE)
    return added


def load_onchain(
    session: Session,
    coin: str,
    as_of: dt.date | None = None,
    metrics: Sequence[str] = METRICS,
) -> pd.DataFrame:
    """Wide frame of on-chain metrics for `coin` (columns are metric names) up to `as_of`."""
    df = series.load_series(session, [key(coin, m) for m in metrics], as_of=as_of)
    return df.set_axis(list(metrics), axis=1)
