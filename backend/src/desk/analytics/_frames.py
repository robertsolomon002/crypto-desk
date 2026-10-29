"""Shared helpers: as-of truncation, high/low fallbacks and JSON conversion (D33)."""

import dataclasses
import datetime as dt
import math
from collections.abc import Mapping
from typing import Any, overload

import numpy as np
import pandas as pd

DAY = pd.Timedelta(days=1)


@overload
def truncate(obj: pd.DataFrame, as_of: dt.date | None) -> pd.DataFrame: ...
@overload
def truncate(obj: pd.Series, as_of: dt.date | None) -> pd.Series: ...
def truncate(obj, as_of):
    """Rows dated `<= as_of` (the as_of day included). Index: UTC midnights."""
    if as_of is None:
        return obj
    end = pd.Timestamp(as_of, tz="UTC") + DAY
    return obj.loc[obj.index < end]


def highs(daily: pd.DataFrame) -> pd.Series:
    """High, or the close on close-only rows (Coin Metrics backfill, D31)."""
    return daily["high"].fillna(daily["close"])


def lows(daily: pd.DataFrame) -> pd.Series:
    return daily["low"].fillna(daily["close"])


def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close).diff()


def day(ts: pd.Timestamp) -> dt.date:
    return ts.date()


def to_jsonable(obj: Any) -> Any:
    """JSON-safe structure: frames become records, dates ISO strings, NaN and inf become None."""
    if isinstance(obj, pd.DataFrame):
        frame = obj.reset_index() if not isinstance(obj.index, pd.RangeIndex) else obj
        return [
            {str(k): to_jsonable(v) for k, v in row.items()}
            for row in frame.to_dict(orient="records")
        ]
    if isinstance(obj, pd.Series):
        return [{"date": to_jsonable(k), "value": to_jsonable(v)} for k, v in obj.items()]
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        if pd.isna(obj):
            return None
        return obj.date().isoformat() if obj == obj.normalize() else obj.isoformat()
    if isinstance(obj, dt.datetime | dt.date):
        return obj.isoformat()
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, float | np.floating):
        f = float(obj)
        return f if math.isfinite(f) else None
    if obj is pd.NaT or obj is pd.NA:
        return None
    return obj
