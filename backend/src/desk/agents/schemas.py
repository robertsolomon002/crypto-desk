"""Agent request and stream-event schemas (Stage 5.1). The SSE event payloads are part of the
API contract: the Agent tab (Stage 5.2) is built against them."""

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from desk.agents.keycheck import Provider

MODEL_ID = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    provider: Provider | None = Field(
        default=None, description="Required with an X-LLM-Key header; omitted for the server key"
    )
    model: str | None = Field(default=None, pattern=MODEL_ID)


# --- SSE event payloads (event name → model) -------------------------------------------------


class ConversationEvent(BaseModel):
    """First event: the conversation the answer belongs to (new or continued)."""

    id: int
    title: str | None
    model: str
    server_key: bool


class TokenEvent(BaseModel):
    text: str


class ToolStartEvent(BaseModel):
    call_id: str
    name: str
    args: dict[str, Any]


class ToolEndEvent(BaseModel):
    call_id: str
    name: str
    snapshot_id: int
    ok: bool
    preview: str = Field(description="The first 300 characters of the tool's JSON result")


class DoneEvent(BaseModel):
    message_id: int
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float | None = Field(description="Server-key spend for this answer; null for keys")
    tool_calls: int
    limited: bool = Field(description="True when the tool-call limit cut the research short")
    truncated: bool = Field(description="True when the model hit its output-token limit")


class ErrorEvent(BaseModel):
    code: Literal["timeout", "provider", "budget", "internal"]
    message: str


EVENTS: dict[str, type[BaseModel]] = {
    "conversation": ConversationEvent,
    "token": TokenEvent,
    "tool_start": ToolStartEvent,
    "tool_end": ToolEndEvent,
    "done": DoneEvent,
    "error": ErrorEvent,
}


# --- Conversation and snapshot responses -----------------------------------------------------


class ConversationSummary(BaseModel):
    id: int
    title: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    messages: int


class SnapshotRef(BaseModel):
    id: int
    tool: str
    created_at: dt.datetime


class ChatMessage(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    model: str | None
    created_at: dt.datetime
    snapshots: list[SnapshotRef] = Field(
        default_factory=list, description="Tool calls made for this answer (assistant only)"
    )


class ConversationDetail(BaseModel):
    id: int
    title: str | None
    created_at: dt.datetime
    messages: list[ChatMessage]


class Snapshot(BaseModel):
    id: int
    conversation_id: int | None
    tool: str
    args: dict[str, Any]
    result: Any
    as_of: dt.datetime | None
    created_at: dt.datetime
