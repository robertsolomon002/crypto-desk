"""Load check (Stage 8.1, D53): three users ask the agent at the same time.

One API process serves them, as one Cloud Run instance would (max 2 instances, concurrency 80).
The model is a fake that waits before each turn (a tool call, then the answer); the tools are
the real desk-mcp tools on the seeded test database. The answers must overlap rather than
queue: the model waits are awaited on the event loop, and the tools and database writes run
in worker threads, so three chats take about as long as one. Each must finish with `done`,
one snapshot per tool call and its own conversation.

The numbers measured on Rob's machine are in docs/DECISIONS.md (D53).
"""

import asyncio
import time
import tracemalloc

import httpx
from sqlalchemy import func, select

from desk.api.main import app
from desk.models import AgentSnapshot, Conversation
from tests.agent_fakes import ScriptedModel, answer, ask, sse
from tests.api_fakes import ADMIN, MEMBER, auth

WAIT = 0.6  # seconds before each model turn, so one chat takes at least 2 * WAIT
USERS = [
    (ADMIN, {}, {"message": "List the coins."}),  # the server key
    (MEMBER, {"X-LLM-Key": "sk-or-load-1"},
     {"message": "List the coins.", "provider": "openrouter"}),
    ("user_load_3", {"X-LLM-Key": "sk-or-load-2"},
     {"message": "List the coins.", "provider": "openrouter"}),
]  # fmt: skip


async def ask_agent(client: httpx.AsyncClient, user: str, key: dict, body: dict) -> tuple:
    start = time.perf_counter()
    r = await client.post("/api/agent/chat", json=body, headers={**auth(user), **key})
    return r.status_code, sse(r.text), time.perf_counter() - start


async def burst(n: int) -> tuple[list, float]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        start = time.perf_counter()
        results = await asyncio.gather(*(ask_agent(c, *USERS[i]) for i in range(n)))
        return list(results), time.perf_counter() - start


def test_three_concurrent_chats_overlap(api, api_sessions, monkeypatch) -> None:
    from desk.agents import llm

    monkeypatch.setattr(llm, "make_chat_model", lambda choice, key: ScriptedModel(
        script=[ask("list_coins"), answer], delays=[WAIT, WAIT]))  # fmt: skip

    [(status, _, _)], single = asyncio.run(burst(1))
    assert status == 200
    tracemalloc.start()
    results, wall = asyncio.run(burst(3))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"\nload check: one chat {single:.2f} s, three at once {wall:.2f} s, "
          f"peak Python allocations during the three {peak / 1024**2:.1f} MiB")  # fmt: skip

    for status, events, seconds in results:
        names = [e for e, _ in events]
        assert status == 200 and names[-1] == "done", names
        assert names.count("tool_end") == 1 and seconds >= 2 * WAIT
    # Queued, the three would take about 3x one chat; overlapped, about 1x.
    assert wall < 1.6 * single, (wall, single)
    with api_sessions() as s:
        assert s.scalar(select(func.count()).select_from(AgentSnapshot)) == 4
        assert s.scalar(select(func.count(func.distinct(Conversation.user_id)))) == 3


def test_concurrent_chats_respect_the_hourly_limit(api, monkeypatch) -> None:
    """The per-user hourly limit is counted in the database. Three questions sent at once by
    a user with one question left: exactly one gets through."""
    from desk.agents import chat, llm

    monkeypatch.setattr(llm, "make_chat_model", lambda choice, key: ScriptedModel(
        script=[answer], delays=[WAIT]))  # fmt: skip
    monkeypatch.setattr(chat, "agent_settings",
                        lambda: {**chat.load_app_settings()["agent"],
                                 "messages_per_user_per_hour": 1})  # fmt: skip

    async def same_user() -> list[int]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
            rs = await asyncio.gather(*(ask_agent(c, *USERS[1]) for _ in range(3)))
            return sorted(r[0] for r in rs)

    assert asyncio.run(same_user()) == [200, 429, 429]
