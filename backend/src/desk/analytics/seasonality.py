"""Monthly, weekly and day-of-week return seasonality. Complete periods only."""

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from desk.analytics._frames import DAY, truncate
from desk.data.market import resample_weekly


@dataclass(frozen=True)
class Seasonality:
    matrix: pd.DataFrame  # rows = years (or empty for day-of-week), columns = periods
    summary: pd.DataFrame  # per period: mean, median, pct_positive, count


def _summary(returns: pd.Series, by) -> pd.DataFrame:
    g = returns.groupby(by)
    return pd.DataFrame(
        {"mean": g.mean(), "median": g.median(), "pct_positive": g.apply(lambda r: (r > 0).mean()),
         "count": g.count()}
    )  # fmt: skip


def monthly(daily: pd.DataFrame, as_of: dt.date | None = None) -> Seasonality:
    """Month-over-month close returns: year x month matrix (1..12) plus per-month summary.

    A month counts only once its last day is in the data; its return needs the previous month's
    close, so the first month in the data has none.
    """
    close = truncate(daily, as_of)["close"]
    if close.empty:
        return Seasonality(pd.DataFrame(), pd.DataFrame())
    last = close.index[-1]
    month_end = close.resample("ME").last()
    complete = month_end.index <= last  # "ME" labels are month-end midnights
    rets = month_end[complete].pct_change().dropna()
    matrix = (
        pd.DataFrame({"year": rets.index.year, "month": rets.index.month, "ret": rets.to_numpy()})
        .pivot(index="year", columns="month", values="ret")
        .reindex(columns=range(1, 13))
    )
    matrix.columns = [str(m) for m in matrix.columns]
    summary = _summary(rets, rets.index.month).reindex(range(1, 13))
    summary.index.name = "month"
    return Seasonality(matrix, summary)


def weekly(daily: pd.DataFrame, as_of: dt.date | None = None) -> Seasonality:
    """Week-over-week returns of complete Monday weeks, by ISO week number (1..53)."""
    w = resample_weekly(truncate(daily, as_of))
    rets = w["close"].pct_change().dropna()
    if rets.empty:
        return Seasonality(pd.DataFrame(), pd.DataFrame())
    iso = rets.index.isocalendar()
    matrix = (
        pd.DataFrame({"year": iso["year"].to_numpy(), "week": iso["week"].to_numpy(),
                      "ret": rets.to_numpy()})
        .pivot(index="year", columns="week", values="ret")
    )  # fmt: skip
    matrix.columns = [str(c) for c in matrix.columns]
    summary = _summary(rets, iso["week"].to_numpy())
    summary.index.name = "week"
    return Seasonality(matrix, summary)


def day_of_week(daily: pd.DataFrame, as_of: dt.date | None = None) -> Seasonality:
    """Daily close-to-close returns by weekday (0 = Monday), consecutive days only."""
    close = truncate(daily, as_of)["close"]
    rets = close.pct_change()
    consecutive = close.index.to_series().diff() == DAY
    rets = rets[consecutive.to_numpy()].dropna()
    summary = _summary(rets, rets.index.day_of_week).reindex(range(7))
    summary.index.name = "weekday"
    return Seasonality(pd.DataFrame(), summary)
