"""Every analytics function under one name, with the same calling convention (D33).

`run(name, inputs, coin, as_of, **params)` returns the raw result (frames, dataclasses);
`run_json` the JSON form. The CLI, `cache`, the look-ahead test, and later the API and
desk-mcp all call through here, so each function is defined once.
"""

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from desk.analytics import cycles, indicators, levels, onchain, pivots, regime, seasonality, stats
from desk.analytics._frames import to_jsonable, truncate
from desk.analytics.inputs import Inputs
from desk.data.market import resample_weekly


@dataclass(frozen=True)
class Spec:
    name: str
    description: str
    fn: Callable[..., Any]  # (inputs, coin, as_of, **params) -> result
    params: dict[str, Any] = field(default_factory=dict)  # defaults; also the allowed names
    series: Callable[[Any], pd.DataFrame | pd.Series] | None = None  # date-indexed view
    heavy: bool = False  # precomputed by cache.refresh
    needs: str = "daily"  # daily | onchain | cycles | all_coins

    def supports(self, inputs: Inputs, coin: str) -> bool:
        if self.needs == "onchain":
            return coin in inputs.onchain
        if self.needs == "cycles":
            return coin in inputs.cycles.coins
        return coin in inputs.daily


def _cycles(inputs: Inputs, coin: str, as_of):
    return cycles.resolve_anchors(inputs.daily[coin], inputs.cycles.coins[coin], as_of)


def _day_n(inputs, coin, as_of, mode):
    resolved = _cycles(inputs, coin, as_of)
    paths = cycles.cycle_paths(inputs.daily[coin], resolved, mode, as_of)
    return cycles.day_n_table(paths, resolved, mode)


def _pivots(inputs, coin, as_of, timeframe):
    bars = inputs.daily[coin]
    if timeframe == "1w":
        bars = resample_weekly(truncate(bars, as_of))  # complete weeks up to as_of
    elif timeframe != "1d":
        raise ValueError("timeframe must be 1d or 1w")
    return pivots.zigzag(bars, as_of, **pivots.DEFAULTS[timeframe])


def _correlation(inputs, coin, as_of, window):
    others = [c for c in inputs.daily if c != coin]
    closes = {c: inputs.daily[c]["close"] for c in [coin, *others]}
    return stats.rolling_correlation(closes, as_of, window)


SPECS = [
    Spec("indicators", "SMA/EMA 20/50/200, Bollinger, RSI 14, MACD, vol 30/90, 20W SMA band",
         lambda i, c, a: indicators.indicators(i.daily[c], a), series=lambda r: r),
    Spec("regime", "Regime label (frozen D34 rules) with its inputs and history",
         lambda i, c, a: regime.regime(i.daily[c], a), series=lambda r: r.labels),
    Spec("levels", "Key levels with distance from the last close",
         lambda i, c, a: levels.key_levels(i.daily[c], a)),
    Spec("pivots", "Zigzag swing pivots (timeframe 1d or 1w)", _pivots,
         params={"timeframe": "1d"}),
    Spec("cycles_anchors", "Cycle bottoms, halvings and tops found in the data",
         _cycles, needs="cycles"),
    Spec("cycles_paths", "Cycle overlays aligned by halving, bottom or top",
         lambda i, c, a, mode, max_days: cycles.cycle_paths(
             i.daily[c], _cycles(i, c, a), mode, a, max_days),
         params={"mode": "halving", "max_days": 1500}, heavy=True, needs="cycles"),
    Spec("cycles_day_n", "Every cycle at the current cycle's day N", _day_n,
         params={"mode": "halving"}, heavy=True, needs="cycles"),
    Spec("roi_since_bottom", "Return since each cycle bottom at fixed days and day N",
         lambda i, c, a: cycles.roi_since_bottom(i.daily[c], _cycles(i, c, a), a),
         heavy=True, needs="cycles"),
    Spec("yoy", "Each calendar year normalized to its first close",
         lambda i, c, a: cycles.yoy_paths(i.daily[c], a), heavy=True),
    Spec("seasonality_monthly", "Monthly returns: year x month matrix and per-month summary",
         lambda i, c, a: seasonality.monthly(i.daily[c], a), heavy=True),
    Spec("seasonality_weekly", "Weekly returns by ISO week",
         lambda i, c, a: seasonality.weekly(i.daily[c], a), heavy=True),
    Spec("seasonality_dow", "Daily returns by weekday",
         lambda i, c, a: seasonality.day_of_week(i.daily[c], a), heavy=True),
    Spec("return_distribution", "Return histogram with the latest period's percentile",
         lambda i, c, a, horizon: stats.return_distribution(i.daily[c], horizon, a),
         params={"horizon": "1w"}, heavy=True),
    Spec("drawdowns", "Drawdown from the running ATH close, per day",
         lambda i, c, a: stats.drawdown_series(i.daily[c], a), series=lambda r: r),
    Spec("drawdown_episodes", "Deepest peak-to-trough episodes",
         lambda i, c, a, top_n: stats.drawdown_episodes(i.daily[c], a, top_n),
         params={"top_n": 10}, heavy=True),
    Spec("rolling_volatility", "Annualized 30 and 90 day realized volatility",
         lambda i, c, a: stats.rolling_volatility(i.daily[c], a), series=lambda r: r),
    Spec("rolling_correlation", "Rolling correlation of daily log returns with the other coins",
         _correlation, params={"window": 90}, series=lambda r: r, needs="all_coins"),
    Spec("onchain", "MVRV, realized cap and price, NUPL, supply, addresses, hash rate",
         lambda i, c, a: onchain.onchain_metrics(i.onchain[c], a), series=lambda r: r,
         needs="onchain"),
]  # fmt: skip

REGISTRY: dict[str, Spec] = {s.name: s for s in SPECS}


def get(name: str) -> Spec:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown analytics function {name!r}; see `desk analytics list`") from None


def resolve_params(spec: Spec, params: dict[str, Any]) -> dict[str, Any]:
    """Defaults overlaid with `params`; strings (from the CLI) are cast to the default's type."""
    unknown = set(params) - set(spec.params)
    if unknown:
        raise ValueError(f"{spec.name} has no parameter(s) {sorted(unknown)}")
    out = dict(spec.params)
    for k, v in params.items():
        default = spec.params[k]
        out[k] = type(default)(v) if isinstance(v, str) and not isinstance(default, str) else v
    return out


def run(name: str, inputs: Inputs, coin: str, as_of: dt.date | None = None, **params: Any) -> Any:
    spec = get(name)
    coin = coin.upper()
    if not spec.supports(inputs, coin):
        raise ValueError(f"{name} is not available for {coin}")
    return spec.fn(inputs, coin, as_of, **resolve_params(spec, params))


def run_json(
    name: str, inputs: Inputs, coin: str, as_of: dt.date | None = None, **params: Any
) -> Any:
    return to_jsonable(run(name, inputs, coin, as_of, **params))
