"""The weekly brief writer (Section 3.3, Stage 7.1, D51): one call, no tools.

It gets, per coin, the desk's run (analyst reports, the debate, the signal and the validator's
verdict), every source's signal for the week (desk, coin flip, trend rule, MCO) and the key
levels, all as untrusted data. It returns a structured brief: a 5-line summary, and per coin
the setup, bull case, bear case, what would change the view and levels to watch. `render`
turns that into the Markdown stored in `briefs.content`.

Server key only: `server.brief_writer` (Sonnet 5.5), or `server.brief_writer_degraded` (Haiku
5.5) once spend reaches the Decision 9 degrade point (step 3). Sonnet 5.5 refuses forced tool
choice, so structured output uses `json_schema` (DATA_SOURCES, Stage 0.3). Spend is recorded
with source `brief`.
"""

import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from desk.agents import cost, tracing
from desk.config import get_settings, load_app_settings, load_models_config

PROMPT = "brief_v1.md"
PROMPT_VERSION = "brief_v1"
SUMMARY_LINES = 5


class BriefError(RuntimeError):
    """The brief couldn't be written (no key, budget used up, unreadable output)."""


class LevelOut(BaseModel):
    label: str = Field(description="What the level is, e.g. 'desk invalidation', '20W SMA'")
    price: float = Field(description="USD")


class CoinBriefOut(BaseModel):
    coin: str = Field(description="Ticker, e.g. BTC")
    setup: str = Field(description="Where the coin stands and the desk's call, at most 60 words")
    bull_case: str = Field(description="At most 50 words")
    bear_case: str = Field(description="At most 50 words")
    what_would_change: str = Field(description="What would change the view, at most 40 words")
    levels_to_watch: list[LevelOut] = Field(description="2 to 5 levels, nearest first")


class BriefOut(BaseModel):
    """The weekly brief."""

    summary: list[str] = Field(description=f"Exactly {SUMMARY_LINES} lines, at most 25 words each")
    coins: list[CoinBriefOut] = Field(description="One entry per coin given, in the same order")


@dataclass
class BriefResult:
    brief: BriefOut
    content: str
    model: str
    tokens_in: int
    tokens_out: int
    cost: Decimal


def brief_settings() -> dict[str, Any]:
    return load_app_settings().get("brief") or {}


def choose_model(degraded: bool) -> str:
    server = load_models_config().get("server") or {}
    name = server.get("brief_writer_degraded" if degraded else "brief_writer")
    if not name:
        raise BriefError("the brief writer model isn't configured")
    return name


def make_model(name: str) -> BaseChatModel:
    key = get_settings().anthropic_api_key
    if key is None or not key.get_secret_value():
        raise BriefError("the server key isn't configured")
    cfg = brief_settings()
    return ChatAnthropic(
        model=name,
        api_key=key,
        max_tokens=int(cfg.get("max_output_tokens", 8000)),
        timeout=float(cfg.get("timeout_seconds", 180)),
        max_retries=2,
    )


def estimate(n_coins: int, model: str) -> dict[str, Any]:
    """Typical tokens for one brief (`brief.estimate_tokens`: fixed plus per coin) and its USD."""
    cfg = brief_settings().get("estimate_tokens") or {}
    base, per = cfg.get("base", [2000, 300]), cfg.get("per_coin", [6000, 700])
    tin, tout = int(base[0]) + n_coins * int(per[0]), int(base[1]) + n_coins * int(per[1])
    price = None
    if model in (load_models_config().get("prices") or {}):
        price = float(cost.call_cost(model, tin, tout))
    return {"model": model, "tokens_in": tin, "tokens_out": tout, "cost_usd": price}


def _block(title: str, payload: Any) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"<{title}>\n{body}\n</{title}>"


def messages(week: dt.date, as_of: dt.date, coins: list[dict[str, Any]]) -> list[Any]:
    text = (get_settings().prompts_dir / PROMPT).read_text(encoding="utf-8")
    system = text.replace("{week}", week.isoformat()).replace("{as_of}", as_of.isoformat())
    order = ", ".join(c["coin"] for c in coins)
    task = (
        f"Write the brief for the week starting {week} (data up to {as_of}, UTC). Coins, "
        f"in this order: {order}.\n\n" + "\n\n".join(_block("coin", c) for c in coins)
    )
    return [SystemMessage(system), HumanMessage(task)]


def _fmt(price: float) -> str:
    return f"{price:,.2f}" if price >= 100 else f"{price:.4g}"


def render(week: dt.date, brief: BriefOut, model: str) -> str:
    """The stored Markdown. Model text goes in as plain lines (the UI sanitizes Markdown)."""
    lines = [f"# Weekly brief: week of {week.isoformat()}", "", "## Summary", ""]
    lines += [f"- {s.strip()}" for s in brief.summary]
    for c in brief.coins:
        lines += [
            "",
            f"## {c.coin}",
            "",
            f"**Setup.** {c.setup.strip()}",
            "",
            f"**Bull case.** {c.bull_case.strip()}",
            "",
            f"**Bear case.** {c.bear_case.strip()}",
            "",
            f"**What would change the view.** {c.what_would_change.strip()}",
        ]
        if c.levels_to_watch:
            lines += [
                "",
                "**Levels to watch (USD):** "
                + "; ".join(f"{lv.label} {_fmt(lv.price)}" for lv in c.levels_to_watch),
            ]
    lines += ["", f"_Written by {model} from the desk's reports and debate. Not financial advice._"]
    return "\n".join(lines)


def check(brief: BriefOut, coins: list[str]) -> list[str]:
    problems = []
    if len(brief.summary) != SUMMARY_LINES:
        problems.append(f"summary has {len(brief.summary)} lines, not {SUMMARY_LINES}")
    got = [c.coin.upper() for c in brief.coins]
    if got != coins:
        problems.append(f"coins {got} don't match {coins}")
    return problems


async def write(
    session: Session,
    *,
    week: dt.date,
    as_of: dt.date,
    coins: list[dict[str, Any]],
    model: BaseChatModel | None = None,
) -> BriefResult:
    """Write the brief on the server key. Raises `BriefError` (budget, key, output) and lets
    provider errors through after the client's retries."""
    try:
        degraded = cost.check_budget(session).degraded
    except cost.BudgetExceeded as e:
        raise BriefError(str(e)) from None
    name = choose_model(degraded)
    chat_model = model or make_model(name)
    runnable = chat_model.with_structured_output(BriefOut, method="json_schema", include_raw=True)
    runnable = runnable.with_config(tags=["brief"], run_name="brief_writer")
    with tracing.agent_tracing(server_key=True, metadata={"week": week.isoformat(), "brief": True}):
        out = await runnable.ainvoke(messages(week, as_of, coins))
    raw = out.get("raw")
    meta = getattr(raw, "usage_metadata", None) or {}
    tin, tout = int(meta.get("input_tokens", 0)), int(meta.get("output_tokens", 0))
    spent = cost.record(session, "brief", name, tin, tout)
    brief = out.get("parsed")
    if brief is None or out.get("parsing_error") is not None:
        raise BriefError("the brief writer's output didn't match the schema")
    symbols = [c["coin"] for c in coins]
    problems = check(brief, symbols)
    if any("coins" in p for p in problems):
        raise BriefError("; ".join(problems))
    return BriefResult(
        brief=brief,
        content=render(week, brief, name),
        model=name,
        tokens_in=tin,
        tokens_out=tout,
        cost=spent,
    )
