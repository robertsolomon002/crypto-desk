"""The scorecard on hand-computed cases (Stage 7.2, D52)."""

import datetime as dt

import pytest

from desk.signals.score import EARLY_WEEKS, Resolved, compound, scorecard, stats

W1, W2 = dt.date(2026, 11, 9), dt.date(2026, 11, 16)


def row(week, coin, stance, conf, hit, brier, first, pnl, source="desk") -> Resolved:
    return Resolved(week, coin, source, stance, conf, hit, brier, first, pnl)


# By hand:
# W1 BTC lean_long 0.7, closed up:   hit, (0.7-1)^2 = 0.09, target first,       +5%
# W1 ETH flat 0.6, closed up:        miss, P(up) 0.4, (0.4-1)^2 = 0.36, no levels, 0
# W2 BTC lean_long 0.8, closed down: miss, 0.8^2 = 0.64, invalidation first,     -3%
# W2 ETH lean_long 0.6, closed up:   hit, 0.4^2 = 0.16, neither,                 +1%
DESK = [
    row(W1, "BTC", "lean_long", 0.7, True, 0.09, "target", 0.05),
    row(W1, "ETH", "flat", 0.6, False, 0.36, None, 0.0),
    row(W2, "BTC", "lean_long", 0.8, False, 0.64, "invalidation", -0.03),
    row(W2, "ETH", "lean_long", 0.6, True, 0.16, "neither", 0.01),
]
FLIP = [
    row(W1, "BTC", "flat", 0.5, False, 0.25, None, 0.0, "coinflip"),
    row(W2, "BTC", "flat", 0.5, True, 0.25, None, 0.0, "coinflip"),
]


def test_per_source_stats() -> None:
    s = stats(DESK)
    assert (s.signals, s.weeks, s.hits, s.hit_rate) == (4, 2, 2, 0.5)
    assert s.brier == pytest.approx(1.25 / 4)  # 0.3125
    assert (s.with_levels, s.target_first, s.invalidation_first, s.neither) == (3, 1, 1, 1)
    assert s.target_first_rate == pytest.approx(1 / 3)
    assert s.long_weeks == 3
    # Equal weight per week: W1 (5% + 0) / 2 = 2.5%, W2 (-3% + 1%) / 2 = -1%; 1.025 * 0.99 - 1
    assert s.paper_return == pytest.approx(0.01475)
    assert s.early_days


def test_per_coin_and_cumulative() -> None:
    card = scorecard(DESK + FLIP, version=1)
    assert list(card.by_source) == ["desk", "coinflip"]  # the SOURCES order
    btc = card.by_coin[("desk", "BTC")]
    assert btc.paper_return == pytest.approx(1.05 * 0.97 - 1)  # 0.0185
    assert btc.brier == pytest.approx((0.09 + 0.64) / 2)
    assert card.by_coin[("desk", "ETH")].target_first_rate == 0.0  # one with levels: neither
    assert card.by_source["coinflip"].brier == pytest.approx(0.25)
    assert card.by_source["coinflip"].target_first_rate is None  # no levels at all
    assert card.by_source["coinflip"].paper_return == 0.0
    w1, w2 = card.cumulative["desk"]
    assert (w1.week, w1.signals, w1.hit_rate) == (W1, 2, 0.5)
    assert w1.brier == pytest.approx(0.225) and w1.paper_return == pytest.approx(0.025)
    assert (w2.week, w2.signals) == (W2, 4)
    assert w2.brier == pytest.approx(0.3125) and w2.paper_return == pytest.approx(0.01475)
    assert card.weeks == [W1, W2]


def test_early_days_ends_at_twelve_weeks() -> None:
    weeks = [W1 + dt.timedelta(weeks=i) for i in range(EARLY_WEEKS)]
    rows = [row(w, "BTC", "flat", 0.5, True, 0.25, None, 0.0) for w in weeks]
    assert not stats(rows).early_days
    assert stats(rows[:-1]).early_days


def test_empty_and_compound() -> None:
    s = stats([])
    assert (s.signals, s.hit_rate, s.brier, s.target_first_rate, s.paper_return) == (
        0, None, None, None, 0.0
    )  # fmt: skip
    assert compound([0.1, -0.1]) == pytest.approx(-0.01)
    assert scorecard([], 1).by_source == {}
