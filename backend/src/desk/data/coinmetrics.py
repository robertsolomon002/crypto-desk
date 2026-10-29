"""Coin Metrics community API (no key). Stage 1.1 uses `fetch_asset_metric` for the early BTC
price backfill (D20); Stage 1.2 adds the on-chain metrics into `series`.

Limits and catalog: `docs/DATA_SOURCES.md` (6,000 requests per 20 s; `CapRealUSD` is not free).
"""

import datetime as dt

import httpx

BASE_URL = "https://community-api.coinmetrics.io/v4"
USER_AGENT = "crypto-desk/1.1 (+https://github.com/robertsolomon002/crypto-desk)"
PAGE_SIZE = 10_000


def make_client() -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(30.0),
        transport=httpx.HTTPTransport(retries=3),
    )


def fetch_asset_metric(
    client: httpx.Client, asset: str, metric: str, start: dt.date, end: dt.date
) -> list[tuple[dt.date, float]]:
    """Daily values of one metric for one asset, oldest first, `start` and `end` inclusive.

    Follows `next_page_url` until the range is exhausted. Missing values are skipped.
    """
    params: dict[str, str | int] | None = {
        "assets": asset,
        "metrics": metric,
        "frequency": "1d",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "paging_from": "start",
        "page_size": PAGE_SIZE,
    }
    url = "/timeseries/asset-metrics"
    out: list[tuple[dt.date, float]] = []
    while url:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()
        for row in body.get("data", []):
            value = row.get(metric)
            if value is None:
                continue
            out.append((dt.date.fromisoformat(row["time"][:10]), float(value)))
        url = body.get("next_page_url")
        params = None  # next_page_url already carries the query
    return out
