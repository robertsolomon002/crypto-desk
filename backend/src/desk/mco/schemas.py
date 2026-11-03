"""The strict JSON a video extract must match (Section 3.4), sent to Gemini as the response
schema and validated with Pydantic afterwards.

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


class Level(BaseModel):
    price: float = Field(gt=0)
    label: str = Field(description="What the level is, e.g. 'support', 'wave 4 low', 'target'")


class PivotLabel(BaseModel):
    wave_label: str = Field(description="The wave label as he writes it, e.g. '1', 'iii', 'B'")
    pivot_kind: Literal["high", "low"] = Field(
        description="Whether the label sits on a swing high or a swing low"
    )
    approx_date: str = Field(description="Date of the swing, YYYY-MM-DD")
    approx_price: float = Field(gt=0, description="Price of the swing in USD")
    chart_timeframe: str = Field(description="Chart the label is drawn on: 1d, 1w, 4h, ...")

    @field_validator("approx_date")
    @classmethod
    def _iso_date(cls, v: str) -> str:
        dt.date.fromisoformat(v.strip()[:10])
        return v.strip()[:10]


class CoinView(BaseModel):
    coin: str = Field(description="Ticker symbol, e.g. BTC, ETH, SOL")
    bias: Bias
    wave_position: str = Field(description="Where he says price is in the wave count")
    primary_scenario: str
    alternative_scenario: str
    key_levels: list[Level]
    invalidation: float | None = Field(description="Price that invalidates the primary count")
    targets: list[float]
    timeframe: str = Field(description="Horizon of the view, e.g. 'days', 'weeks', 'months'")
    extraction_confidence: Confidence = Field(
        description="How sure you are that this extraction matches what the video says"
    )
    pivot_labels: list[PivotLabel]

    @field_validator("coin")
    @classmethod
    def _ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{2,10}", v):
            raise ValueError("coin must be a ticker symbol")
        return v


class Extract(BaseModel):
    coins: list[CoinView]
    summary: str = Field(description=f"Overall summary, at most {SUMMARY_MAX_WORDS} words")
    # Added by the pipeline, not by the model: deterministic checks that lowered confidence.
    checks: list[str] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def _short(cls, v: str) -> str:
        words = v.split()
        if len(words) > SUMMARY_MAX_WORDS:  # trimmed rather than rejected
            return " ".join(words[:SUMMARY_MAX_WORDS]) + " …"
        return v.strip()


def response_schema() -> dict:
    """The JSON schema Gemini is asked to follow (without the pipeline-only `checks`)."""
    schema = Extract.model_json_schema()
    schema["properties"].pop("checks", None)
    return schema
