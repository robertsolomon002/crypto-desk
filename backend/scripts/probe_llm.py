"""Stage 0.3 LLM probe (local only; hard spend cap $0.25 on Rob's server keys).

Run from `backend/`:
    uv run python scripts/probe_llm.py [--only anthropic,openrouter,gemini,mcp,notify]

- Anthropic: structured output (json_schema) on Haiku 4.5, Haiku 5.5 and Sonnet 5.5.
- OpenRouter: the friends' path, through LangChain's OpenAI-compatible client.
- Gemini: MCO's newest public crypto video by YouTube URL -> draft Section 3.4 schema. The
  extracted content is printed to this terminal only; nothing is written to disk (Decision 6).
- MCP: langchain-mcp-adapters stdio round trip to scripts/dummy_mcp_server.py.
- Notify: Telegram and Discord test messages, skipped while their secrets are unset.
LangSmith tracing is forced off so no prompt or MCO content leaves this machine via traces.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Literal

import feedparser
import httpx
from probe_cost import CostGuard, SpendCapError
from pydantic import BaseModel, Field, ValidationError

from desk.config import get_settings

os.environ["LANGSMITH_TRACING"] = "false"

CAP_USD = 0.25
SCRIPTS = Path(__file__).resolve().parent
MCO_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
guard = CostGuard(cap_usd=CAP_USD)
settings = get_settings()


def report(name: str, ok: bool, detail: str) -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name} | {detail}", flush=True)


# --- Anthropic ------------------------------------------------------------------------------


class TinySignal(BaseModel):
    coin: Literal["BTC", "ETH", "SOL"]
    stance: Literal["lean_long", "flat"]
    confidence: float = Field(ge=0.5, le=0.95)
    rationale: str = Field(max_length=200)


SIGNAL_PROMPT = (
    "Return an example weekly signal for BTC as test data. Stance flat, confidence 0.55, "
    "a one-sentence rationale saying this is a probe."
)


def probe_anthropic() -> None:
    from langchain_anthropic import ChatAnthropic

    key = settings.anthropic_api_key
    if key is None:
        report("anthropic", False, "ANTHROPIC_API_KEY not set")
        return
    # Haiku 4.5 has no `effort`; the 5.5 models take effort="low" for a cheap probe.
    for model, extra in [
        ("claude-haiku-4-5", {}),
        ("claude-haiku-5-5", {"reasoning_effort": "low"}),
        ("claude-sonnet-5-5", {"reasoning_effort": "low"}),
    ]:
        try:
            guard.check(model, 1000, 2000)
            llm = ChatAnthropic(model=model, api_key=key, max_tokens=2000, **extra)
            runnable = llm.with_structured_output(
                TinySignal, method="json_schema", include_raw=True
            )
            t0 = time.perf_counter()
            out = runnable.invoke(SIGNAL_PROMPT)
            dt = time.perf_counter() - t0
            usage = out["raw"].usage_metadata or {}
            c = guard.charge(model, usage.get("input_tokens", 0), usage.get("output_tokens", 0))
            parsed = out["parsed"]
            report(
                f"anthropic:{model}",
                parsed is not None,
                f"{dt:.1f}s in={usage.get('input_tokens')} out={usage.get('output_tokens')} "
                f"${c:.5f} parsed={parsed!r}",
            )
        except SpendCapError as exc:
            report(f"anthropic:{model}", False, str(exc))
        except Exception as exc:
            report(f"anthropic:{model}", False, f"{type(exc).__name__}: {str(exc)[:300]}")


# --- OpenRouter -----------------------------------------------------------------------------

OPENROUTER_MODEL = "anthropic/claude-haiku-5.5"


def probe_openrouter() -> None:
    from langchain_openai import ChatOpenAI

    key = settings.openrouter_api_key
    if key is None:
        report("openrouter", False, "OPENROUTER_API_KEY not set")
        return
    llm = ChatOpenAI(
        model=OPENROUTER_MODEL,
        api_key=key,
        base_url="https://openrouter.ai/api/v1",
        max_tokens=1000,
    )
    for method in ["json_schema", "function_calling"]:
        try:
            guard.check(OPENROUTER_MODEL, 1000, 1000)
            t0 = time.perf_counter()
            out = llm.with_structured_output(TinySignal, method=method, include_raw=True).invoke(
                SIGNAL_PROMPT
            )
            dt = time.perf_counter() - t0
            usage = out["raw"].usage_metadata or {}
            c = guard.charge(
                OPENROUTER_MODEL, usage.get("input_tokens", 0), usage.get("output_tokens", 0)
            )
            report(
                f"openrouter:{OPENROUTER_MODEL}:{method}",
                out["parsed"] is not None,
                f"{dt:.1f}s in={usage.get('input_tokens')} out={usage.get('output_tokens')} "
                f"${c:.5f} parsed={out['parsed']!r}",
            )
        except Exception as exc:
            report(f"openrouter:{method}", False, f"{type(exc).__name__}: {str(exc)[:300]}")


# --- Gemini + MCO video ---------------------------------------------------------------------


class Level(BaseModel):
    price: float
    label: str


class PivotLabel(BaseModel):
    wave_label: str
    approx_date: str = Field(description="YYYY-MM-DD")
    approx_price: float
    chart_timeframe: str


class CoinView(BaseModel):
    coin: str
    bias: Literal["bullish", "bearish", "neutral"]
    wave_position: str
    primary_scenario: str
    alternative_scenario: str
    key_levels: list[Level]
    invalidation: float | None
    targets: list[float]
    timeframe: str
    extraction_confidence: Literal["high", "medium", "low"]
    pivot_labels: list[PivotLabel]


class MCOExtract(BaseModel):
    coins: list[CoinView]
    summary: str = Field(description="At most 120 words")


GEMINI_PROMPT = (
    "You are extracting an Elliott wave analyst's views from this public video. For each coin "
    "discussed (BTC, ETH, SOL, others), give the bias, the current wave position, the primary "
    "and alternative scenarios, key price levels with labels, the invalidation level, targets, "
    "the timeframe, how confident you are that the extraction is right, and any wave labels "
    "he places on specific swing highs or lows (label, approximate date, approximate price, "
    "chart timeframe). Only report what the video says; do not add your own analysis. Then "
    "write an overall summary of at most 120 words."
)


def newest_mco_crypto_video() -> str | None:
    import yaml

    cfg = yaml.safe_load((settings.config_dir / "feeds.yaml").read_text(encoding="utf-8"))
    cid = cfg["mco"]["channel_id"]
    keywords = cfg["mco"]["crypto_keywords"]
    feed = feedparser.parse(httpx.get(MCO_FEED.format(cid=cid), timeout=30).content)
    for e in feed.entries:  # newest first
        text = f"{e.get('title', '')} {e.get('summary', '')}".lower()
        if any(k in text for k in keywords):
            return e.link
    return None


def probe_gemini(models: list[str]) -> None:
    from google import genai
    from google.genai import types

    key = settings.google_api_key
    if key is None:
        report("gemini", False, "GOOGLE_API_KEY not set")
        return
    url = newest_mco_crypto_video()
    if url is None:
        report("gemini", False, "no crypto video found in MCO feed")
        return
    client = genai.Client(api_key=key.get_secret_value())
    for model in models:
        try:
            guard.check(model, 300_000, 8000)
            t0 = time.perf_counter()
            resp = client.models.generate_content(
                model=model,
                contents=types.Content(
                    role="user",
                    parts=[
                        types.Part(file_data=types.FileData(file_uri=url)),
                        types.Part(text=GEMINI_PROMPT),
                    ],
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=MCOExtract.model_json_schema(),
                    media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
                ),
            )
            dt = time.perf_counter() - t0
            u = resp.usage_metadata
            tin = u.prompt_token_count or 0
            tout = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
            c = guard.charge(model, tin, tout)
            try:
                extract = MCOExtract.model_validate_json(resp.text)
                valid = True
            except ValidationError as exc:
                extract, valid = None, False
                print(f"  schema errors: {exc.error_count()}")
            report(
                f"gemini:{model}",
                valid,
                f"{dt:.1f}s in={tin} out={tout} paid-equivalent ${c:.4f} (free tier: $0) "
                f"schema_valid={valid}",
            )
            if extract:  # local terminal only (Decision 6)
                for v in extract.coins:
                    levels = ", ".join(f"{lv.price:g} {lv.label}" for lv in v.key_levels)
                    print(
                        f"  {v.coin}: {v.bias} ({v.extraction_confidence}) | {v.wave_position} | "
                        f"levels: {levels} | inval {v.invalidation} | targets {v.targets} | "
                        f"{len(v.pivot_labels)} pivot labels"
                    )
        except Exception as exc:
            report(f"gemini:{model}", False, f"{type(exc).__name__}: {str(exc)[:300]}")


# --- MCP round trip -------------------------------------------------------------------------


async def _mcp() -> None:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "dummy": {
                "command": sys.executable,
                "args": [str(SCRIPTS / "dummy_mcp_server.py")],
                "transport": "stdio",
            }
        }
    )
    tools = await client.get_tools()
    result = await tools[0].ainvoke({"a": 2, "b": 3})
    report("mcp:stdio", "5" in str(result), f"tools={[t.name for t in tools]} 2+3 -> {result!r}")


def probe_mcp() -> None:
    try:
        asyncio.run(_mcp())
    except Exception as exc:
        report("mcp:stdio", False, f"{type(exc).__name__}: {str(exc)[:300]}")


# --- Notify ---------------------------------------------------------------------------------


def probe_notify() -> None:
    text = "Crypto Desk probe (Stage 0.3): test message."
    if settings.telegram_bot_token and settings.telegram_chat_id:
        tok = settings.telegram_bot_token.get_secret_value()
        r = httpx.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": text},
            timeout=30,
        )
        report("telegram", r.is_success, f"HTTP {r.status_code}")
    else:
        report("telegram", False, "pending: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
    if settings.discord_webhook_url:
        r = httpx.post(
            settings.discord_webhook_url.get_secret_value(), json={"content": text}, timeout=30
        )
        report("discord", r.is_success, f"HTTP {r.status_code}")
    else:
        report("discord", False, "pending: DISCORD_WEBHOOK_URL not set")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="anthropic,openrouter,gemini,mcp,notify")
    parser.add_argument("--gemini-models", default="gemini-3.8-flash,gemini-3.5-flash-lite")
    args = parser.parse_args()
    steps = args.only.split(",")
    if "anthropic" in steps:
        probe_anthropic()
    if "openrouter" in steps:
        probe_openrouter()
    if "gemini" in steps:
        probe_gemini(args.gemini_models.split(","))
    if "mcp" in steps:
        probe_mcp()
    if "notify" in steps:
        probe_notify()
    print("\n".join(["", "Spend:", *guard.lines]))
    print(
        f"Total charged ${guard.spent_usd:.4f} (cap ${CAP_USD:.2f}); "
        f"Gemini paid-equivalent ${guard.paid_equivalent_usd:.4f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
