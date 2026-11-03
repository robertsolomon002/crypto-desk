"""Gemini video extract to strict JSON (Section 3.4 step 2, D25, D48).

For each model in `models.yaml` `server.video_summary` (Flash-Lite, then 3.8 Flash):
1. send the public YouTube URL with `prompts/mco_extract_v1.md` and the response schema
   (low media resolution; the SDK retries 408/429/5xx with backoff; long client timeout);
2. validate with Pydantic; on failure, one text-only repair call (`mco_repair_v1.md`);
3. on an API error or a second invalid answer, move to the next model.
If every model fails, extract from the title and description only (`mco_fallback_v1.md`),
marked low detail: every coin `low` confidence, no pivot labels.

Afterwards, deterministic checks (D25): a bias that contradicts its own targets or invalidation
relative to the last close sets that coin's confidence to `low` and adds a note to `checks`.

Every Gemini call is reported to `spend` (one `llm_spend` row, source `mco`; $0 on the free
tier). Logs carry ids, models, token counts and error codes only, never model or video text.
"""

import datetime as dt
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import ValidationError

from desk.config import get_settings, load_models_config
from desk.mco.schemas import Extract, response_schema

log = logging.getLogger(__name__)

PROMPT_VERSION = "mco_extract_v1"
RETRY_CODES = [408, 429, 500, 502, 503, 504]


@dataclass(frozen=True)
class Reply:
    text: str
    tokens_in: int
    tokens_out: int


class Gemini(Protocol):
    def video(self, model: str, url: str, prompt: str) -> Reply: ...
    def text(self, model: str, prompt: str) -> Reply: ...


class GeminiError(Exception):
    """A failed Gemini call; `code` is short and safe to log (e.g. `503`, `timeout`)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SummarizeFailed(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class Summary:
    extract: Extract
    model: str
    low_detail: bool
    calls: int = 0
    errors: list[str] = field(default_factory=list)  # codes from failed attempts


# --- The real client --------------------------------------------------------------------------


class GenaiClient:
    """google-genai 2.33: `models.generate_content` with `file_data` for the YouTube URL and
    `response_json_schema` (Stage 0.3 probe). `HttpOptions.timeout` is in milliseconds, and
    the SDK only retries when `retry_options` is set (installed source, D48)."""

    def __init__(self, api_key: str, timeout_s: int = 300, attempts: int = 3) -> None:
        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=timeout_s * 1000,
                retry_options=types.HttpRetryOptions(
                    attempts=attempts,
                    initial_delay=5.0,
                    max_delay=60.0,
                    http_status_codes=RETRY_CODES,
                ),
            ),
        )

    def _call(self, model: str, parts: list, video: bool) -> Reply:
        from google.genai import errors

        t = self._types
        config = t.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=response_schema(),
            media_resolution=t.MediaResolution.MEDIA_RESOLUTION_LOW if video else None,
        )
        try:
            resp = self._client.models.generate_content(
                model=model, contents=t.Content(role="user", parts=parts), config=config
            )
        except errors.APIError as exc:
            raise GeminiError(str(exc.code)) from None
        except Exception as exc:  # timeouts and transport errors from httpx
            name = type(exc).__name__
            raise GeminiError("timeout" if "Timeout" in name else name) from None
        u = resp.usage_metadata
        tin = (u.prompt_token_count or 0) if u else 0
        tout = ((u.candidates_token_count or 0) + (u.thoughts_token_count or 0)) if u else 0
        if not resp.text:
            raise GeminiError("empty")
        return Reply(resp.text, tin, tout)

    def video(self, model: str, url: str, prompt: str) -> Reply:
        t = self._types
        return self._call(
            model, [t.Part(file_data=t.FileData(file_uri=url)), t.Part(text=prompt)], video=True
        )

    def text(self, model: str, prompt: str) -> Reply:
        return self._call(model, [self._types.Part(text=prompt)], video=False)


# --- Prompts ----------------------------------------------------------------------------------


def load_prompt(name: str) -> str:
    return (get_settings().prompts_dir / f"{name}.md").read_text(encoding="utf-8")


def _fill(template: str, **values: str) -> str:
    for k, v in values.items():  # str.replace, not format: descriptions may contain braces
        template = template.replace("{" + k + "}", v)
    return template


def _errors(exc: ValidationError) -> str:
    return "\n".join(
        f"- {'.'.join(map(str, e['loc'])) or '(root)'}: {e['msg']}" for e in exc.errors()[:20]
    )


# --- Pipeline ---------------------------------------------------------------------------------


def model_chain() -> list[str]:
    return list((load_models_config().get("server") or {}).get("video_summary") or [])


def summarize(
    client: Gemini,
    url: str,
    title: str,
    description: str,
    published: dt.date,
    spend: Callable[[str, int, int], None],
    aliases: dict[str, str] | None = None,
    closes: dict[str, float] | None = None,
    models: list[str] | None = None,
) -> Summary:
    """Extract one video; raises `SummarizeFailed` when even the fallback fails."""
    models = models or model_chain()
    date = published.isoformat()
    errors: list[str] = []
    calls = 0

    def attempt(model: str, call: Callable[[], Reply]) -> Extract:
        nonlocal calls
        reply = call()
        calls += 1
        spend(model, reply.tokens_in, reply.tokens_out)
        try:
            return Extract.model_validate_json(reply.text)
        except ValidationError as exc:
            errors.append(f"{model}:schema")
            repair = _fill(load_prompt("mco_repair_v1"), errors=_errors(exc), json=reply.text)
            fixed = client.text(model, repair)
            calls += 1
            spend(model, fixed.tokens_in, fixed.tokens_out)
            return Extract.model_validate_json(fixed.text)

    prompt = _fill(load_prompt("mco_extract_v1"), published_date=date)
    for model in models:
        try:
            extract = attempt(model, lambda m=model: client.video(m, url, prompt))
        except GeminiError as exc:
            errors.append(f"{model}:{exc.code}")
            log.warning("mco summarize: %s failed (%s)", model, exc.code)
            continue
        except ValidationError:
            errors.append(f"{model}:schema")
            log.warning("mco summarize: %s answer invalid after repair", model)
            continue
        out = Summary(finish(extract, aliases, closes), model, False, calls, errors)
        log.info("mco summarize: %s ok (%d calls)", model, calls)
        return out

    fallback = _fill(
        load_prompt("mco_fallback_v1"),
        published_date=date,
        title=title,
        description=description[:5000],
    )
    for model in models:
        try:
            extract = attempt(model, lambda m=model: client.text(m, fallback))
        except (GeminiError, ValidationError) as exc:
            errors.append(f"{model}:fallback:{getattr(exc, 'code', 'schema')}")
            continue
        for c in extract.coins:
            c.extraction_confidence = "low"
            c.pivot_labels = []
        log.info("mco summarize: low-detail fallback on %s", model)
        return Summary(finish(extract, aliases, closes), model, True, calls, errors)
    raise SummarizeFailed(errors[-1] if errors else "no_models")


def finish(
    extract: Extract, aliases: dict[str, str] | None, closes: dict[str, float] | None
) -> Extract:
    """Coins to our symbols (aliases), merged if named twice, then the D25 checks."""
    aliases = {k.upper(): v for k, v in (aliases or {}).items()}
    seen: dict[str, int] = {}
    coins = []
    for c in extract.coins:
        c.coin = aliases.get(c.coin, c.coin)
        if c.coin in seen:  # keep the first view; a duplicate is usually a restatement
            continue
        seen[c.coin] = len(coins)
        coins.append(c)
    extract.coins = coins
    extract.checks = [*extract.checks, *consistency(extract, closes or {})]
    return extract


def consistency(extract: Extract, closes: dict[str, float]) -> list[str]:
    """D25: bias vs where targets and invalidation sit relative to the last close."""
    notes = []
    for c in extract.coins:
        close = closes.get(c.coin)
        if not close:
            continue
        bad = None
        if c.bias == "bullish":
            if c.targets and all(t < close for t in c.targets):
                bad = "bias bullish but every target is below the last close"
            elif c.invalidation is not None and c.invalidation > close:
                bad = "bias bullish but the invalidation is above the last close"
        elif c.bias == "bearish":
            if c.targets and all(t > close for t in c.targets):
                bad = "bias bearish but every target is above the last close"
            elif c.invalidation is not None and c.invalidation < close:
                bad = "bias bearish but the invalidation is below the last close"
        if bad:
            c.extraction_confidence = "low"
            notes.append(f"{c.coin}: {bad} ({close:g})")
    return notes


def to_payload(extract: Extract) -> dict:
    return json.loads(extract.model_dump_json())
