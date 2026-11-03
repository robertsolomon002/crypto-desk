"""Gemini extract pipeline (Stages 6.1, D48 and D49): v2 schema with scenarios, repair, model
chain, low-detail fallback, the per-scenario D25 check, earlier views as context, v1 payloads
read as v2, and spend reporting. Gemini is faked; no MCO text is in this repo."""

import datetime as dt
import json
from decimal import Decimal

import pytest

from desk.agents import cost
from desk.mco import summarize as summ
from desk.mco.schemas import Extract, load_payload, response_schema

URL = "https://www.youtube.com/watch?v=fakeVideo01"
DAY = dt.date(2026, 11, 2)


def scenario(name="primary", bias="bearish", targets=(58000.0,), invalidation=72000.0, **kw):
    return {
        "name": name,
        "color": "white" if name == "primary" else "orange",
        "bias": bias,
        "description": f"{name} case",
        "levels": [{"price": 61000, "label": "fib"}],
        "targets": list(targets),
        "invalidation": invalidation,
        "trigger": None,
        **kw,
    }


def view(scenarios=None, **kw) -> dict:
    base = {
        "coin": "BTC",
        "bias": "bearish",
        "wave_position": "wave B",
        "timeframe": "weeks",
        "key_levels": [{"price": 60000, "label": "support"}],
        "scenarios": scenarios
        or [scenario(), scenario("alternative", "bullish", (80000.0,), 55000.0)],
        "extraction_confidence": "high",
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


def test_valid_first_answer_with_two_scenarios() -> None:
    spent = []
    fake = FakeGemini({("video", "lite"): [good()]})
    out = run(fake, spent)
    assert out.model == "lite" and not out.low_detail and out.calls == 1
    c = out.extract.coins[0]
    assert [(s.name, s.bias, s.color) for s in c.scenarios] == [
        ("primary", "bearish", "white"),
        ("alternative", "bullish", "orange"),
    ]
    assert spent == [("lite", 1000, 100)]
    prompt = fake.calls[0][2]
    assert "2026-11-02" in prompt and "<earlier_views>\nnone\n</earlier_views>" in prompt


def test_earlier_views_go_into_the_prompt() -> None:
    fake = FakeGemini({("video", "lite"): [good()]})
    run(fake, previous="BTC (video of 2026-11-01): bearish; wave B")
    assert "BTC (video of 2026-11-01): bearish; wave B\n</earlier_views>" in fake.calls[0][2]


def test_previous_views_text() -> None:
    a = Extract.model_validate_json(good())
    b = Extract.model_validate_json(good(coin="ETH"))
    newer = Extract.model_validate_json(good(bias="bullish", wave_position="wave C"))
    text = summ.previous_views(
        [(dt.date(2026, 10, 30), a), (dt.date(2026, 10, 31), b), (dt.date(2026, 11, 1), newer)]
    )
    lines = text.splitlines()
    assert lines[0] == "BTC (video of 2026-11-01): bullish; wave C"  # newest view per coin
    assert lines[1].startswith("  primary: bearish; primary case Targets 58000; invalidation")
    assert "ETH (video of 2026-10-31)" in text and "2026-10-30" not in text


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
    assert out.extract.coins[0].extraction_confidence == "low"
    assert "<video_title>\nFake title\n</video_title>" in fake.calls[-1][2]


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
    ("sc", "flag"),
    [
        (
            scenario(bias="bullish", targets=(50000.0,), invalidation=None),
            "primary: bias bullish but every target is below",
        ),
        (
            scenario(bias="bullish", targets=(), invalidation=70000.0),
            "primary: bias bullish but the invalidation is above",
        ),
        (
            scenario(bias="bearish", targets=(80000.0,), invalidation=None),
            "primary: bias bearish but every target is above",
        ),
        (scenario(), None),
        (scenario(bias="neutral", targets=(80000.0,), invalidation=None), None),
    ],
)
def test_consistency_check_per_scenario(sc, flag) -> None:
    alt = scenario("alternative", "bullish", (80000.0,), 55000.0)
    out = run(FakeGemini({("video", "lite"): [good(scenarios=[sc, alt])]}), closes={"BTC": 65000.0})
    if flag:
        assert out.extract.coins[0].extraction_confidence == "low"
        assert out.extract.checks[0].startswith(f"BTC {flag}")
    else:
        assert out.extract.checks == [] and out.extract.coins[0].extraction_confidence == "high"


def test_alternative_scenario_is_checked_too() -> None:
    bad_alt = scenario("alternative", "bullish", (50000.0,), None)
    out = run(
        FakeGemini({("video", "lite"): [good(scenarios=[scenario(), bad_alt])]}),
        closes={"BTC": 65000.0},
    )
    assert out.extract.checks == [
        "BTC alternative: bias bullish but every target is below the last close (65000)"
    ]


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
        Extract.model_validate(
            {"coins": [view(scenarios=[scenario(name="third")])], "summary": "s"}
        )
    schema = json.dumps(response_schema())
    assert "checks" not in response_schema()["properties"]
    assert "scenarios" in schema and "pivot_label" not in schema and "wave_label" not in schema


def test_v1_payloads_read_as_v2_without_labels() -> None:
    v1 = {
        "coins": [
            {
                "coin": "SOL",
                "bias": "bearish",
                "wave_position": "wave 3",
                "primary_scenario": "down",
                "alternative_scenario": "low is in",
                "key_levels": [{"price": 31.5, "label": "support"}],
                "invalidation": None,
                "targets": [42.5, 38.0],
                "timeframe": "days",
                "extraction_confidence": "high",
                "pivot_labels": [
                    {
                        "wave_label": "3",
                        "pivot_kind": "low",
                        "approx_date": "2026-11-04",
                        "approx_price": 88,
                        "chart_timeframe": "1h",
                    }
                ],
            }
        ],
        "summary": "s",
        "checks": [],
    }
    ex = load_payload(v1, "mco_extract_v1")
    c = ex.coins[0]
    assert [s.name for s in c.scenarios] == ["primary", "alternative"]
    assert c.scenarios[0].targets == [42.5, 38.0] and c.scenarios[1].bias == "neutral"
    assert "pivot_labels" not in ex.model_dump_json() and "wave_label" not in ex.model_dump_json()


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
    assert summ.PROMPT_VERSION == "mco_extract_v2"
    for name in ("mco_extract_v2", "mco_repair_v1", "mco_fallback_v2"):
        assert "untrusted" in summ.load_prompt(name)
