"""FRED macro series from `config/fred_series.yaml` (Stage 1.2), stored as `fred:<id>`.

`GET https://api.stlouisfed.org/fred/series/observations` returns the latest vintage, oldest
first; missing values are ".". Observations are dated by period, not by publication: DGS10 for
day D is published on D+1 or later, M2SL for month M about 55 days after the 1st of M. So as-of
reads only include a row once `date + release_lag_days <= as_of` (lags measured in Stage 1.2, D32).

The API key travels in the query string, so HTTP errors are re-raised without the URL.
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import httpx
import pandas as pd
import yaml
from sqlalchemy.orm import Session

from desk.config import get_settings
from desk.data import http, series

BASE_URL = "https://api.stlouisfed.org/fred"
SOURCE = "fred"
HISTORY_START = dt.date(2010, 1, 1)
REVISION_DAYS = 365  # refetch the last year on every update to pick up revisions (M2SL)


class FredError(RuntimeError):
    pass


@dataclass(frozen=True)
class FredSeries:
    id: str
    label: str
    units: str
    release_lag_days: int

    @property
    def key(self) -> str:
        return f"fred:{self.id}"


def load_config(path: Path | None = None) -> list[FredSeries]:
    path = path or get_settings().config_dir / "fred_series.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        FredSeries(s["id"], s["label"], s["units"], int(s["release_lag_days"]))
        for s in cfg.get("series") or []
    ]


def make_client() -> httpx.Client:
    return http.make_client(BASE_URL)


def fetch_observations(
    client: httpx.Client, series_id: str, api_key: str, start: dt.date
) -> list[tuple[dt.date, float]]:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start.isoformat(),
    }
    try:
        resp = client.get("/series/observations", params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise FredError(f"FRED {series_id}: HTTP {exc.response.status_code}") from None
    except httpx.HTTPError as exc:
        raise FredError(f"FRED {series_id}: {type(exc).__name__}") from None
    return [
        (dt.date.fromisoformat(o["date"]), float(o["value"]))
        for o in resp.json().get("observations", [])
        if o["value"] != "."
    ]


def update(
    session: Session,
    client: httpx.Client,
    api_key: str,
    now: dt.datetime,
    config: list[FredSeries] | None = None,
) -> dict[str, int]:
    """Fetch every configured series (history from 2010 the first time); new rows per id."""
    added: dict[str, int] = {}
    for s in config or load_config():
        last = series.last_date(session, s.key)
        start = HISTORY_START if last is None else last - dt.timedelta(days=REVISION_DAYS)
        points = [(d, v) for d, v in fetch_observations(client, s.id, api_key, start)
                  if d <= now.date()]  # fmt: skip
        added[s.id] = series.upsert_series(session, s.key, points, SOURCE)
    return added


def load_macro(
    session: Session,
    as_of: dt.date | None = None,
    config: list[FredSeries] | None = None,
) -> pd.DataFrame:
    """Wide frame of FRED series (columns are FRED ids) published by `as_of`.

    Columns have different frequencies (M2SL is monthly); no forward fill is applied here.
    """
    config = config or load_config()
    df = series.load_series(
        session,
        [s.key for s in config],
        as_of=as_of,
        lag_days={s.key: s.release_lag_days for s in config},
    )
    return df.set_axis([s.id for s in config], axis=1)
