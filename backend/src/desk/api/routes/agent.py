"""`/api/agent` routes: the model list and the key test behind the Settings wizard (Stage 3.4),
the chat agent with its conversations and data snapshots (Stage 5.1, D45), and the
multi-agent desk behind "Ask the desk" (Stage 5.3, D47).

The user's key arrives only as the `X-LLM-Key` header, which `LlmKeyRedaction` removes before
any route runs and keeps as a `SecretStr` in the request state (D37). It is sent to the chosen
provider in one request header and is never stored, logged or returned.
"""

import datetime as dt
from collections.abc import AsyncIterable, Iterator
from typing import Annotated

import anyio
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field, SecretStr

from desk.agents import chat, desk_graph
from desk.agents.keycheck import Provider, check_key
from desk.agents.schemas import (
    DESK_EVENTS,
    EVENTS,
    ChatRequest,
    ConversationDetail,
    ConversationSummary,
    DeskEstimate,
    DeskRequest,
    Snapshot,
)
from desk.api import deps
from desk.api.deps import SessionDep, UserDep, require_role
from desk.api.middleware import count_error
from desk.api.schemas import Envelope, Source
from desk.config import load_models_config
from desk.models import AgentSnapshot

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


# --- Chat (Stage 5.1) -------------------------------------------------------------------------


async def _count(where: str, payload: object) -> None:
    """Count a failed run on the Health page by its error code only (Stage 8.1)."""
    await anyio.to_thread.run_sync(count_error, where, str(getattr(payload, "code", "error")))


def tools_factory() -> chat.ToolsFactory:
    """desk-mcp's tools for one answer (tests swap in their own)."""
    return chat.desk_tools


def prepared_chat(body: ChatRequest, request: Request, user: UserDep,
                  session: SessionDep) -> chat.Prepared:  # fmt: skip
    """Validate and save the question before the stream starts, so refusals are plain HTTP
    errors: 400 (no key, bad model), 402 (server budget used up), 404, 429 (hourly limit)."""
    key: SecretStr | None = getattr(request.state, "llm_key", None)
    try:
        return chat.prepare(session, deps._sessions(), user_id=user.id, is_admin=user.is_admin,
                            message=body.message, conversation_id=body.conversation_id,
                            provider=body.provider, model=body.model, key=key)  # fmt: skip
    except chat.ChatError as e:
        headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
        raise HTTPException(e.status, e.message, headers=headers) from None


SSE_DOC = (
    "Server-Sent Events, in order: "
    + ", ".join(EVENTS)
    + (
        ". `token` events carry the answer text; each tool call sends `tool_start` then `tool_end` "
        "(with its snapshot id). The stream ends with `done`, or with `error` (timeout, provider, "
        "budget, internal), after which the partial answer is saved."
    )
)


@router.post("/chat", response_class=EventSourceResponse, operation_id="chat",
             description=SSE_DOC)  # fmt: skip
async def chat_stream(
    prepared: Annotated[chat.Prepared, Depends(prepared_chat)],
    factory: Annotated[chat.ToolsFactory, Depends(tools_factory)],
) -> AsyncIterable[ServerSentEvent]:
    """Ask the agent. Send your own key in `X-LLM-Key` with `provider` (and optionally
    `model`); an admin without a key uses the capped server key."""
    async for name, payload in chat.run(prepared, factory):
        if name == "error":
            await _count("agent.chat", payload)
        yield ServerSentEvent(event=name, data=payload.model_dump(mode="json"))


@router.get("/conversations", response_model=list[ConversationSummary],
            operation_id="listConversations")  # fmt: skip
def list_conversations(user: UserDep, session: SessionDep) -> list[ConversationSummary]:
    """Your conversations, most recently active first."""
    return [ConversationSummary(**c) for c in chat.list_conversations(session, user.id)]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail,
            operation_id="getConversation")  # fmt: skip
def get_conversation(
    conversation_id: int, user: UserDep, session: SessionDep
) -> ConversationDetail:
    """One of your conversations with its messages and, per answer, its tool snapshots."""
    detail = chat.conversation_detail(session, user.id, conversation_id)
    if detail is None:
        raise HTTPException(404, "conversation not found")
    return ConversationDetail(**detail)


@router.delete("/conversations/{conversation_id}", status_code=204,
               operation_id="deleteConversation")  # fmt: skip
def delete_conversation(conversation_id: int, user: UserDep, session: SessionDep) -> Response:
    """Delete one of your conversations with its messages and snapshots."""
    if not chat.delete_conversation(session, user.id, conversation_id):
        raise HTTPException(404, "conversation not found")
    return Response(status_code=204)


@router.get("/snapshots/{snapshot_id}", response_model=Snapshot, operation_id="getSnapshot")
def get_snapshot(snapshot_id: int, user: UserDep, session: SessionDep) -> Snapshot:
    """The exact arguments and result of one agent tool call (yours; admins can open any)."""
    row = session.get(AgentSnapshot, snapshot_id)
    if row is None or (row.user_id != user.id and not user.is_admin):
        raise HTTPException(404, "snapshot not found")
    return Snapshot(id=row.id, conversation_id=row.conversation_id, tool=row.tool,
                    args=row.args or {}, result=row.result, as_of=row.as_of,
                    created_at=row.created_at)  # fmt: skip


# --- The multi-agent desk (Stage 5.3) ---------------------------------------------------------


def desk_tools_factory() -> desk_graph.DeskToolsFactory:
    """desk-mcp's tools for one analyst, limited to its groups (tests swap in their own)."""
    return chat.desk_tools


def prepared_desk(body: DeskRequest, request: Request, user: UserDep,
                  session: SessionDep) -> desk_graph.DeskPrepared:  # fmt: skip
    """Validate the run and save its question before the stream starts: 400 (no key, bad
    model), 402 (server budget used up), 404 (unknown coin), 422, 429 (hourly limits)."""
    key: SecretStr | None = getattr(request.state, "llm_key", None)
    try:
        return desk_graph.prepare(session, deps._sessions(), user_id=user.id,
                                  is_admin=user.is_admin, coin=body.coin, as_of=body.as_of,
                                  provider=body.provider, model=body.model, key=key)  # fmt: skip
    except chat.ChatError as e:
        headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
        raise HTTPException(e.status, e.message, headers=headers) from None


DESK_DOC = (
    "Server-Sent Events: "
    + ", ".join(DESK_EVENTS)
    + (
        ". `desk` comes first. Each node (technical, context, bull_open, bear_open, bull_rebut, "
        "bear_rebut, head, validator) sends `node_start` then `node_end`; the analysts' tool "
        "calls send `tool_start` and `tool_end` with their node and snapshot id. The head and "
        "validator can run twice (one retry). `signal` carries the final signal and verdict. "
        "The stream ends with `done` (with the `desk_run` snapshot id) or `error`; both save "
        "the full state."
    )
)


@router.post("/desk", response_class=EventSourceResponse, operation_id="askDesk",
             description=DESK_DOC)  # fmt: skip
async def desk_stream(
    prepared: Annotated[desk_graph.DeskPrepared, Depends(prepared_desk)],
    factory: Annotated[desk_graph.DeskToolsFactory, Depends(desk_tools_factory)],
) -> AsyncIterable[ServerSentEvent]:
    """Ask the desk about one coin: two analysts, a bull and bear debate, and the head's
    Decision 8 signal. Same keys as chat; an admin without a key uses the capped server key."""
    async for name, payload in desk_graph.run(prepared, factory):
        if name == "error":
            await _count("agent.desk", payload)
        yield ServerSentEvent(event=name, data=payload.model_dump(mode="json"))


@router.get("/desk/estimate", response_model=Envelope[DeskEstimate],
            operation_id="deskEstimate")  # fmt: skip
def desk_estimate(
    user: UserDep,
    provider: Provider | None = None,
    model: Annotated[str | None, Query(pattern=MODEL_ID)] = None,
) -> Envelope[DeskEstimate]:
    """Typical tokens for one desk run and, when the model has a known price, its USD. With no
    provider, the server key's model (admins)."""
    cfg = load_models_config()
    if provider is None:
        name = (cfg.get("server") or {}).get("agent")
        if not user.is_admin or not name:
            raise HTTPException(400, "choose the provider your key is for")
        estimate = desk_graph.estimate("server", name)
    else:
        name = model or (cfg.get("byo_defaults") or {}).get(provider)
        if not name:
            raise HTTPException(400, "choose a model")
        estimate = desk_graph.estimate(provider, name)
    src = Source(name="config", detail="settings.yaml desk.estimate_tokens; models.yaml prices")
    return Envelope(as_of=dt.datetime.now(dt.UTC).date(), sources=[src],
                    data=DeskEstimate(**estimate))  # fmt: skip
