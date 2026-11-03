"""LangSmith tracing for agent runs (Section 3.6, Section 9, D45).

- Only server-key runs (Rob's) are traced, and only when `LANGSMITH_TRACING` is on and a
  LangSmith key is set. Friends' runs (their own keys) are never traced: that keeps their
  questions private and the free plan's 5,000 traces a month for Rob.
- Every run is wrapped in an explicit `tracing_context(enabled=...)`, so an environment
  variable can't switch tracing on for a run that shouldn't be traced.
- `ScrubbingClient` removes secrets from everything it is asked to post: any string containing
  a known secret value (the server's LLM keys, plus the request's key if there is one) becomes
  `[redacted]`, and fields with key-like names (`api_key`, `authorization`, `headers`, ...) are
  dropped. LangChain already serializes `SecretStr` fields as secret references; this is the
  second layer, tested with a canary key.
"""

import contextlib
from collections.abc import Iterable, Iterator
from functools import lru_cache
from typing import Any

from langsmith import Client
from langsmith.run_helpers import tracing_context
from pydantic import SecretStr

from desk.api.middleware import REDACTED
from desk.config import get_settings

SENSITIVE_NAMES = {
    "api_key",
    "apikey",
    "anthropic_api_key",
    "openai_api_key",
    "x-api-key",
    "x_api_key",
    "x-llm-key",
    "authorization",
    "headers",
    "default_headers",
    "http_client",
    "http_async_client",
}


def scrub(value: Any, secrets: Iterable[str]) -> Any:
    """A copy of `value` with secret strings redacted and key-like fields dropped."""
    found = [s for s in secrets if s]
    return _scrub(value, found)


def _scrub(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        for s in secrets:
            if s in value:
                value = value.replace(s, REDACTED)
        return value
    if isinstance(value, SecretStr):
        return REDACTED
    if isinstance(value, dict):
        return {k: _scrub(v, secrets) for k, v in value.items()
                if not (isinstance(k, str) and k.lower() in SENSITIVE_NAMES)}  # fmt: skip
    if isinstance(value, list | tuple):
        return type(value)(_scrub(v, secrets) for v in value)
    return value


def server_secrets() -> list[str]:
    s = get_settings()
    keys = [s.anthropic_api_key, s.openrouter_api_key, s.google_api_key, s.langsmith_api_key]
    return [k.get_secret_value() for k in keys if isinstance(k, SecretStr) and k.get_secret_value()]


class ScrubbingClient(Client):
    """A LangSmith client that scrubs every run it creates or updates (all fields, not only
    inputs and outputs). `extra_secrets` adds values to redact beyond the server's keys."""

    def __init__(self, *args: Any, extra_secrets: Iterable[str] = (), **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._extra_secrets = [s for s in extra_secrets if s]

    def _secrets(self) -> list[str]:
        return server_secrets() + self._extra_secrets

    def create_run(self, name: str, inputs: dict[str, Any], run_type: Any, **kwargs: Any) -> Any:
        secrets = self._secrets()
        own = {k: kwargs.pop(k) for k in ("api_key", "api_url") if k in kwargs}
        return super().create_run(_scrub(name, secrets), _scrub(inputs, secrets), run_type,
                                  **own, **_scrub(kwargs, secrets))  # fmt: skip

    def update_run(self, run_id: Any, **kwargs: Any) -> Any:
        secrets = self._secrets()
        own = {k: kwargs.pop(k) for k in ("api_key", "api_url") if k in kwargs}
        return super().update_run(run_id, **own, **_scrub(kwargs, secrets))


def tracing_enabled() -> bool:
    s = get_settings()
    key = s.langsmith_api_key
    return bool(s.langsmith_tracing and key is not None and key.get_secret_value())


@lru_cache
def trace_client() -> ScrubbingClient:
    s = get_settings()
    assert s.langsmith_api_key is not None
    return ScrubbingClient(api_key=s.langsmith_api_key.get_secret_value(),
                           workspace_id=s.langsmith_workspace_id or None)  # fmt: skip


@contextlib.contextmanager
def agent_tracing(*, server_key: bool, metadata: dict[str, Any] | None = None) -> Iterator[None]:
    """Trace this block to LangSmith only for a server-key run; otherwise force tracing off."""
    if server_key and tracing_enabled():
        with tracing_context(enabled=True, client=trace_client(),
                             project_name=get_settings().langsmith_project,
                             metadata=metadata or {}, tags=["agent", "chat"]):  # fmt: skip
            yield
    else:
        with tracing_context(enabled=False):
            yield
