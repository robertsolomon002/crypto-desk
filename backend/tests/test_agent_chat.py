"""The chat agent (Stage 5.1): tool flow over the in-memory desk-mcp session, limits, timeout,
snapshots, the server-key budget, rate limits and conversation ownership. Models are scripted
fakes; the tools are the real desk-mcp tools on the seeded test database."""

import datetime as dt
from decimal import Decimal
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import func, select

from desk.agents import chat, llm
from desk.models import AgentSnapshot, Conversation, LlmSpend, Message
from tests.agent_fakes import ScriptedModel, ask, sse
from tests.api_fakes import ADMIN, CANARY, MEMBER, OTHER_MEMBER, auth

KEY = {"X-LLM-Key": CANARY}
BODY = {"message": "Where is BTC vs its key levels?", "provider": "openrouter"}


@pytest.fixture
def model(monkeypatch):
    """`model(*turns, **fields)` makes the agent use a scripted model; returns it, with the
    `ModelChoice` it was built for in `model.choices`."""

    def use(*turns, **fields) -> ScriptedModel:
        fake = ScriptedModel(script=list(turns), **fields)
        fake.log["choices"] = []

        def make(choice: llm.ModelChoice, key: Any) -> ScriptedModel:
            fake.log["choices"].append(choice)
            return fake

        monkeypatch.setattr(llm, "make_chat_model", make)
        return fake

    return use


@pytest.fixture
def settings(monkeypatch):
    """Override `config/settings.yaml` agent values for one test."""

    def use(**values) -> None:
        base = chat.agent_settings()
        monkeypatch.setattr(chat, "agent_settings", lambda: {**base, **values})

    return use


def post(api, body=None, headers=None):
    r = api.post("/api/agent/chat", json=body or BODY, headers=headers or {**auth(MEMBER), **KEY})
    return r, (sse(r.text) if r.status_code == 200 else [])


def names(events) -> list[str]:
    return [e[0] for e in events]


def test_tool_flow_streams_events_and_writes_snapshots(api, api_sessions, model) -> None:
    fake = model(
        ask("get_key_levels", {"coin": "BTC"}, text="Checking levels.", call_id="k"),
        ask("list_coins", call_id="l"),
        AIMessage("BTC sits between its 50D and 200D SMA (get_key_levels)."),
    )
    r, events = post(api)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    order = [n for n in names(events) if n != "token"]
    assert order == ["conversation", "tool_start", "tool_end", "tool_start", "tool_end", "done"]
    conv = events[0][1]
    assert conv["title"] == BODY["message"] and conv["server_key"] is False
    assert conv["model"] == "anthropic/claude-haiku-5.5"  # the OpenRouter default

    starts = [d for n, d in events if n == "tool_start"]
    ends = [d for n, d in events if n == "tool_end"]
    assert [s["name"] for s in starts] == ["get_key_levels", "list_coins"]
    assert starts[0]["args"] == {"coin": "BTC"}
    assert all(e["ok"] for e in ends) and [s["call_id"] for s in starts] == [
        e["call_id"] for e in ends
    ]
    text = "".join(d["text"] for n, d in events if n == "token")
    assert text == "Checking levels.BTC sits between its 50D and 200D SMA (get_key_levels)."

    done = events[-1][1]
    assert done["tool_calls"] == 2 and done["limited"] is False and done["cost_usd"] is None
    assert done["truncated"] is False
    assert done["tokens_in"] == 3000 and done["tokens_out"] == 600

    # The tools were offered to the model, and their results went back to it.
    assert "get_cycle_comparison" in fake.log["tools"][0]
    last_sent = fake.log["messages"][-1]
    assert [m.type for m in last_sent][:2] == ["system", "human"]
    assert "Today is" in last_sent[0].content and "{today}" not in last_sent[0].content
    assert sum(m.type == "tool" for m in last_sent) == 2

    with api_sessions() as s:
        snaps = s.scalars(select(AgentSnapshot).order_by(AgentSnapshot.id)).all()
        assert [x.id for x in snaps] == [e["snapshot_id"] for e in ends]
        levels = snaps[0]
        assert levels.tool == "get_key_levels" and levels.args == {"coin": "BTC"}
        assert levels.conversation_id == conv["id"]
        assert set(levels.result) == {"as_of", "sources", "data"}  # the exact tool JSON
        assert levels.as_of == dt.datetime(2026, 10, 27, tzinfo=dt.UTC)
        assert ends[0]["preview"] and len(ends[0]["preview"]) <= 300
        msgs = s.scalars(select(Message).order_by(Message.id)).all()
        assert [(m.role, m.content) for m in msgs] == [("user", BODY["message"]),
                                                       ("assistant", text)]  # fmt: skip
        assert msgs[1].id == done["message_id"] and msgs[1].cost is None
        assert msgs[1].tokens_in == 3000
        assert s.scalar(select(func.count()).select_from(LlmSpend)) == 0  # a user key


def test_tool_errors_are_snapshotted_and_passed_back(api, api_sessions, model) -> None:
    fake = model(ask("get_regime", {"coin": "NOPE"}), ask("no_such_tool"), AIMessage("Sorry."))
    _, events = post(api)
    ends = [d for n, d in events if n == "tool_end"]
    assert [e["ok"] for e in ends] == [False, False]
    assert "NOPE" in ends[0]["preview"]
    assert "Unknown tool" in ends[1]["preview"]
    assert names(events)[-1] == "done"
    tool_msgs = [m for m in fake.log["messages"][-1] if m.type == "tool"]
    assert [m.status for m in tool_msgs] == ["error", "error"]
    with api_sessions() as s:
        results = s.scalars(select(AgentSnapshot.result).order_by(AgentSnapshot.id)).all()
        assert all("error" in r for r in results)


def test_tool_call_limit_forces_a_final_answer(api, api_sessions, model, settings) -> None:
    settings(max_tool_calls=3)
    fake = model(ask("list_coins", text="More."))  # it would call tools forever
    _, events = post(api)
    assert names(events).count("tool_end") == 3
    done = events[-1]
    assert done[0] == "done" and done[1]["limited"] is True and done[1]["tool_calls"] == 3
    # Four model turns: three with tools, then one with tools switched off and the note.
    assert fake.log["tool_choice"] == [None, None, None, "none"]
    assert fake.log["messages"][-1][-1].content == chat.LIMIT_NOTE
    with api_sessions() as s:
        assert s.scalar(select(func.count()).select_from(AgentSnapshot)) == 3


def test_parallel_calls_past_the_limit_are_not_run(api, model, settings) -> None:
    settings(max_tool_calls=2)
    three = AIMessage("", tool_calls=[{"name": "list_coins", "args": {}, "id": f"p{i}"}
                                      for i in range(3)])  # fmt: skip
    fake = model(three, AIMessage("Done."))
    _, events = post(api)
    assert names(events).count("tool_start") == 2
    tool_msgs = [m for m in fake.log["messages"][1] if m.type == "tool"]
    assert [m.content == chat.TOOL_BUDGET_USED for m in tool_msgs] == [False, False, True]
    assert events[-1][1]["limited"] is True


def test_timeout_ends_with_an_error_and_keeps_the_partial_answer(
    api, api_sessions, model, settings
) -> None:
    settings(timeout_seconds=1.5)
    model(ask("list_coins", text="Looking."), AIMessage("never"), delays=[0, 5])
    _, events = post(api)
    assert names(events)[-1] == "error" and "done" not in names(events)
    assert events[-1][1]["code"] == "timeout"
    with api_sessions() as s:
        answer = s.scalars(select(Message).where(Message.role == "assistant")).one()
        assert answer.content == "Looking."


def test_provider_failure_is_our_own_message(api, monkeypatch) -> None:
    class Boom(Exception):
        status_code = 401

    class Failing(ScriptedModel):
        async def _astream(self, *a, **k):
            raise Boom(f"invalid key {CANARY[:12]}...")
            yield  # pragma: no cover

    monkeypatch.setattr(llm, "make_chat_model", lambda c, k: Failing(script=[]))
    r, events = post(api)
    assert events[-1] == ("error", {"code": "provider",
                                    "message": "Your key was rejected by the provider. "
                                               "Check it in Settings."})  # fmt: skip
    assert CANARY[:12] not in r.text


def test_an_answer_cut_off_at_the_token_limit_is_flagged(api, model) -> None:
    model(AIMessage("A long answer that stops mid"), stop_reason="max_tokens")
    _, events = post(api)
    assert events[-1][0] == "done" and events[-1][1]["truncated"] is True


def test_conversation_memory_and_ownership(api, api_sessions, model) -> None:
    fake = model(ask("list_coins"), AIMessage("First answer."))
    _, events = post(api)
    conv_id = events[0][1]["id"]
    fake.log["messages"].clear()
    fake.script[:] = [AIMessage("Second answer.")]
    _, events = post(api, {**BODY, "conversation_id": conv_id, "message": "And ETH?"})
    assert events[0][1]["id"] == conv_id
    sent = fake.log["messages"][0]
    assert [m.type for m in sent] == ["system", "human", "ai", "human"]
    assert sent[2].content == "First answer." and sent[3].content == "And ETH?"

    detail = api.get(f"/api/agent/conversations/{conv_id}", headers=auth(MEMBER)).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert [len(m["snapshots"]) for m in detail["messages"]] == [0, 1, 0, 0]
    snap_id = detail["messages"][1]["snapshots"][0]["id"]
    listing = api.get("/api/agent/conversations", headers=auth(MEMBER)).json()
    assert [(c["id"], c["messages"]) for c in listing] == [(conv_id, 4)]

    snap = api.get(f"/api/agent/snapshots/{snap_id}", headers=auth(MEMBER)).json()
    assert snap["tool"] == "list_coins" and snap["result"]["data"]

    other = auth(OTHER_MEMBER)
    assert api.get(f"/api/agent/conversations/{conv_id}", headers=other).status_code == 404
    assert api.get(f"/api/agent/snapshots/{snap_id}", headers=other).status_code == 404
    assert api.delete(f"/api/agent/conversations/{conv_id}", headers=other).status_code == 404
    assert api.get("/api/agent/conversations", headers=other).json() == []
    r, _ = post(api, {**BODY, "conversation_id": conv_id}, {**other, **KEY})
    assert r.status_code == 404
    assert api.get(f"/api/agent/snapshots/{snap_id}", headers=auth(ADMIN)).status_code == 200

    assert api.delete(f"/api/agent/conversations/{conv_id}", headers=auth(MEMBER)).status_code \
        == 204  # fmt: skip
    with api_sessions() as s:
        for table in (Conversation, Message, AgentSnapshot):
            assert s.scalar(select(func.count()).select_from(table)) == 0, table


def test_member_without_a_key_gets_a_clear_error(api, api_sessions, model) -> None:
    model()
    r = api.post("/api/agent/chat", json={"message": "hi"}, headers=auth(MEMBER))
    assert r.status_code == 400 and "Settings" in r.json()["detail"]
    r = api.post("/api/agent/chat", json={"message": "hi"}, headers={**auth(MEMBER), **KEY})
    assert r.status_code == 400 and "provider" in r.json()["detail"]
    with api_sessions() as s:  # nothing saved for a refused request
        assert s.scalar(select(func.count()).select_from(Message)) == 0


def _spend(api_sessions, usd: str) -> None:
    with api_sessions() as s:
        s.add(
            LlmSpend(
                date=dt.datetime.now(dt.UTC).date(),
                source="chat",
                model="claude-haiku-5-5",
                tokens_in=0,
                tokens_out=0,
                cost=Decimal(usd),
            )
        )
        s.commit()  # fmt: skip


def test_admin_server_key_records_spend(api, api_sessions, model) -> None:
    fake = model(ask("list_coins"), AIMessage("Answer."), usage=(10_000, 1_000))
    _, events = post(api, {"message": "hi"}, auth(ADMIN))
    choice = fake.log["choices"][0]
    assert choice.server_key and choice.model == "claude-haiku-5-5" and not choice.degraded
    assert events[0][1]["server_key"] is True
    done = events[-1][1]
    # 2 calls x (10,000 x $0.10 + 1,000 x $0.50) / 1M = $0.003
    assert done["cost_usd"] == pytest.approx(0.003)
    with api_sessions() as s:
        rows = s.scalars(select(LlmSpend)).all()
        assert [(r.source, r.model, r.tokens_in) for r in rows] == [
            ("chat", "claude-haiku-5-5", 10_000)
        ] * 2
        answer = s.scalars(select(Message).where(Message.role == "assistant")).one()
        assert answer.cost == Decimal("0.003000")


def test_admin_near_the_cap_degrades_and_over_it_is_refused(api, api_sessions, model) -> None:
    fake = model(AIMessage("ok"))
    _spend(api_sessions, "6.50")  # over 80% of $8
    _, events = post(api, {"message": "hi"}, auth(ADMIN))
    assert fake.log["choices"][0].degraded and names(events)[-1] == "done"
    _spend(api_sessions, "1.50")
    r = api.post("/api/agent/chat", json={"message": "hi"}, headers=auth(ADMIN))
    assert r.status_code == 402 and "budget" in r.json()["detail"]
    # An admin's own key is never capped.
    r, events = post(api, BODY, {**auth(ADMIN), **KEY})
    assert r.status_code == 200 and names(events)[-1] == "done"


def test_hourly_message_limit(api, model, settings) -> None:
    settings(messages_per_user_per_hour=2)
    model(AIMessage("ok"))
    assert post(api)[0].status_code == 200
    assert post(api)[0].status_code == 200
    r, _ = post(api)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 3500
    assert post(api, headers={**auth(OTHER_MEMBER), **KEY})[0].status_code == 200


def test_bad_requests(api, model) -> None:
    model()
    h = {**auth(MEMBER), **KEY}
    long = {**BODY, "message": "x" * 4001}
    assert api.post("/api/agent/chat", json=long, headers=h).status_code == 422
    bad_model = {**BODY, "model": "evil model; rm"}
    assert api.post("/api/agent/chat", json=bad_model, headers=h).status_code == 422
    assert api.post("/api/agent/chat", json=BODY).status_code == 401


# --- Unit: model factory and budget -----------------------------------------------------------


def test_provider_routing(monkeypatch) -> None:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.load import dumpd
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    key = SecretStr(CANARY)
    made = {}
    for provider in ("openrouter", "anthropic", "openai"):
        choice = llm.choose(provider, None, key, is_admin=False)
        made[provider] = llm.make_chat_model(choice, key)
        assert not choice.server_key
        blob = str(dumpd(made[provider])) + repr(made[provider])
        assert CANARY not in blob
    router, anthropic, openai = made["openrouter"], made["anthropic"], made["openai"]
    assert isinstance(router, ChatOpenAI) and router.openai_api_base == llm.OPENROUTER_BASE_URL
    assert router.model_name == "anthropic/claude-haiku-5.5" and router.use_responses_api is False
    assert router.stream_usage is True
    assert isinstance(anthropic, ChatAnthropic) and anthropic.model == "claude-haiku-5-5"
    assert isinstance(openai, ChatOpenAI) and openai.model_name == "gpt-6-luna"
    assert openai.openai_api_base is None and openai.reasoning_effort == "none"
    assert router.openai_api_key.get_secret_value() == CANARY  # the key itself is used

    picked = llm.choose("openrouter", "openai/gpt-5-mini", key, is_admin=False)
    assert picked.model == "openai/gpt-5-mini"
    with pytest.raises(llm.ModelError, match="Settings"):
        llm.choose("openrouter", None, SecretStr("  "), is_admin=False)
    with pytest.raises(llm.ModelError, match="provider"):
        llm.choose(None, None, key, is_admin=True)
    with pytest.raises(llm.ModelError, match="valid"):
        llm.choose("openai", "bad id!", key, is_admin=False)

    class S:
        anthropic_api_key = SecretStr("server-key")

    monkeypatch.setattr(llm, "get_settings", lambda: S)
    server = llm.choose(None, None, None, is_admin=True)
    assert server.server_key and server.model == "claude-haiku-5-5"
    m = llm.make_chat_model(server, None)
    assert isinstance(m, ChatAnthropic) and m.max_tokens == 4000 and m.reasoning_effort is None
    degraded = llm.make_chat_model(llm.choose(None, None, None, is_admin=True, degraded=True),
                                   None)  # fmt: skip
    assert degraded.max_tokens == 1500 and degraded.reasoning_effort == "low"
    S.anthropic_api_key = None
    with pytest.raises(llm.ModelError, match="server key"):
        llm.make_chat_model(server, None)


def test_cost_prices_and_budget(pg_sessions) -> None:
    from desk.agents import cost

    assert cost.call_cost("claude-haiku-5-5", 100_000, 1_000_000) == Decimal("0.510000")
    assert cost.call_cost("claude-haiku-5-5", 200_000, 1_000_000) == Decimal("2.600000")  # long
    assert cost.call_cost("claude-sonnet-5-5", 1000, 1000) == Decimal("0.012000")
    with pytest.raises(cost.UnknownPrice):
        cost.call_cost("mystery", 1, 1)

    today = dt.date(2026, 11, 15)
    with pg_sessions() as s:
        cost.record(s, "chat", "claude-sonnet-5-5", 300_000, 100_000, day=dt.date(2026, 10, 31))
        assert cost.month_spend(s, today) == 0  # last month doesn't count
        cost.record(s, "desk", "claude-sonnet-5-5", 2_000_000, 100_000, day=today)  # $5
        b = cost.check_budget(s, today)
        assert b.spent == Decimal("5.000000") and not b.degraded and b.remaining == 3
        cost.record(s, "brief", "claude-sonnet-5-5", 750_000, 0, day=today)  # $1.50
        assert cost.check_budget(s, today).degraded
        cost.record(s, "mco", "claude-sonnet-5-5", 750_000, 0, day=today)
        with pytest.raises(cost.BudgetExceeded):
            cost.check_budget(s, today)
