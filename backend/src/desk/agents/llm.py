"""Per-request chat model factory (Section 3.2, D45).

- A user's key (from the `X-LLM-Key` header only) picks its provider's integration:
  OpenRouter through `ChatOpenAI` with OpenRouter's base URL (Chat Completions), Anthropic
  through `ChatAnthropic`, OpenAI through `ChatOpenAI`.
- An admin with no key gets Rob's server key (`ANTHROPIC_API_KEY`) on `server.agent`, capped by
  `agents/cost.py`. Near the cap (`degraded`) it moves to `server.chat_degraded` at low effort
  with fewer output tokens (Decision 9, step 1).

Keys are passed as `SecretStr` and never fall back to environment variables: an empty key is
refused here, so a friend's request can never run on a key from the server's environment.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from desk.agents.keycheck import Provider
from desk.config import get_settings, load_app_settings, load_models_config

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")
TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 1  # the 90-second answer timeout leaves no room for more


class ModelError(ValueError):
    """The request can't be turned into a model (no key, bad model id, server key missing)."""


@dataclass(frozen=True)
class ModelChoice:
    provider: Provider | Literal["server"]
    model: str
    server_key: bool
    degraded: bool = False


def choose(
    provider: Provider | None,
    model: str | None,
    key: SecretStr | None,
    *,
    is_admin: bool,
    degraded: bool = False,
) -> ModelChoice:
    """Which provider and model a request runs on. Raises `ModelError` with a user-facing
    message."""
    has_key = key is not None and bool(key.get_secret_value().strip())
    if not has_key:
        if not is_admin:
            raise ModelError("Add your own LLM key in Settings to use the agent.")
        cfg = load_models_config().get("server") or {}
        name = cfg.get("chat_degraded" if degraded else "agent")
        if not name:
            raise ModelError("The server model isn't configured.")
        return ModelChoice("server", name, server_key=True, degraded=degraded)
    if provider is None:
        raise ModelError("Choose the provider your key is for.")
    name = model or (load_models_config().get("byo_defaults") or {}).get(provider)
    if not name:
        raise ModelError("Choose a model.")
    if not MODEL_ID.match(name):
        raise ModelError("That model id isn't valid.")
    return ModelChoice(provider, name, server_key=False)


def _byo_params(provider: str, model: str) -> dict[str, Any]:
    params = (load_models_config().get("byo_params") or {}).get(provider) or {}
    return dict(params.get(model) or {})


def make_chat_model(choice: ModelChoice, key: SecretStr | None) -> BaseChatModel:
    """A streaming chat model for one request. `key` is ignored for the server key."""
    agent = load_app_settings().get("agent") or {}
    max_tokens = int(agent.get("max_output_tokens", 4000))
    if choice.server_key:
        server_key = get_settings().anthropic_api_key
        if server_key is None or not server_key.get_secret_value():
            raise ModelError("The server key isn't configured.")
        extra: dict[str, Any] = {}
        if choice.degraded:
            max_tokens = int(agent.get("degraded_max_output_tokens", 1500))
            extra["effort"] = "low"
        return ChatAnthropic(model=choice.model, api_key=server_key, max_tokens=max_tokens,
                             timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES, **extra)  # fmt: skip
    if key is None or not key.get_secret_value().strip():
        raise ModelError("Add your own LLM key in Settings to use the agent.")
    secret = SecretStr(key.get_secret_value().strip())
    params = _byo_params(choice.provider, choice.model)
    if choice.provider == "anthropic":
        return ChatAnthropic(model=choice.model, api_key=secret, max_tokens=max_tokens,
                             timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES,
                             **params)  # fmt: skip
    if choice.provider == "openrouter":
        return ChatOpenAI(model=choice.model, api_key=secret, base_url=OPENROUTER_BASE_URL,
                          max_tokens=max_tokens, timeout=TIMEOUT_SECONDS,
                          max_retries=MAX_RETRIES, stream_usage=True,
                          use_responses_api=False, **params)  # fmt: skip
    if choice.provider == "openai":
        return ChatOpenAI(model=choice.model, api_key=secret, max_tokens=max_tokens,
                          timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES, stream_usage=True,
                          **params)  # fmt: skip
    raise ModelError(f"Unknown provider {choice.provider!r}.")
