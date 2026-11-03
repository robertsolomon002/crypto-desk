"""Gemini extract pipeline (Stage 6.1): schema, repair, model chain, low-detail fallback, the
D25 consistency check and spend reporting. Gemini is faked; no MCO text is in this repo."""

import datetime as dt
import json
from decimal import Decimal

import pytest

from desk.agents import cost
from desk.mco import summarize as summ
from desk.mco.schemas import Extract, response_schema

URL = "https://www.youtube.com/watch?v=fakeVideo01"
DAY = dt.date(2026, 11, 2)


def view(**kw) -> dict:
    base = {
        "coin": "BTC",
        "bias": "bearish",
        "wave_position": "wave B",
        "primary_scenario": "C",
        "alternative_scenario": "up",
        "key_levels": [{"price": 60000, "label": "support"}],
        "invalidation": 72000,
        "targets": [58000],
        "timeframe": "weeks",
        "extraction_confidence": "high",
        "pivot_labels": [
            {
                "wave_label": "B",
                "pivot_kind": "high",
                "approx_date": "2026-10-20",
                "approx_price": 70000,
                "chart_timeframe": "1d",
            }
        ],
    }
    return {**base, **kw}


def good(**kw) -> str:
    return json.dumps({"coins": [view(**kw)], "summary": "A made-up summary."})


class FakeGemini:
    """Scripted replies per (kind, model); an Exception instance is raised."""

    def __init__(self, script: dict[tuple[str, str], list]) -> None:
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[tuple[str, str, str]] = []

    def _next(self, kind: str, model: str, prompt: str) -> summ.Reply:
        self.calls.append((kind, model, prompt))
        item = self.script[(kind, model)].pop(0)
        if isinstance(item, Exception):
            raise item
        return summ.Reply(item, 1000, 100)

    def video(self, model, url, prompt):
        return self._next("video", model, prompt)

    def text(self, model, prompt):
        return self._next("text", model, prompt)


MODELS = ["lite", "flash"]


def run(fake, spent=None, **kw):
    spent = spent if spent is not None else []
    return summ.summarize(
        fake,
        URL,
        "Fake title",
        "Fake description",
        DAY,
        lambda m, i, o: spent.append((m, i, o)),
        models=MODELS,
        **kw,
    )


def test_valid_first_answer() -> None:
    spent = []
    fake = FakeGemini({("video", "lite"): [good()]})
    out = run(fake, spent)
    assert out.model == "lite" and not out.low_detail and out.calls == 1
    assert out.extract.coins[0].coin == "BTC" and spent == [("lite", 1000, 100)]
    assert "2026-11-02" in fake.calls[0][2]  # publication date in the prompt


def test_repair_once_then_valid() -> None:
    bad = good(bias="sideways")
    fake = FakeGemini({("video", "lite"): [bad], ("text", "lite"): [good()]})
    spent = []
    out = run(fake, spent)
    assert out.model == "lite" and out.calls == 2 and len(spent) == 2
    assert "coins.0.bias" in fake.calls[1][2]  # error locations in the repair prompt


def test_chain_moves_on_after_503_and_after_failed_repair() -> None:
    fake = FakeGemini({("video", "lite"): [summ.GeminiError("503")], ("video", "flash"): [good()]})
    out = run(fake)
    assert out.model == "flash" and out.errors == ["lite:503"]

    fake = FakeGemini(
        {
            ("video", "lite"): ["{not json"],
            ("text", "lite"): ["{still not"],
            ("video", "flash"): [good()],
        }
    )
    assert run(fake).model == "flash"


def test_low_detail_fallback() -> None:
    fake = FakeGemini(
        {
            ("video", "lite"): [summ.GeminiError("timeout")],
            ("video", "flash"): [summ.GeminiError("503")],
            ("text", "lite"): [good()],
        }
    )
    out = run(fake)
    assert out.low_detail and out.model == "lite"
    c = out.extract.coins[0]
    assert c.extraction_confidence == "low" and c.pivot_labels == []
    prompt = fake.calls[-1][2]
    assert "<video_title>\nFake title\n</video_title>" in prompt


def test_everything_fails() -> None:
    err = summ.GeminiError("429")
    fake = FakeGemini({(k, m): [err] for k in ("video", "text") for m in MODELS})
    with pytest.raises(summ.SummarizeFailed) as exc:
        run(fake)
    assert exc.value.code == "flash:fallback:429"


def test_braces_in_description_do_not_break_the_prompt() -> None:
    fake = FakeGemini(
        {
            ("video", "lite"): [summ.GeminiError("503")],
            ("video", "flash"): [summ.GeminiError("503")],
            ("text", "lite"): [good()],
        }
    )
    summ.summarize(fake, URL, "t", "price {title} {0} }{", DAY, lambda *a: None, models=MODELS)
    assert "price {title} {0} }{" in fake.calls[-1][2]


@pytest.mark.parametrize(
    ("kw", "flag"),
    [
        ({"bias": "bullish", "targets": [50000], "invalidation": None}, "every target is below"),
        ({"bias": "bullish", "targets": [], "invalidation": 70000}, "invalidation is above"),
        ({"bias": "bearish", "targets": [80000], "invalidation": None}, "every target is above"),
        ({"bias": "bearish", "targets": [58000], "invalidation": 72000}, None),
        ({"bias": "neutral", "targets": [80000], "invalidation": None}, None),
    ],
)
def test_consistency_check(kw, flag) -> None:
    fake = FakeGemini({("video", "lite"): [good(**kw)]})
    out = run(fake, closes={"BTC": 65000.0})
    if flag:
        assert out.extract.coins[0].extraction_confidence == "low"
        assert flag in out.extract.checks[0]
    else:
        assert out.extract.checks == [] and out.extract.coins[0].extraction_confidence == "high"


def test_aliases_and_duplicates() -> None:
    reply = json.dumps(
        {
            "coins": [view(coin="Bitcoin"), view(coin="BTC", bias="bullish"), view(coin="sol")],
            "summary": "s",
        }
    )
    out = run(FakeGemini({("video", "lite"): [reply]}), aliases={"BITCOIN": "BTC", "SOL": "SOL"})
    assert [(c.coin, c.bias) for c in out.extract.coins] == [("BTC", "bearish"), ("SOL", "bearish")]


def test_schema_rules() -> None:
    long = " ".join(["word"] * 200)
    ex = Extract.model_validate_json(json.dumps({"coins": [view()], "summary": long}))
    assert len(ex.summary.split()) == 121  # 120 words and an ellipsis
    with pytest.raises(ValueError):
        Extract.model_validate({"coins": [view(coin="not a ticker!")], "summary": "s"})
    with pytest.raises(ValueError):
        bad = view(pivot_labels=[{**view()["pivot_labels"][0], "approx_date": "last week"}])
        Extract.model_validate({"coins": [bad], "summary": "s"})
    schema = response_schema()
    assert "checks" not in schema["properties"]
    assert "pivot_kind" in json.dumps(schema)


def test_gemini_is_free_on_the_free_tier(monkeypatch) -> None:
    monkeypatch.setattr(
        cost,
        "load_models_config",
        lambda: {
            "gemini_tier": "free",
            "prices": {"gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50}},
        },
    )
    assert cost.call_cost("gemini-3.5-flash-lite", 84_000, 1_100) == Decimal(0)
    monkeypatch.setattr(
        cost,
        "load_models_config",
        lambda: {
            "gemini_tier": "paid",
            "prices": {"gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50}},
        },
    )
    assert cost.call_cost("gemini-3.5-flash-lite", 84_000, 1_100) == Decimal("0.027950")


def test_real_config_chain_and_prompts_exist() -> None:
    assert summ.model_chain() == ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
    for name in ("mco_extract_v1", "mco_repair_v1", "mco_fallback_v1"):
        assert "untrusted" in summ.load_prompt(name)
