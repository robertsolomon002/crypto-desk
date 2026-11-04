"""The chat agent: a small LangGraph tool-calling loop over `desk-mcp` (Section 3.2, D45).

Graph: `agent` (the model, streaming) ⇄ `tools` (desk-mcp tools through
`langchain-mcp-adapters`), ending when the model answers without asking for a tool.

- **Tools** come from the same FastMCP server Claude desktop uses, connected in-process over
  the MCP SDK's in-memory transport (`build_server(threaded=True)`), so each chat skips a
  subprocess start and the tools run in worker threads on the API's database sessions.
- **Limits:** at most `agent.max_tool_calls` tool calls per answer. When they are used up the
  model gets one last turn with tools switched off (`tool_choice` none) and a note to answer
  from what it has. The whole answer has `agent.timeout_seconds`.
- **Snapshots:** each tool call's arguments and parsed JSON result are written to
  `agent_snapshots` before its `tool_end` event, so "View data" always opens the exact data.
- **Events** (`schemas.EVENTS`): conversation, token, tool_start, tool_end, done, error. Error
  messages are always our own text: provider errors can echo key fragments (D42).
- **Persistence:** the question is saved before the run; the answer (all streamed text) is
  saved at the end, also after a timeout or error, with tokens and, for the server key, cost.
"""

import asyncio
import contextlib
import datetime as dt
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Annotated, Any, TypedDict

import anyio
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from desk.agents import cost, llm, tracing
from desk.agents.keycheck import Provider
from desk.agents.schemas import (
    ConversationEvent,
    DoneEvent,
    ErrorEvent,
    TokenEvent,
    ToolEndEvent,
    ToolStartEvent,
)
from desk.config import get_settings, load_app_settings
from desk.mcp_server import tools as mcp_tools
from desk.mcp_server.server import build_server
from desk.models import AgentSnapshot, Conversation, Message, User

log = logging.getLogger(__name__)

PROMPT_FILE = "agent_v1.md"
PREVIEW_CHARS = 300
TITLE_CHARS = 80
LIMIT_NOTE = (
    "You have used all your tool calls for this answer. Answer now from the data you already "
    "have, and say briefly what you couldn't check."
)
TOOL_BUDGET_USED = "Not run: the tool-call limit for this answer was reached."

Sessions = Callable[[], Session]
Event = tuple[str, Any]  # (SSE event name, payload model)


class ChatError(Exception):
    """A refused chat request, mapped to an HTTP status before streaming starts."""

    def __init__(self, status: int, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.retry_after = retry_after


def agent_settings() -> dict[str, Any]:
    return load_app_settings().get("agent") or {}


# --- Prompt -----------------------------------------------------------------------------------


def system_prompt(today: dt.date, max_tool_calls: int) -> str:
    template = (get_settings().prompts_dir / PROMPT_FILE).read_text(encoding="utf-8")
    return template.replace("{today}", today.isoformat()).replace(
        "{max_tool_calls}", str(max_tool_calls)
    )


# --- Preparing a request (runs before the stream starts, so errors are plain HTTP errors) -----


@dataclass
class Prepared:
    user_id: int
    conversation_id: int
    title: str | None
    choice: llm.ModelChoice
    model: BaseChatModel
    key: SecretStr | None
    history: list[BaseMessage]
    question: str
    sessions: Sessions
    max_tool_calls: int
    timeout: float


def _title(text: str) -> str:
    words = " ".join(text.split())
    return words if len(words) <= TITLE_CHARS else words[: TITLE_CHARS - 1].rstrip() + "…"


def check_rate(session: Session, user_id: int, now: dt.datetime | None = None) -> None:
    """At most `agent.messages_per_user_per_hour` questions per user per rolling hour, counted
    in the database so the limit holds across Cloud Run instances."""
    limit = int(agent_settings().get("messages_per_user_per_hour", 30))
    # Lock the user's row until the caller commits the new question, so concurrent requests by
    # one user are counted in turn. Without it, three questions sent at once all passed a limit
    # with one question left (the Stage 8.1 load check, D53). The desk's own limit runs after
    # this in the same transaction, so it is covered too.
    session.execute(select(User.id).where(User.id == user_id).with_for_update())
    now = now or dt.datetime.now(dt.UTC)
    since = now - dt.timedelta(hours=1)
    recent = select(Message.created_at).where(
        Message.user_id == user_id, Message.role == "user", Message.created_at > since
    )
    times = sorted(session.scalars(recent))
    if len(times) >= limit:
        oldest = times[-limit]
        retry = max(1, int((oldest + dt.timedelta(hours=1) - now).total_seconds()) + 1)
        raise ChatError(429, f"You've asked {limit} questions in the last hour. "
                             "Try again in a few minutes.", retry_after=retry)  # fmt: skip


def load_history(session: Session, conversation_id: int, limit: int) -> list[BaseMessage]:
    rows = session.execute(
        select(Message.role, Message.content)
        .where(Message.conversation_id == conversation_id, Message.role.in_(["user", "assistant"]))
        .order_by(Message.id.desc())
        .limit(limit)
    ).all()
    out: list[BaseMessage] = []
    for role, content in reversed(rows):
        if not content:
            continue
        out.append(HumanMessage(content) if role == "user" else AIMessage(content))
    # Start on a question: some providers refuse a history that opens with an answer.
    while out and not isinstance(out[0], HumanMessage):
        out.pop(0)
    return out


def has_user_key(key: SecretStr | None) -> bool:
    return key is not None and bool(key.get_secret_value().strip())


def resolve_model(
    session: Session,
    *,
    is_admin: bool,
    provider: Provider | None,
    model: str | None,
    key: SecretStr | None,
) -> tuple[llm.ModelChoice, BaseChatModel]:
    """The model a request runs on: the user's key, or (admin only) the capped server key.
    Raises `ChatError` 402 when the server budget is used up and 400 for a bad choice."""
    degraded = False
    if not has_user_key(key) and is_admin:
        try:
            degraded = cost.check_budget(session).degraded
        except cost.BudgetExceeded:
            raise ChatError(
                402,
                "Rob's monthly AI budget is used up. It resets on the 1st "
                "(UTC); you can also add your own key in Settings.",
            ) from None
    try:
        choice = llm.choose(provider, model, key, is_admin=is_admin, degraded=degraded)
        return choice, llm.make_chat_model(choice, key)
    except llm.ModelError as e:
        raise ChatError(400, str(e)) from None


def prepare(
    session: Session,
    sessions: Sessions,
    *,
    user_id: int,
    is_admin: bool,
    message: str,
    conversation_id: int | None,
    provider: Provider | None,
    model: str | None,
    key: SecretStr | None,
) -> Prepared:
    """Validate a chat request and save the question. Raises `ChatError`."""
    question = message.strip()
    cfg = agent_settings()
    if not question:
        raise ChatError(422, "Ask a question.")
    if len(question) > int(cfg.get("max_message_chars", 4000)):
        raise ChatError(422, "That question is too long.")
    has_key = has_user_key(key)
    choice, chat_model = resolve_model(session, is_admin=is_admin, provider=provider,
                                       model=model, key=key)  # fmt: skip

    if conversation_id is not None:
        conv = session.get(Conversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise ChatError(404, "conversation not found")
        history = load_history(session, conv.id, int(cfg.get("history_messages", 20)))
    else:
        conv = None
        history = []
    check_rate(session, user_id)

    if conv is None:
        conv = Conversation(user_id=user_id, title=_title(question))
        session.add(conv)
        session.flush()
    session.add(Message(conversation_id=conv.id, user_id=user_id, role="user", content=question))
    session.commit()
    return Prepared(
        user_id=user_id,
        conversation_id=conv.id,
        title=conv.title,
        choice=choice,
        model=chat_model,
        key=key if has_key else None,
        history=history,
        question=question,
        sessions=sessions,
        max_tool_calls=int(cfg.get("max_tool_calls", 10)),
        timeout=float(cfg.get("timeout_seconds", 90)),
    )


# --- The graph --------------------------------------------------------------------------------


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_calls: int


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal(0))
    model_calls: int = 0
    tool_calls: int = 0
    limited: bool = False
    truncated: bool = False


def _content_text(content: Any) -> str:
    """Tool or model content as plain text (strings, or lists of content blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def _parse_result(text: str, ok: bool) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return {"text": text} if ok else {"error": text}


def _as_of(result: Any) -> dt.datetime | None:
    if isinstance(result, dict) and isinstance(result.get("as_of"), str):
        try:
            day = dt.date.fromisoformat(result["as_of"][:10])
        except ValueError:
            return None
        return dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)
    return None


def _no_tools_choice(model: BaseChatModel) -> Any:
    # Anthropic needs the tools defined while the history holds tool calls, so the last turn
    # keeps them bound and switches them off instead of unbinding them.
    return {"type": "none"} if isinstance(model, ChatAnthropic) else "none"


async def call_tool(
    by_name: dict[str, BaseTool], call_id: str, name: str, args: dict[str, Any]
) -> tuple[str, bool]:
    """Run one tool call: (result text, ok). Never raises: a tool must never end the answer."""
    tool = by_name.get(name)
    if tool is None:
        return f"Unknown tool: {name}", False
    try:
        msg = await tool.ainvoke({"name": name, "args": args, "id": call_id, "type": "tool_call"})
    except Exception as e:
        log.warning("tool %s failed: %s", name, type(e).__name__)
        return f"Error executing tool {name}", False
    return _content_text(getattr(msg, "content", msg)), getattr(msg, "status", "success") != "error"


def save_snapshot(sessions: Sessions, user_id: int, conversation_id: int | None, tool: str,
                  args: dict[str, Any], result: Any) -> int:  # fmt: skip
    """Write one `agent_snapshots` row (the Data tab's "View data") and return its id."""
    with sessions() as s:
        row = AgentSnapshot(user_id=user_id, conversation_id=conversation_id, tool=tool,
                            args=args, result=result, as_of=_as_of(result))  # fmt: skip
        s.add(row)
        s.commit()
        return row.id


def build_graph(p: Prepared, tools: list[BaseTool], usage: Usage):
    by_name = {t.name: t for t in tools}
    with_tools = p.model.bind_tools(tools)
    without_tools = p.model.bind_tools(tools, tool_choice=_no_tools_choice(p.model))

    def record_usage(message: AIMessage) -> None:
        meta = message.usage_metadata or {}
        tokens_in, tokens_out = int(meta.get("input_tokens", 0)), int(meta.get("output_tokens", 0))
        usage.tokens_in += tokens_in
        usage.tokens_out += tokens_out
        usage.model_calls += 1
        if p.choice.server_key:
            with p.sessions() as s:
                usage.cost += cost.record(s, "chat", p.choice.model, tokens_in, tokens_out)

    async def agent(state: AgentState) -> dict[str, Any]:
        write = get_stream_writer()
        final = state["tool_calls"] >= p.max_tool_calls
        if final:
            usage.limited = True
        runnable = without_tools if final else with_tools
        messages = list(state["messages"]) + ([HumanMessage(LIMIT_NOTE)] if final else [])
        full: AIMessageChunk | None = None
        async for chunk in runnable.astream(messages):
            text = _content_text(chunk.content) if chunk.content else ""
            if text:
                write(("token", TokenEvent(text=text)))
            full = chunk if full is None else full + chunk
        if full is None:
            message = AIMessage(content="")
        else:
            message = AIMessage(content=full.content, tool_calls=full.tool_calls,
                                usage_metadata=full.usage_metadata, id=full.id)  # fmt: skip
            meta = full.response_metadata or {}
            if meta.get("stop_reason") == "max_tokens" or meta.get("finish_reason") == "length":
                usage.truncated = True  # Anthropic / OpenAI-style "hit max output tokens"
        await anyio.to_thread.run_sync(record_usage, message)
        if final and message.tool_calls:
            message = AIMessage(content=message.content, id=message.id)  # no more tools
        return {"messages": [message]}

    def save(name: str, args: dict[str, Any], result: Any) -> int:
        return save_snapshot(p.sessions, p.user_id, p.conversation_id, name, args, result)

    async def run_tools(state: AgentState) -> dict[str, Any]:
        write = get_stream_writer()
        last = state["messages"][-1]
        assert isinstance(last, AIMessage)
        used = state["tool_calls"]
        out: list[ToolMessage] = []
        for call in last.tool_calls:
            call_id = call.get("id") or f"call_{used}"
            name, args = call["name"], dict(call.get("args") or {})
            if used >= p.max_tool_calls:
                usage.limited = True
                out.append(ToolMessage(TOOL_BUDGET_USED, tool_call_id=call_id, name=name,
                                       status="error"))  # fmt: skip
                continue
            used += 1
            usage.tool_calls += 1
            write(("tool_start", ToolStartEvent(call_id=call_id, name=name, args=args)))
            text, ok = await call_tool(by_name, call_id, name, args)
            result = _parse_result(text, ok)
            snapshot_id = await anyio.to_thread.run_sync(save, name, args, result)
            write(("tool_end", ToolEndEvent(call_id=call_id, name=name, snapshot_id=snapshot_id,
                                            ok=ok, preview=text[:PREVIEW_CHARS])))  # fmt: skip
            out.append(ToolMessage(text, tool_call_id=call_id, name=name,
                                   status="success" if ok else "error"))  # fmt: skip
        return {"messages": out, "tool_calls": used}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("tools", run_tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, ["tools", END])
    graph.add_edge("tools", "agent")
    return graph.compile()


# --- Running it -------------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def desk_tools(
    sessions: Sessions, groups: str | None = None
) -> AsyncIterator[list[BaseTool]]:
    """desk-mcp's tools (all groups, or a comma-separated subset) over an in-memory MCP
    session, on the API's database sessions."""
    token = mcp_tools.session_override.set(sessions)
    server = build_server(groups, threaded=True)
    try:
        async with create_connected_server_and_client_session(server) as s:
            yield await load_mcp_tools(s)
    finally:
        mcp_tools.session_override.reset(token)


ToolsFactory = Callable[[Sessions], contextlib.AbstractAsyncContextManager[list[BaseTool]]]


def _save_answer(p: Prepared, text: str, usage: Usage) -> int:
    with p.sessions() as s:
        row = Message(
            conversation_id=p.conversation_id,
            user_id=p.user_id,
            role="assistant",
            content=text,
            model=p.choice.model,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            cost=usage.cost if p.choice.server_key else None,
        )
        s.add(row)
        s.commit()
        return row.id


_DONE = object()


async def run(p: Prepared, tools_factory: ToolsFactory = desk_tools) -> AsyncIterator[Event]:
    """Answer one question, yielding (event, payload) pairs. Never raises for model, tool or
    timeout failures: they end the stream with an `error` event."""
    yield (
        "conversation",
        ConversationEvent(
            id=p.conversation_id,
            title=p.title,
            model=p.choice.model,
            server_key=p.choice.server_key,
        ),
    )
    usage = Usage()
    parts: list[str] = []
    queue: asyncio.Queue[Any] = asyncio.Queue()
    today = dt.datetime.now(dt.UTC).date()

    async def work() -> None:
        try:
            async with asyncio.timeout(p.timeout):
                meta = {"user_id": p.user_id, "conversation_id": p.conversation_id,
                        "model": p.choice.model}  # fmt: skip
                with tracing.agent_tracing(server_key=p.choice.server_key, metadata=meta):
                    async with tools_factory(p.sessions) as tools:
                        graph = build_graph(p, tools, usage)
                        state = {
                            "messages": [SystemMessage(system_prompt(today, p.max_tool_calls)),
                                         *p.history, HumanMessage(p.question)],
                            "tool_calls": 0,
                        }  # fmt: skip
                        config = {"recursion_limit": 2 * p.max_tool_calls + 6}
                        async for item in graph.astream(state, config, stream_mode="custom"):
                            await queue.put(item)
        except Exception as e:
            await queue.put(("error", _error_event(e, p.timeout)))
        finally:
            await queue.put(_DONE)

    task = asyncio.create_task(work())
    failed = False
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            name, payload = item
            if name == "token":
                parts.append(payload.text)
            if name == "error":
                failed = True
            yield name, payload
        message_id = await anyio.to_thread.run_sync(_save_answer, p, "".join(parts), usage)
        if not failed:
            yield (
                "done",
                DoneEvent(
                    message_id=message_id,
                    model=p.choice.model,
                    tokens_in=usage.tokens_in,
                    tokens_out=usage.tokens_out,
                    cost_usd=float(usage.cost) if p.choice.server_key else None,
                    tool_calls=usage.tool_calls,
                    limited=usage.limited,
                    truncated=usage.truncated,
                ),
            )
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


def _leaf(e: BaseException) -> BaseException:
    """The original error: the MCP session's task group wraps failures in exception groups."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


def _error_event(e: Exception, timeout: float) -> ErrorEvent:
    leaf = _leaf(e)
    if isinstance(leaf, TimeoutError):
        return ErrorEvent(code="timeout", message=f"The answer took longer than {int(timeout)} "
                                                  "seconds and was stopped.")  # fmt: skip
    if isinstance(leaf, cost.UnknownPrice):
        return ErrorEvent(code="internal", message="The server model has no price set.")
    # Only the exception type is logged: provider messages can contain key fragments.
    log.warning("agent run failed: %s", type(leaf).__name__)
    return ErrorEvent(code="provider", message=_provider_message(leaf))


def _provider_message(e: BaseException) -> str:
    """Our own words for a provider failure, picked from the HTTP status when there is one."""
    status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None),
                                                        "status_code", None)  # fmt: skip
    messages = {
        401: "Your key was rejected by the provider. Check it in Settings.",
        402: "Your provider account has no credit left.",
        403: "Your key isn't allowed to use this model.",
        404: "The provider doesn't know this model id.",
        429: "The provider is rate limiting your key. Try again in a minute.",
    }
    if isinstance(status, int) and status in messages:
        return messages[status]
    if isinstance(status, int) and status >= 500:
        return "The model provider had an error. Try again."
    return "The model call failed. Try again, or pick another model."


# --- Conversations ----------------------------------------------------------------------------


def list_conversations(session: Session, user_id: int) -> list[dict[str, Any]]:
    last = func.max(Message.created_at)
    rows = session.execute(
        select(
            Conversation.id,
            Conversation.title,
            Conversation.created_at,
            last,
            func.count(Message.id),
        )  # fmt: skip
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user_id)
        .group_by(Conversation.id)
        .order_by(func.coalesce(last, Conversation.created_at).desc())
    ).all()
    return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3] or r[2],
             "messages": r[4]} for r in rows]  # fmt: skip


def conversation_detail(session: Session, user_id: int, conversation_id: int) -> dict | None:
    conv = session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        return None
    messages = session.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id, Message.role.in_(["user", "assistant"]))
        .order_by(Message.id)
    ).all()
    snaps = session.execute(
        select(AgentSnapshot.id, AgentSnapshot.tool, AgentSnapshot.created_at)
        .where(AgentSnapshot.conversation_id == conv.id)
        .order_by(AgentSnapshot.id)
    ).all()
    out, pending = [], list(snaps)
    for m in messages:
        item = {"id": m.id, "role": m.role, "content": m.content, "model": m.model,
                "created_at": m.created_at, "snapshots": []}  # fmt: skip
        if m.role == "assistant":
            # A tool call belongs to the first answer saved after it.
            while pending and pending[0][2] <= m.created_at:
                sid, tool, created = pending.pop(0)
                item["snapshots"].append({"id": sid, "tool": tool, "created_at": created})
        out.append(item)
    return {"id": conv.id, "title": conv.title, "created_at": conv.created_at, "messages": out}


def delete_conversation(session: Session, user_id: int, conversation_id: int) -> bool:
    """Delete a user's own conversation with its messages and snapshots (FK cascades)."""
    result = session.execute(
        delete(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    session.commit()
    return bool(result.rowcount)
