"""Analytics functions against hand-computed values on small synthetic series (Stage 1.3)."""

import datetime as dt
import math

import numpy as np
import pandas as pd
import pytest

from desk.analytics import (
    cycles,
    indicators,
    levels,
    onchain,
    pivots,
    regime,
    seasonality,
    stats,
    summary,
)
from desk.analytics._frames import to_jsonable, truncate
from tests.analytics_fakes import frame

D = dt.date
nan = float("nan")


def values(s: pd.Series) -> list[float]:
    return [round(v, 6) if not math.isnan(v) else v for v in s.tolist()]


def assert_list(actual: list[float], expected: list[float]) -> None:
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected, strict=True):
        assert (math.isnan(a) and math.isnan(e)) or a == pytest.approx(e, abs=1e-6), (a, e)


# --- Helpers ----------------------------------------------------------------------------------


def test_truncate_includes_the_as_of_day() -> None:
    df = frame(range(1, 11))  # 2024-01-01 .. 2024-01-10
    assert truncate(df, D(2024, 1, 5)).index[-1].date() == D(2024, 1, 5)
    assert len(truncate(df, None)) == 10
    assert truncate(df, D(2023, 12, 31)).empty


def test_to_jsonable() -> None:
    df = frame([1.0, nan])
    out = to_jsonable({"df": df[["close"]], "x": np.float64(nan), "d": pd.Timestamp("2024-01-02")})
    records = [{"date": "2024-01-01", "close": 1.0}, {"date": "2024-01-02", "close": None}]
    assert out == {"df": records, "x": None, "d": "2024-01-02"}
    level = levels.Level("ath", 2.0, D(2024, 1, 1), 0.5)
    assert to_jsonable([level]) == [
        {"name": "ath", "value": 2.0, "date": "2024-01-01", "distance": 0.5}
    ]


# --- Indicators -------------------------------------------------------------------------------


def test_sma_and_ema() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert_list(values(indicators.sma(s, 3)), [nan, nan, 2.0, 3.0, 4.0])
    # span 3 -> alpha 0.5, seeded with the first value: 1, 1.5, 2.25, 3.125, 4.0625
    assert_list(values(indicators.ema(s, 3)), [nan, nan, 2.25, 3.125, 4.0625])


def test_rsi_wilder_hand_example() -> None:
    # changes +1, -0.5, +1, -0.5; first averages (n=2): gain 0.5, loss 0.25 -> RS 2
    # then gain (0.5+1)/2=0.75, loss 0.25/2=0.125 -> RS 6; then 0.375, 0.3125 -> RS 1.2
    s = pd.Series([10.0, 11.0, 10.5, 11.5, 11.0])
    assert_list(values(indicators.rsi(s, 2)), [nan, nan, 100 - 100 / 3, 100 - 100 / 7,
                                               100 - 100 / 2.2])  # fmt: skip
    assert indicators.rsi(pd.Series(np.arange(1.0, 30.0)), 14).iloc[-1] == 100.0
    assert indicators.rsi(pd.Series([5.0] * 20), 14).iloc[-1] == 50.0


def test_bollinger_and_macd_match_numpy() -> None:
    s = pd.Series(np.linspace(1, 40, 40) + np.sin(np.arange(40)))
    bb = indicators.bollinger(s, 20, 2.0)
    window = s.iloc[-20:].to_numpy()
    assert bb["bb_mid"].iloc[-1] == pytest.approx(window.mean())
    assert bb["bb_upper"].iloc[-1] == pytest.approx(window.mean() + 2 * window.std(ddof=0))

    m = indicators.macd(s)
    fast, slow = s.ewm(span=12, adjust=False).mean(), s.ewm(span=26, adjust=False).mean()
    assert m["macd"].iloc[-1] == pytest.approx(fast.iloc[-1] - slow.iloc[-1])
    assert (m["macd_hist"] - (m["macd"] - m["macd_signal"])).abs().max() < 1e-12


def test_realized_vol() -> None:
    steady = pd.Series(100 * 1.01 ** np.arange(10))
    assert indicators.realized_vol(steady, 5).iloc[-1] == pytest.approx(0.0, abs=1e-12)
    a = 0.05
    zig = pd.Series(100 * np.exp(np.cumsum([0, a, -a, a, -a])))
    # std (ddof=1) of [a, -a] is a * sqrt(2)
    assert indicators.realized_vol(zig, 2).iloc[-1] == pytest.approx(a * math.sqrt(2) *
                                                                    math.sqrt(365))  # fmt: skip


def test_weekly_band_applies_from_the_monday_after_the_week() -> None:
    weeks = 30  # 2024-01-01 is a Monday; every day of week w closes at w
    df = frame(np.repeat(np.arange(1.0, weeks + 1), 7), start="2024-01-01")
    band = indicators.weekly_band(df)
    first = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(weeks=20)  # Monday of week 21
    assert band.loc[first, "sma20w"] == pytest.approx(10.5)  # mean of weeks 1..20
    assert math.isnan(band.loc[first - pd.Timedelta(days=1), "sma20w"])
    assert band.loc[first + pd.Timedelta(days=6), "sma20w"] == pytest.approx(10.5)


def test_indicators_frame_columns() -> None:
    out = indicators.indicators(frame(np.linspace(1, 300, 300)), D(2024, 6, 1))
    assert out.index[-1].date() == D(2024, 6, 1)
    assert {"sma200", "ema21w", "rsi14", "macd_hist", "vol90", "bb_lower"} <= set(out.columns)


# --- Regime -----------------------------------------------------------------------------------


def test_regime_rules() -> None:
    # drift plus a zigzag whose size shrinks, so volatility falls and never trips high-vol
    wiggle = np.array([0.01 * (1 - i / 400) * (-1) ** i for i in range(400)])
    up = frame(100 * np.exp(np.cumsum(0.003 + wiggle)))
    down = frame(100 * np.exp(np.cumsum(-0.003 + wiggle)))
    flat = frame([100.0] * 400)
    calm = [0.001 * (-1) ** i for i in range(370)]
    wild = [0.10 * (-1) ** i for i in range(30)]
    calm_then_wild = frame(100 * np.exp(np.cumsum(calm + wild)))
    assert regime.regime(up).current == "uptrend"
    assert regime.regime(down).current == "downtrend"
    assert regime.regime(flat).current == "range"
    assert regime.regime(calm_then_wild).current == "high-vol"
    assert regime.regime(up, D(2024, 6, 1)).current == "insufficient_data"  # day 153
    r = regime.regime(up)
    assert r.inputs["close"] > r.inputs["sma200"] and r.labels.iloc[363] == "insufficient_data"
    assert r.labels.iloc[364] == "uptrend"  # day 365


# --- Pivots and levels ------------------------------------------------------------------------


def test_zigzag_fixed_threshold() -> None:
    closes = [100, 105, 111, 100, 98, 95, 90, 95, 99.5, 105]
    got = pivots.zigzag(frame(closes), floor=0.10, cap=0.10)
    assert [(p.kind, p.date.day, p.price, p.confirmed, p.confirmed_on and p.confirmed_on.day)
            for p in got] == [
        ("low", 1, 100, True, 3),  # +11% to 111 on Jan 3 confirms the low
        ("high", 3, 111, True, 5),  # 98 <= 111 * 0.9 on Jan 5
        ("low", 7, 90, True, 9),  # 99.5 >= 90 * 1.1 on Jan 9
        ("high", 10, 105, False, None),  # open leg
    ]  # fmt: skip


def test_key_levels() -> None:
    # 2024-01-01 is a Monday: two complete weeks, then two days of week 3
    closes = [10, 11, 12, 13, 14, 15, 16] + [20, 19, 18, 17, 16, 15, 14] + [15, 15]
    out = {lv.name: lv for lv in levels.key_levels(frame(closes, ohlc=True))}
    assert out["prev_week_high"].value == 20 and out["prev_week_low"].value == 14
    assert out["prev_week_high"].date == D(2024, 1, 8)
    assert out["ath"].value == 20 and out["ath"].date == D(2024, 1, 8)
    assert out["ath"].distance == pytest.approx(20 / 15 - 1)
    assert "sma200d" not in out  # not enough data


# --- Cycles -----------------------------------------------------------------------------------


def _cycle_data() -> tuple[pd.DataFrame, list[cycles.CycleConfig]]:
    # Jan 1-10 falls to 50 on Jan 5, rises to 200 on Feb 4, falls to 80 on Mar 6, up to 160
    days = pd.date_range("2020-01-01", "2020-04-30", freq="D", tz="UTC")
    close = np.interp(np.arange(len(days)), [0, 4, 34, 65, 120], [100, 50, 200, 80, 160])
    cfg = [
        cycles.CycleConfig("A", (D(2020, 1, 1), D(2020, 1, 10)), D(2020, 1, 15),
                           (D(2020, 2, 1), D(2020, 2, 10))),
        cycles.CycleConfig("B", (D(2020, 3, 1), D(2020, 3, 10)), None, None),
    ]  # fmt: skip
    return frame(close, start="2020-01-01"), cfg


def test_cycle_anchors_appear_only_after_their_window() -> None:
    df, cfg = _cycle_data()
    a, b = cycles.resolve_anchors(df, cfg)
    assert (a.bottom.date, a.bottom.price) == (D(2020, 1, 5), 50.0)
    assert (a.top.date, a.top.price) == (D(2020, 2, 4), 200.0)
    assert a.halving.date == D(2020, 1, 15)
    assert (b.bottom.date, b.bottom.price) == (D(2020, 3, 6), 80.0)
    early, _ = cycles.resolve_anchors(df, cfg, D(2020, 2, 9))  # top window ends Feb 10
    assert early.top is None and early.bottom is not None


def test_cycle_paths_and_day_n() -> None:
    df, cfg = _cycle_data()
    resolved = cycles.resolve_anchors(df, cfg)
    paths = cycles.cycle_paths(df, resolved, "bottom")
    a = paths[paths["cycle"] == "A"]
    assert a["date"].iloc[-1].date() == D(2020, 3, 5)  # stops the day before B's bottom
    assert a.loc[a["day"] == 30, "multiple"].item() == pytest.approx(4.0)  # 200 / 50
    assert a["drawdown"].iloc[-1] == pytest.approx(a["close"].iloc[-1] / 200 - 1)
    table = cycles.day_n_table(paths, resolved, "bottom")
    assert table.current_cycle == "B" and table.day == (D(2020, 4, 30) - D(2020, 3, 6)).days
    row_a = table.table.set_index("cycle").loc["A"]
    assert row_a["max_multiple"] == pytest.approx(4.0) and row_a["top_day"] == 30
    assert table.day == 55 and row_a["reached_day_n"]  # A spans days 0..60
    assert row_a["date"].date() == D(2020, 2, 29) and row_a["day"] == 55


def test_yoy_paths_normalize_to_first_close() -> None:
    df = frame([10.0, 20.0, 40.0], start="2023-12-31")
    out = cycles.yoy_paths(df)
    assert out[["year", "day", "multiple"]].values.tolist() == [[2023, 364, 1.0], [2024, 0, 1.0],
                                                               [2024, 1, 2.0]]  # fmt: skip


def test_repo_cycles_config() -> None:
    cfg = cycles.load_config()
    assert [c.name for c in cfg.coins["BTC"]] == ["2013", "2017", "2021", "2025"]
    assert cfg.coins["BTC"][-1].top_window == (D(2025, 9, 1), D(2025, 12, 31))
    assert cfg.coins["ETH"][0].bottom_window is None and cfg.default_anchor == "halving"


def test_cycles_config_rejects_bad_order(tmp_path) -> None:
    path = tmp_path / "cycles.yaml"
    path.write_text(
        "halvings: [2020-05-11]\ncycles:\n  BTC:\n    - name: x\n"
        "      bottom_window: [2021-01-01, 2021-02-01]\n      halving: 2020-05-11\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="bottom < halving < top"):
        cycles.load_config(path)


# --- Seasonality ------------------------------------------------------------------------------


def test_monthly_seasonality_complete_months_across_a_year_boundary() -> None:
    days = pd.date_range("2022-12-01", "2023-03-15", freq="D", tz="UTC")
    close = np.select([days.month == 12, days.month == 1, days.month == 2], [100, 110, 99], 120)
    out = seasonality.monthly(frame(close, start="2022-12-01"))
    assert list(out.matrix.index) == [2023]
    assert out.matrix.loc[2023, "1"] == pytest.approx(0.10)
    assert out.matrix.loc[2023, "2"] == pytest.approx(-0.10)
    assert math.isnan(out.matrix.loc[2023, "3"])  # March is incomplete
    assert out.summary.loc[1, "pct_positive"] == 1.0 and out.summary.loc[2, "count"] == 1


def test_day_of_week_and_weekly_seasonality() -> None:
    df = frame(100 * 1.01 ** np.arange(70), start="2024-01-01")
    dow = seasonality.day_of_week(df)
    assert dow.summary["mean"].round(10).nunique() == 1
    assert dow.summary["mean"].iloc[0] == pytest.approx(0.01)
    wk = seasonality.weekly(df)
    assert wk.summary["mean"].iloc[0] == pytest.approx(1.01**7 - 1)


# --- Stats ------------------------------------------------------------------------------------


def test_drawdown_episodes() -> None:
    out = stats.drawdown_episodes(frame([1, 2, 1, 1.5, 2, 3, 1.5, 3.5, 1.75]))
    assert out[["peak", "trough", "depth"]].values.tolist() == [[2, 1, -0.5], [3, 1.5, -0.5],
                                                                [3.5, 1.75, -0.5]]  # fmt: skip
    assert out["recovery_date"].tolist() == [D(2024, 1, 5), D(2024, 1, 8), None]
    assert out["days"].tolist() == [3, 2, 1]


def test_return_distribution_percentile() -> None:
    closes = [100, 110, 99, 108.9, 130.68]  # +10%, -10%, +10%, +20%
    d = stats.return_distribution(frame(closes), "1d")
    assert d.count == 4 and d.current == pytest.approx(0.2) and d.current_percentile == 100.0
    assert d.current_date == D(2024, 1, 5) and sum(d.counts) == 4


def test_rolling_correlation_extremes() -> None:
    a = frame(100 * np.exp(np.cumsum(np.sin(np.arange(60)) / 10)))["close"]
    out = stats.rolling_correlation({"A": a, "B": a * 3, "C": 1 / a}, window=30)
    assert out["A/B"].iloc[-1] == pytest.approx(1.0)
    assert out["A/C"].iloc[-1] == pytest.approx(-1.0)
    assert out["A/B"].iloc[:29].isna().all()


# --- On-chain ---------------------------------------------------------------------------------


def test_nupl_identity() -> None:
    idx = pd.date_range("2024-01-01", periods=2, tz="UTC")
    raw = pd.DataFrame({"CapMrktCurUSD": [200.0, 300.0], "CapMVRVCur": [2.0, 0.75],
                        "SplyCur": [10.0, 10.0], "AdrActCnt": [1.0, 1.0],
                        "HashRate": [nan, nan]}, index=idx)  # fmt: skip
    out = onchain.onchain_metrics(raw)
    assert out["realized_cap"].tolist() == [100.0, 400.0]
    assert out["realized_price"].tolist() == [10.0, 40.0]
    assert out["nupl"].tolist() == pytest.approx([0.5, 1 - 1 / 0.75])
    mc, rc = out["market_cap"], out["realized_cap"]
    assert ((mc - rc) / mc).tolist() == pytest.approx(out["nupl"].tolist())


def test_coin_summary() -> None:
    closes = [100.0 + i for i in range(40)]  # 100 .. 139 from 2024-01-01
    closes[9] = 200.0  # the ATH, 30 days before the last close (close-only: high = close)
    s = summary.coin_summary(frame(closes))
    assert (s.date, s.close) == (dt.date(2024, 2, 9), 139.0)
    assert s.change_1d == pytest.approx(139 / 138 - 1)
    assert s.change_7d == pytest.approx(139 / 132 - 1)
    assert s.change_30d == pytest.approx(139 / 200 - 1)  # 30 days back is the spike
    assert (s.ath, s.ath_date) == (200.0, dt.date(2024, 1, 10))
    assert s.ath_distance == pytest.approx(139 / 200 - 1)
    assert s.regime == "insufficient_data"
    gap = frame(closes).drop(pd.Timestamp("2024-02-08", tz="UTC"))
    # a missing day: compare with the last close on or before one day ago
    assert summary.coin_summary(gap).change_1d == pytest.approx(139 / 137 - 1)
    short = summary.coin_summary(frame(closes[:5]))
    assert short.change_7d is None and short.change_30d is None
    empty = summary.coin_summary(frame(closes), dt.date(2023, 1, 1))
    assert empty.close is None and empty.regime == "insufficient_data"
