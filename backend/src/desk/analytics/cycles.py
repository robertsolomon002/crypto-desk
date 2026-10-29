"""Cycle alignment by halving, bottom or top, the day-N comparison, ROI since bottom, and YoY.

Cycles come from `config/cycles.yaml`: each runs bottom -> halving -> top. Bottoms and tops are
search windows; the anchor is the lowest (highest) daily close inside the window, and it exists
only once the window has ended by `as_of`, so hindsight windows cannot leak (D33, D35).
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from desk.analytics._frames import truncate
from desk.config import get_settings

MODES = ("halving", "bottom", "top")
ROI_DAYS = (30, 90, 180, 365, 730, 1000)


@dataclass(frozen=True)
class CycleConfig:
    name: str
    bottom_window: tuple[dt.date, dt.date] | None
    halving: dt.date | None
    top_window: tuple[dt.date, dt.date] | None


@dataclass(frozen=True)
class CyclesConfig:
    coins: dict[str, list[CycleConfig]]
    default_anchor: str


@dataclass(frozen=True)
class Anchor:
    kind: str  # bottom | halving | top
    date: dt.date
    price: float


@dataclass(frozen=True)
class Cycle:
    name: str
    bottom: Anchor | None
    halving: Anchor | None
    top: Anchor | None

    def anchor(self, mode: str) -> Anchor | None:
        return getattr(self, mode)


def _window(raw) -> tuple[dt.date, dt.date] | None:
    if not raw:
        return None
    start, end = (d if isinstance(d, dt.date) else dt.date.fromisoformat(d) for d in raw)
    if start > end:
        raise ValueError(f"window {raw} ends before it starts")
    return start, end


def load_config(path: Path | None = None) -> CyclesConfig:
    path = path or get_settings().config_dir / "cycles.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    halvings = set(cfg.get("halvings") or [])
    coins: dict[str, list[CycleConfig]] = {}
    for coin, cycles in (cfg.get("cycles") or {}).items():
        out = []
        for c in cycles:
            halving = c.get("halving")
            if halving is not None and halving not in halvings:
                raise ValueError(f"{coin} {c['name']}: halving {halving} is not in `halvings`")
            cc = CycleConfig(str(c["name"]), _window(c.get("bottom_window")), halving,
                             _window(c.get("top_window")))  # fmt: skip
            points = [p for p in (cc.bottom_window and cc.bottom_window[1], cc.halving,
                                  cc.top_window and cc.top_window[0]) if p]  # fmt: skip
            if points != sorted(points):
                raise ValueError(f"{coin} {cc.name}: expected bottom < halving < top")
            out.append(cc)
        coins[coin.upper()] = out
    mode = cfg.get("default_anchor", "halving")
    if mode not in MODES:
        raise ValueError(f"default_anchor must be one of {MODES}")
    return CyclesConfig(coins, mode)


# --- Anchors ----------------------------------------------------------------------------------


def _extreme(close: pd.Series, window, last: dt.date, kind: str) -> Anchor | None:
    if window is None or window[1] > last:
        return None
    start = pd.Timestamp(window[0], tz="UTC")
    end = pd.Timestamp(window[1], tz="UTC")
    inside = close[(close.index >= start) & (close.index <= end)]
    if inside.empty:
        return None
    ts = inside.idxmin() if kind == "bottom" else inside.idxmax()
    return Anchor(kind, ts.date(), float(inside[ts]))


def _halving(close: pd.Series, day: dt.date | None, last: dt.date) -> Anchor | None:
    if day is None or day > last:
        return None
    after = close[close.index >= pd.Timestamp(day, tz="UTC")]
    if after.empty:
        return None
    return Anchor("halving", after.index[0].date(), float(after.iloc[0]))


def resolve_anchors(
    daily: pd.DataFrame, cycles: list[CycleConfig], as_of: dt.date | None = None
) -> list[Cycle]:
    """Anchors found in the data up to `as_of`; an anchor is None until its window has ended."""
    close = truncate(daily, as_of)["close"]
    if close.empty:
        return [Cycle(c.name, None, None, None) for c in cycles]
    last = close.index[-1].date()
    return [
        Cycle(
            c.name,
            _extreme(close, c.bottom_window, last, "bottom"),
            _halving(close, c.halving, last),
            _extreme(close, c.top_window, last, "top"),
        )
        for c in cycles
    ]


# --- Paths and tables -------------------------------------------------------------------------


def cycle_paths(
    daily: pd.DataFrame,
    cycles: list[Cycle],
    mode: str = "halving",
    as_of: dt.date | None = None,
    max_days: int = 1500,
) -> pd.DataFrame:
    """Long frame: cycle, day offset from the anchor, date, close, multiple of the anchor close,
    and drawdown from the highest close since the anchor. A path stops at the next cycle's
    anchor, after `max_days`, or at `as_of`."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    close = truncate(daily, as_of)["close"]
    anchored = [(c, c.anchor(mode)) for c in cycles if c.anchor(mode) is not None]
    frames = []
    for i, (cycle, anchor) in enumerate(anchored):
        start = pd.Timestamp(anchor.date, tz="UTC")
        end = start + pd.Timedelta(days=max_days)
        if i + 1 < len(anchored):
            end = min(end, pd.Timestamp(anchored[i + 1][1].date, tz="UTC") - pd.Timedelta(days=1))
        seg = close[(close.index >= start) & (close.index <= end)]
        frames.append(
            pd.DataFrame(
                {
                    "cycle": cycle.name,
                    "day": (seg.index - start).days,
                    "date": seg.index,
                    "close": seg.to_numpy(),
                    "multiple": seg.to_numpy() / anchor.price,
                    "drawdown": (seg / seg.cummax() - 1).to_numpy(),
                }
            )
        )
    cols = ["cycle", "day", "date", "close", "multiple", "drawdown"]
    if not frames:
        return pd.DataFrame(columns=cols)
    return pd.concat(frames, ignore_index=True)[cols]


def _at_day(path: pd.DataFrame, n: int) -> pd.Series | None:
    upto = path[path["day"] <= n]
    return None if upto.empty else upto.iloc[-1]


@dataclass(frozen=True)
class DayN:
    mode: str
    current_cycle: str | None
    day: int | None
    table: pd.DataFrame


def day_n_table(paths: pd.DataFrame, cycles: list[Cycle], mode: str = "halving") -> DayN:
    """Each cycle at day N, where N is the current (last anchored) cycle's latest day."""
    cols = ["cycle", "anchor_date", "anchor_price", "day", "date", "close", "multiple",
            "drawdown", "max_multiple", "min_multiple", "top_day", "reached_day_n"]  # fmt: skip
    anchored = [c for c in cycles if c.anchor(mode) is not None]
    with_path = [c for c in anchored if (paths["cycle"] == c.name).any()] if len(paths) else []
    if not with_path:
        return DayN(mode, None, None, pd.DataFrame(columns=cols))
    current = with_path[-1]
    n = int(paths.loc[paths["cycle"] == current.name, "day"].max())
    rows = []
    for c in anchored:
        path = paths[paths["cycle"] == c.name]
        row = _at_day(path, n)
        upto = path[path["day"] <= n]
        anchor = c.anchor(mode)
        top_day = (c.top.date - anchor.date).days if c.top and c.top.date >= anchor.date else None
        rows.append(
            {"cycle": c.name, "anchor_date": anchor.date, "anchor_price": anchor.price,
             "day": None if row is None else int(row["day"]),
             "date": None if row is None else row["date"],
             "close": None if row is None else row["close"],
             "multiple": None if row is None else row["multiple"],
             "drawdown": None if row is None else row["drawdown"],
             "max_multiple": upto["multiple"].max() if not upto.empty else None,
             "min_multiple": upto["multiple"].min() if not upto.empty else None,
             "top_day": top_day,
             "reached_day_n": bool(not path.empty and path["day"].max() >= n)}
        )  # fmt: skip
    return DayN(mode, current.name, n, pd.DataFrame(rows, columns=cols))


def roi_since_bottom(
    daily: pd.DataFrame, cycles: list[Cycle], as_of: dt.date | None = None
) -> pd.DataFrame:
    """Return since each cycle's bottom at fixed day offsets and at the current cycle's day N."""
    paths = cycle_paths(daily, cycles, "bottom", as_of, max_days=100_000)
    table = day_n_table(paths, cycles, "bottom")
    days = sorted({*ROI_DAYS, *([table.day] if table.day is not None else [])})
    rows = []
    for c in cycles:
        if c.bottom is None:
            continue
        path = paths[paths["cycle"] == c.name]
        row: dict = {"cycle": c.name, "bottom_date": c.bottom.date, "bottom_price": c.bottom.price}
        for n in days:
            reached = not path.empty and path["day"].max() >= n
            point = _at_day(path, n) if reached else None
            row[f"d{n}"] = None if point is None else point["multiple"] - 1
        rows.append(row)
    return pd.DataFrame(rows)


def yoy_paths(daily: pd.DataFrame, as_of: dt.date | None = None) -> pd.DataFrame:
    """Each calendar year normalized to its first close: year, day of year (0 = Jan 1), date,
    close, multiple."""
    close = truncate(daily, as_of)["close"]
    frames = []
    for year, seg in close.groupby(close.index.year):
        jan1 = pd.Timestamp(year=int(year), month=1, day=1, tz="UTC")
        frames.append(
            pd.DataFrame(
                {"year": int(year), "day": (seg.index - jan1).days, "date": seg.index,
                 "close": seg.to_numpy(), "multiple": seg.to_numpy() / seg.iloc[0]}
            )
        )  # fmt: skip
    cols = ["year", "day", "date", "close", "multiple"]
    return pd.concat(frames, ignore_index=True)[cols] if frames else pd.DataFrame(columns=cols)
