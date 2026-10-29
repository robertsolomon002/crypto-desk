"""Fear & Greed index from alternative.me (Stage 1.2), stored in `series` as key `fng`.

`GET https://api.alternative.me/fng/?limit=N` returns the newest N days first (`limit=0` is the
full history, from 2018-02-01). Each row's `timestamp` is 00:00 UTC of its day; the value for
day D is published at the start of D, so D is known by the end of D (the `series` as-of rule).
"""

import datetime as dt

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from desk.data import series

URL = "https://api.alternative.me/fng/"
KEY = "fng"
SOURCE = "alternative.me"
OVERLAP_DAYS = 3


def parse(body: dict) -> list[tuple[dt.date, float]]:
    """Points oldest first. Raises if the API reports an error."""
    error = (body.get("metadata") or {}).get("error")
    if error:
        raise RuntimeError(f"alternative.me error: {error}")
    points = {
        dt.datetime.fromtimestamp(int(row["timestamp"]), tz=dt.UTC).date(): float(row["value"])
        for row in body.get("data") or []
    }
    return sorted(points.items())


def fetch(client: httpx.Client, limit: int = 0) -> list[tuple[dt.date, float]]:
    resp = client.get(URL, params={"limit": limit, "format": "json"})
    resp.raise_for_status()
    return parse(resp.json())


def update(session: Session, client: httpx.Client, now: dt.datetime) -> int:
    """Fetch new days (the full history the first time); returns the number of new rows."""
    last = series.last_date(session, KEY)
    limit = 0 if last is None else (now.date() - last).days + OVERLAP_DAYS
    points = [(d, v) for d, v in fetch(client, limit) if d <= now.date()]
    return series.upsert_series(session, KEY, points, SOURCE)


def load_fng(session: Session, as_of: dt.date | None = None) -> pd.Series:
    """Daily Fear & Greed values (0 to 100) up to `as_of`, indexed by UTC midnight."""
    return series.load_series(session, [KEY], as_of=as_of)[KEY]
