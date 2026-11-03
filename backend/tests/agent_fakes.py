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
