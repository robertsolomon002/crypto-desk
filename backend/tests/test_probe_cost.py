import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from probe_cost import CostGuard, SpendCapError, cost  # noqa: E402


def test_cost_per_million_tokens() -> None:
    assert cost("claude-sonnet-5-5", 1_000_000, 0) == pytest.approx(2.00)
    assert cost("claude-haiku-5-5", 1000, 1000) == pytest.approx(0.0006)


def test_guard_blocks_call_that_could_exceed_cap() -> None:
    guard = CostGuard(cap_usd=0.01)
    guard.check("claude-haiku-5-5", 10_000, 1000)  # worst case $0.0015
    guard.charge("claude-haiku-5-5", 10_000, 1000)
    with pytest.raises(SpendCapError):
        guard.check("claude-sonnet-5-5", 10_000, 1000)  # worst case $0.03


def test_free_tier_never_counts_against_cap() -> None:
    guard = CostGuard(cap_usd=0.0)
    assert guard.check("gemini-3.8-flash", 200_000, 8000) == 0.0
    guard.charge("gemini-3.8-flash", 120_000, 2000)
    assert guard.spent_usd == 0.0
    assert guard.paid_equivalent_usd == pytest.approx(0.0975)
