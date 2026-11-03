"""Test doubles for the agent (Stage 5.1): a scripted streaming chat model and an SSE parser."""

import asyncio
import json
import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field


def ask(
    name: str, args: dict[str, Any] | None = None, text: str = "", call_id: str = "c"
) -> AIMessage:
    """A scripted model turn that calls one tool."""
    return AIMessage(text, tool_calls=[{"name": name, "args": args or {}, "id": call_id}])


answer = AIMessage("ok")


class ScriptedModel(BaseChatModel):
    """Answers with `script` in order (repeating the last turn), streaming text word by word and
    then the tool calls and usage in one final chunk. Records what it was sent."""

    script: list[AIMessage]
    delays: list[float] = Field(default_factory=list)  # seconds before turn n's first token
    usage: tuple[int, int] = (1000, 200)
    stop_reason: str | None = None  # e.g. "max_tokens" on the final chunk
    log: dict[str, list[Any]] = Field(
        default_factory=lambda: {"messages": [], "tool_choice": [], "tools": []}
    )

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        return self.bind(tool_choice=tool_choice, tool_names=[t.name for t in tools])

    def _next(self, messages: list, kwargs: dict[str, Any]) -> AIMessage:
        n = len(self.log["messages"])
        self.log["messages"].append(list(messages))
        self.log["tool_choice"].append(kwargs.get("tool_choice"))
        self.log["tools"].append(kwargs.get("tool_names"))
        return self.script[min(n, len(self.script) - 1)]

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages, kwargs))])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs: Any):
        n = len(self.log["messages"])
        msg = self._next(messages, kwargs)
        if n < len(self.delays) and self.delays[n]:
            await asyncio.sleep(self.delays[n])
        for word in re.split(r"(\s)", str(msg.content or "")):
            if word:
                yield ChatGenerationChunk(message=AIMessageChunk(content=word))
        chunks = [
            {"name": c["name"], "args": json.dumps(c["args"]), "id": f"{c['id']}{n}_{i}",
             "index": i}
            for i, c in enumerate(msg.tool_calls)
        ]  # fmt: skip
        tin, tout = self.usage
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                tool_call_chunks=chunks,
                usage_metadata={"input_tokens": tin, "output_tokens": tout,
                                "total_tokens": tin + tout},
                response_metadata={"stop_reason": self.stop_reason} if self.stop_reason else {},
            )
        )  # fmt: skip


def sse(text: str) -> list[tuple[str, Any]]:
    """(event, data) pairs from an SSE body; keepalive comments are skipped."""
    out = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data = None, None
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if name:
            out.append((name, data))
    return out


# --- The multi-agent desk (Stage 5.3) ---------------------------------------------------------

DEFAULT_TURNS: dict[str, list[AIMessage]] = {
    "technical": [ask("get_regime", {"coin": "BTC"}, call_id="t"), AIMessage("done")],
    "context": [ask("get_sentiment", {"days": 3}, call_id="c"), AIMessage("done")],
}
DEFAULT_OUTPUTS: dict[str, dict[str, Any]] = {
    "ReportOut": {"summary": "A short report.",
                  "findings": [{"claim": "The regime is a range.", "value": "range",
                                "tool": "get_regime"}]},
    "CaseOut": {"points": [{"text": "The point.", "cites": ["T1"]}]},
    "SignalOut": {"stance": "flat", "confidence": 0.55, "entry_low": None, "entry_high": None,
                  "invalidation": None, "target": None, "rationale": "No edge.", "cites": ["T1"]},
}  # fmt: skip


class DeskModel(BaseChatModel):
    """A scripted model for the desk: each call is routed by its `desk:<node>` tag.

    - `turns[node]`: the analyst's research turns, in order (repeating the last);
    - `outputs[node]`: structured outputs as dicts, in order (repeating the last), validated
      against the schema the desk asked for; an invalid dict becomes a parsing error;
    - `delays[node]` seconds before each call, `errors[node]` raised on each call.
    `log[node]` records every call as (kind, messages, tool names)."""

    turns: dict[str, list[AIMessage]] = Field(default_factory=lambda: dict(DEFAULT_TURNS))
    outputs: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    delays: dict[str, float] = Field(default_factory=dict)
    errors: dict[str, Any] = Field(default_factory=dict)
    usage: tuple[int, int] = (1000, 100)
    log: dict[str, list[Any]] = Field(default_factory=dict)
    windows: dict[str, list[tuple[float, float]]] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "desk-scripted"

    @staticmethod
    def _node(tags: list[str] | None) -> str:
        for tag in tags or []:
            if tag.startswith("desk:"):
                return tag[5:]
        return "?"

    def _usage(self) -> dict[str, int]:
        tin, tout = self.usage
        return {"input_tokens": tin, "output_tokens": tout, "total_tokens": tin + tout}

    async def _before(self, node: str) -> float:
        start = asyncio.get_running_loop().time()
        if self.delays.get(node):
            await asyncio.sleep(self.delays[node])
        if node in self.errors:
            raise self.errors[node]
        return start

    def _span(self, node: str, start: float) -> None:
        self.windows.setdefault(node, []).append((start, asyncio.get_running_loop().time()))

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        return self.bind(tool_names=[t.name for t in tools])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("the desk calls models asynchronously")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        node = self._node(run_manager.tags if run_manager else None)
        calls = self.log.setdefault(node, [])
        n = sum(1 for c in calls if c[0] == "turn")
        calls.append(("turn", list(messages), kwargs.get("tool_names")))
        start = await self._before(node)
        script = self.turns.get(node) or [AIMessage("done")]
        msg = script[min(n, len(script) - 1)]
        calls_out = [{**c, "id": f"{c['id']}{n}_{i}"} for i, c in enumerate(msg.tool_calls)]
        self._span(node, start)
        out = AIMessage(content=msg.content, tool_calls=calls_out, usage_metadata=self._usage())
        return ChatResult(generations=[ChatGeneration(message=out)])

    def with_structured_output(self, schema: Any, *, include_raw: bool = False, **kwargs: Any):
        from langchain_core.runnables import RunnableLambda
        from pydantic import ValidationError

        async def run(messages: Any, config: Any) -> dict[str, Any]:
            node = self._node((config or {}).get("tags"))
            calls = self.log.setdefault(node, [])
            n = sum(1 for c in calls if c[0] == "structured")
            calls.append(("structured", list(messages), schema.__name__))
            start = await self._before(node)
            outs = self.outputs.get(node) or [DEFAULT_OUTPUTS[schema.__name__]]
            data = outs[min(n, len(outs) - 1)]
            self._span(node, start)
            raw = AIMessage("", usage_metadata=self._usage())
            try:
                return {"raw": raw, "parsed": schema.model_validate(data), "parsing_error": None}
            except ValidationError as e:
                return {"raw": raw, "parsed": None, "parsing_error": e}

        return RunnableLambda(run)
