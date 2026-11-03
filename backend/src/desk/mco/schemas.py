"""The strict JSON a video extract must match, sent to Gemini as the response schema and
validated with Pydantic afterwards.

- v2 (`Extract`, `prompts/mco_extract_v2.md`, D49): per coin, a primary and an alternative
  scenario, each with its own bias, levels, targets, invalidation and trigger, plus shared
  support and resistance. No wave labels: Rob dropped chart wave counts after Flash-Lite gave
  a different label set on every run of the same video (D49).
- v1 (`ExtractV1`, Stage 6.1, D48) is kept only to read extracts stored before v2.

Everything in an extract is untrusted model output about MCO's private views (Decision 6): it
lives only in the database, is rendered as text, and never goes into logs.
"""

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Bias = Literal["bullish", "bearish", "neutral"]
Confidence = Literal["high", "medium", "low"]
SUMMARY_MAX_WORDS = 120


def _ticker(v: str) -> str:
    v = v.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,10}", v):
        raise ValueError("coin must be a ticker symbol")
    return v


def _trim(v: str) -> str:
    words = v.split()
    if len(words) > SUMMARY_MAX_WORDS:  # trimmed rather than rejected
        return " ".join(words[:SUMMARY_MAX_WORDS]) + " …"
    return v.strip()


class Level(BaseModel):
    price: float = Field(gt=0)
    label: str = Field(description="What the level is, e.g. 'support', '61.8% retracement'")


# --- v2 ---------------------------------------------------------------------------------------


class Scenario(BaseModel):
    name: Literal["primary", "alternative"]
    color: str | None = Field(
        description="Colour he draws this scenario in on his charts, e.g. 'white', 'orange'; "
        "null if not shown"
    )
    bias: Bias
    description: str = Field(description="One or two sentences: what he expects in this case")
    levels: list[Level] = Field(description="Levels that belong to this scenario")
    targets: list[float] = Field(description="Target prices of this scenario, in USD")
    invalidation: float | None = Field(description="Price that invalidates this scenario")
    trigger: str | None = Field(
        description="What would confirm this scenario, e.g. 'a break above $100'"
    )


class CoinView(BaseModel):
    coin: str = Field(description="Ticker symbol, e.g. BTC, ETH, SOL")
    bias: Bias = Field(description="Bias of the primary scenario")
    wave_position: str = Field(description="Where he says price is in his count, in words")
    timeframe: str = Field(description="Horizon of the view, e.g. 'days', 'weeks', 'months'")
    key_levels: list[Level] = Field(description="Support and resistance not tied to one scenario")
    scenarios: list[Scenario] = Field(description="The primary scenario first, then alternatives")
    extraction_confidence: Confidence = Field(
        description="How sure you are that this extraction matches what the video says"
    )

    @field_validator("coin")
    @classmethod
    def _coin(cls, v: str) -> str:
        return _ticker(v)


class Extract(BaseModel):
    coins: list[CoinView]
    summary: str = Field(description=f"Overall summary, at most {SUMMARY_MAX_WORDS} words")
    # Added by the pipeline, not by the model: deterministic checks that lowered confidence.
    checks: list[str] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def _summary(cls, v: str) -> str:
        return _trim(v)


def response_schema() -> dict:
    """The JSON schema Gemini is asked to follow (without the pipeline-only `checks`)."""
    schema = Extract.model_json_schema()
    schema["properties"].pop("checks", None)
    return schema


# --- v1 (read-only) ---------------------------------------------------------------------------


class PivotLabel(BaseModel):
    wave_label: str
    pivot_kind: Literal["high", "low"]
    approx_date: str
    approx_price: float = Field(gt=0)
    chart_timeframe: str

    @field_validator("approx_date")
    @classmethod
    def _iso_date(cls, v: str) -> str:
        dt.date.fromisoformat(v.strip()[:10])
        return v.strip()[:10]


class CoinViewV1(BaseModel):
    coin: str
    bias: Bias
    wave_position: str
    primary_scenario: str
    alternative_scenario: str
    key_levels: list[Level]
    invalidation: float | None
    targets: list[float]
    timeframe: str
    extraction_confidence: Confidence
    pivot_labels: list[PivotLabel]


class ExtractV1(BaseModel):
    coins: list[CoinViewV1]
    summary: str
    checks: list[str] = Field(default_factory=list)


def upgrade_v1(payload: dict) -> Extract:
    """A stored v1 payload in the v2 shape: the primary scenario takes the bias, targets and
    invalidation; the alternative's bias is unknown (neutral). Wave labels are dropped."""
    old = ExtractV1.model_validate(payload)
    coins = []
    for c in old.coins:
        primary = Scenario(
            name="primary",
            color=None,
            bias=c.bias,
            description=c.primary_scenario,
            levels=[],
            targets=c.targets,
            invalidation=c.invalidation,
            trigger=None,
        )
        alt = Scenario(
            name="alternative",
            color=None,
            bias="neutral",
            description=c.alternative_scenario,
            levels=[],
            targets=[],
            invalidation=None,
            trigger=None,
        )
        coins.append(
            CoinView(
                coin=c.coin,
                bias=c.bias,
                wave_position=c.wave_position,
                timeframe=c.timeframe,
                key_levels=c.key_levels,
                scenarios=[primary, alt],
                extraction_confidence=c.extraction_confidence,
            )
        )
    return Extract(coins=coins, summary=old.summary, checks=old.checks)


def load_payload(payload: dict, prompt_version: str) -> Extract:
    """Any stored extract as v2."""
    if prompt_version == "mco_extract_v1":
        return upgrade_v1(payload)
    return Extract.model_validate(payload)
