"""`/api/agent` routes. Stage 3.4: the model list and the key test behind the Settings wizard.
The chat routes come in Stage 5.1.

The user's key arrives only as the `X-LLM-Key` header, which `LlmKeyRedaction` removes before
any route runs and keeps as a `SecretStr` in the request state (D37). It is sent to the chosen
provider in one request header and is never stored, logged or returned.
"""

import datetime as dt
from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr

from desk.agents.keycheck import Provider, check_key
from desk.api.deps import require_role
from desk.api.schemas import Envelope, Source
from desk.config import load_models_config

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_role("member"))])

PROVIDER_LABELS: dict[Provider, str] = {
    "openrouter": "OpenRouter",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
}
MODEL_ID = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$"


class ProviderModels(BaseModel):
    id: Provider
    label: str
    recommended: bool
    default: str | None
    choices: list[str]


class KeyTest(BaseModel):
    provider: Provider
    model: str | None = Field(default=None, pattern=MODEL_ID)


class KeyTestResult(BaseModel):
    ok: bool
    provider: Provider
    model: str | None
    message: str


def provider_client() -> Iterator[httpx.Client]:
    # No redirects: the key must only ever go to the provider host it was meant for.
    with httpx.Client(follow_redirects=False) as client:
        yield client


@router.get("/models", response_model=Envelope[list[ProviderModels]], operation_id="listModels")
def list_models() -> Envelope[list[ProviderModels]]:
    """Providers a friend can bring a key for, with a default and suggested models
    (`config/models.yaml`). OpenRouter is the recommended path (Decision 2)."""
    cfg = load_models_config()
    defaults, choices = cfg.get("byo_defaults", {}), cfg.get("byo_choices", {})
    providers = [
        ProviderModels(
            id=p,
            label=label,
            recommended=p == "openrouter",
            default=defaults.get(p),
            choices=list(choices.get(p) or []),
        )
        for p, label in PROVIDER_LABELS.items()
    ]
    src = Source(name="config", detail="models.yaml")
    return Envelope(as_of=dt.datetime.now(dt.UTC).date(), sources=[src], data=providers)


@router.post("/test-key", response_model=KeyTestResult, operation_id="testKey")
def test_key(
    body: KeyTest,
    request: Request,
    client: Annotated[httpx.Client, Depends(provider_client)],
) -> KeyTestResult:
    """One minimal call with the key from `X-LLM-Key` (1 output token; OpenAI: list models)."""
    key: SecretStr | None = getattr(request.state, "llm_key", None)
    if key is None or not key.get_secret_value().strip():
        raise HTTPException(400, "send the key in the X-LLM-Key header")
    model = body.model or load_models_config().get("byo_defaults", {}).get(body.provider)
    if body.provider != "openai" and not model:
        raise HTTPException(400, "choose a model")
    result = check_key(client, body.provider, key.get_secret_value().strip(), model)
    return KeyTestResult(ok=result.ok, provider=result.provider, model=result.model,
                         message=result.message)  # fmt: skip
