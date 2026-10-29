"""Look-ahead test (Section 3.1, D33): for every registry function, every coin and 50 seeded
random `as_of` values,

1. truncation invariance: f(full data, as_of) == f(data truncated at as_of, as_of);
2. causal prefix (time-series outputs): f(full, None) cut at as_of == f(full, as_of).
"""

import dataclasses
import datetime as dt
import math
import random
from functools import cache

import pandas as pd
import pytest

from desk.analytics import registry
from desk.analytics._frames import truncate
from desk.analytics.inputs import Inputs
from tests.analytics_fakes import synthetic_inputs

N_DATES = 50
COINS = ["BTC", "ETH", "SOL"]


@cache
def full_inputs() -> Inputs:
    return synthetic_inputs()


def truncated(inputs: Inputs, as_of: dt.date) -> Inputs:
    return Inputs(
        {c: truncate(df, as_of) for c, df in inputs.daily.items()},
        {c: truncate(df, as_of) for c, df in inputs.onchain.items()},
        inputs.cycles,
    )


def as_of_dates(coin: str, name: str) -> list[dt.date]:
    index = full_inputs().daily[coin].index
    first, last = index[30].date(), index[-1].date()
    rng = random.Random(f"{name}:{coin}")  # seeded per function and coin
    span = (last - first).days
    return sorted(first + dt.timedelta(days=rng.randrange(span + 1)) for _ in range(N_DATES))


def assert_same(a, b, where: str) -> None:
    if isinstance(a, pd.DataFrame | pd.Series):
        assert type(a) is type(b), where
        if isinstance(a, pd.DataFrame):
            pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, obj=where)
        else:
            pd.testing.assert_series_equal(a, b, check_exact=False, rtol=1e-9, obj=where)
    elif dataclasses.is_dataclass(a):
        assert type(a) is type(b), where
        for f in dataclasses.fields(a):
            assert_same(getattr(a, f.name), getattr(b, f.name), f"{where}.{f.name}")
    elif isinstance(a, list | tuple):
        assert len(a) == len(b), f"{where}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            assert_same(x, y, f"{where}[{i}]")
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), where
        for k in a:
            assert_same(a[k], b[k], f"{where}[{k}]")
    elif isinstance(a, float) and isinstance(b, float):
        assert (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=1e-9), where
    else:
        assert a == b, f"{where}: {a!r} != {b!r}"


CASES = [
    (spec.name, coin)
    for spec in registry.SPECS
    for coin in COINS
    if spec.supports(synthetic_inputs(), coin)
]


@pytest.mark.parametrize(("name", "coin"), CASES)
def test_no_look_ahead(name: str, coin: str) -> None:
    spec = registry.get(name)
    full = full_inputs()
    whole = registry.run(name, full, coin) if spec.series else None
    for as_of in as_of_dates(coin, name):
        where = f"{name}({coin}, as_of={as_of})"
        result = registry.run(name, full, coin, as_of)
        assert_same(result, registry.run(name, truncated(full, as_of), coin, as_of), where)
        if spec.series is not None:
            assert_same(truncate(spec.series(whole), as_of), spec.series(result), f"{where} prefix")


def test_every_function_is_covered() -> None:
    covered = {name for name, _ in CASES}
    assert covered == set(registry.REGISTRY)


def test_selectable_indicators_have_no_look_ahead() -> None:
    """`indicators.custom` (the API's selectable indicators, Stage 2.1) is not a registry entry
    because its parameters are tuples; the same two checks, with every option on."""
    from desk.analytics.indicators import IndicatorRequest, custom

    req = IndicatorRequest(sma=(7, 50), ema=(21,), bollinger=(20, 2.5), rsi=9,
                           macd=(5, 35, 5), vol=(14,), band=True)  # fmt: skip
    for coin in COINS:
        daily = full_inputs().daily[coin]
        whole = custom(daily, req)
        for as_of in as_of_dates(coin, "indicators_custom"):
            where = f"indicators_custom/{coin}/{as_of}"
            cut = custom(daily, req, as_of)
            assert_same(cut, custom(truncate(daily, as_of), req, as_of), where)
            assert_same(truncate(whole, as_of), cut, where + " (prefix)")
