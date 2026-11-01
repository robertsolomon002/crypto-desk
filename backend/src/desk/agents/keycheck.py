"""Test a user's own LLM key with the smallest possible call (Stage 3.4, Settings wizard).

Checked live on 2026-11-01 (D42):
- OpenRouter: `POST /api/v1/chat/completions` with `max_tokens: 1` works (about $0.000002 on
  `anthropic/claude-haiku-5.5`); a bad key is a 401.
- Anthropic: `POST /v1/messages` with `max_tokens: 1` and `anthropic-version: 2023-06-01`
  works (11 input tokens, 1 output token); a bad key is a 401 `authentication_error`.
- OpenAI: no default model is chosen until Stage 5.1, so the check is `GET /v1/models`, which
  authenticates the key at no cost. Its 401 message echoes part of the key.

So the provider's response text is never passed on: the result carries only our own message,
picked from the HTTP status. The key goes into one request header and nowhere else.
"""

from dataclasses import dataclass
from typing import Literal

import httpx

Provider = Literal["openrouter", "anthropic", "openai"]

TIMEOUT = httpx.Timeout(20.0, connect=5.0)
PROMPT = [{"role": "user", "content": "Hi"}]

MESSAGES = {
    401: "The key was rejected. Check that it was copied in full.",
    402: "The key works, but its account has no credit left.",
    403: "The key isn't allowed to use this model.",
    404: "This model id wasn't found for your key.",
    429: "Rate limited by the provider. Try again in a minute.",
}


@dataclass(frozen=True)
class KeyCheck:
    ok: bool
    provider: Provider
    model: str | None
    message: str


def _request(provider: Provider, key: str, model: str | None) -> tuple[str, str, dict, dict]:
    if provider == "openrouter":
        body = {"model": model, "max_tokens": 1, "messages": PROMPT}
        auth = {"Authorization": f"Bearer {key}"}
        return "POST", "https://openrouter.ai/api/v1/chat/completions", auth, body
    if provider == "anthropic":
        body = {"model": model, "max_tokens": 1, "messages": PROMPT}
        auth = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        return "POST", "https://api.anthropic.com/v1/messages", auth, body
    return "GET", "https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"}, {}


def check_key(client: httpx.Client, provider: Provider, key: str, model: str | None) -> KeyCheck:
    """One minimal authenticated call. Never raises for provider or network errors."""
    used = None if provider == "openai" else model
    method, url, headers, body = _request(provider, key, used)
    try:
        r = client.request(method, url, headers=headers, json=body or None, timeout=TIMEOUT)
    except httpx.HTTPError:
        return KeyCheck(False, provider, used, "Couldn't reach the provider. Try again.")
    if r.status_code == 200:
        what = "lists models" if provider == "openai" else f"answered with {used}"
        return KeyCheck(True, provider, used, f"The key works: the provider {what}.")
    if r.status_code == 400 and provider != "openai":
        return KeyCheck(False, provider, used, "The provider refused the request for this model.")
    message = MESSAGES.get(r.status_code, f"The provider returned an error ({r.status_code}).")
    return KeyCheck(False, provider, used, message)
