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


# --- The multi-agent desk (Stage 5.3, D47) ---------------------------------------------------

DeskNode = Literal[
    "technical", "context", "bull_open", "bear_open", "bull_rebut", "bear_rebut", "head",
    "validator",
]  # fmt: skip
DESK_NODES: tuple[str, ...] = DeskNode.__args__  # type: ignore[attr-defined]


class DeskRequest(BaseModel):
    coin: str = Field(pattern=r"^[A-Za-z0-9]{1,16}$")
    as_of: dt.date | None = Field(default=None, description="Run the desk on data up to this date")
    provider: Provider | None = Field(
        default=None, description="Required with an X-LLM-Key header; omitted for the server key"
    )
    model: str | None = Field(default=None, pattern=MODEL_ID)


class Finding(BaseModel):
    id: str = Field(description="T1, T2, ... (technical) or C1, C2, ... (context)")
    claim: str
    value: str | None = None
    tool: str | None = None


class DeskReport(BaseModel):
    analyst: Literal["technical", "context"]
    status: Literal["done", "unavailable"]
    summary: str
    findings: list[Finding]
    note: str | None = Field(default=None, description="Why the report is unavailable")


class DebatePoint(BaseModel):
    text: str
    cites: list[str]
    unknown_cites: list[str] = Field(
        default_factory=list, description="Cited ids that no report contains (flagged, not hidden)"
    )


class DeskCase(BaseModel):
    side: Literal["bull", "bear"]
    phase: Literal["opening", "rebuttal"]
    points: list[DebatePoint]


class DeskSignal(BaseModel):
    """Decision 8: one coin, one week. Levels are required for lean_long."""

    coin: str
    stance: Literal["lean_long", "flat"]
    confidence: float
    entry_low: float | None
    entry_high: float | None
    invalidation: float | None
    target: float | None
    rationale: str
    cites: list[str]


class Validation(BaseModel):
    ok: bool
    errors: list[str]
    attempts: int = Field(description="Head attempts: 1, or 2 after one retry")


class NodeUsage(BaseModel):
    node: DeskNode
    tokens_in: int = 0
    tokens_out: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    cost_usd: float | None = Field(default=None, description="Server-key spend; null for keys")


class DeskRunEvent(BaseModel):
    """First event: the conversation the run is saved in, and what it runs on."""

    conversation_id: int
    title: str
    coin: str
    as_of: dt.date | None
    model: str
    server_key: bool
    reference_close: float | None = Field(
        description="The last daily close; levels are checked on it"
    )
    reference_date: dt.date | None


class NodeStartEvent(BaseModel):
    node: DeskNode


class DeskToolStartEvent(ToolStartEvent):
    node: DeskNode


class DeskToolEndEvent(ToolEndEvent):
    node: DeskNode


class NodeEndEvent(BaseModel):
    node: DeskNode
    status: Literal["done", "unavailable", "failed"]
    report: DeskReport | None = None
    case: DeskCase | None = None
    signal: DeskSignal | None = None
    validation: Validation | None = None
    error: str | None = None
    usage: NodeUsage


class SignalEvent(BaseModel):
    """The desk's final answer: the head's last signal and the validator's verdict."""

    signal: DeskSignal | None
    validation: Validation


class DeskDoneEvent(BaseModel):
    message_id: int
    snapshot_id: int = Field(description="The desk_run snapshot with the full state")
    status: Literal["valid", "invalid"]
    model: str
    tokens_in: int
    tokens_out: int
    model_calls: int
    tool_calls: int
    cost_usd: float | None
    usage: list[NodeUsage]


class DeskErrorEvent(ErrorEvent):
    snapshot_id: int | None = Field(description="The partial desk_run snapshot, when one was saved")


DESK_EVENTS: dict[str, type[BaseModel]] = {
    "desk": DeskRunEvent,
    "node_start": NodeStartEvent,
    "tool_start": DeskToolStartEvent,
    "tool_end": DeskToolEndEvent,
    "node_end": NodeEndEvent,
    "signal": SignalEvent,
    "done": DeskDoneEvent,
    "error": DeskErrorEvent,
}


class NodeEstimate(BaseModel):
    node: DeskNode
    tokens_in: int
    tokens_out: int


class DeskEstimate(BaseModel):
    provider: str
    model: str
    model_calls: int = Field(description="Typical model calls in one run (without a retry)")
    tokens_in: int
    tokens_out: int
    cost_usd: float | None = Field(description="null when the model has no price in models.yaml")
    nodes: list[NodeEstimate]


class DeskRunState(BaseModel):
    """The `desk_run` snapshot's result: everything one run produced."""

    coin: str
    as_of: dt.date | None
    model: str
    status: Literal["running", "valid", "invalid", "error"]
    error: str | None = None
    reference_close: float | None
    reference_date: dt.date | None
    reports: dict[str, DeskReport]
    debate: dict[str, DeskCase]
    signal: DeskSignal | None
    validation: Validation | None
    usage: list[NodeUsage]
