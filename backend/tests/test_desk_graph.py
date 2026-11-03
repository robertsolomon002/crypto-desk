"""The multi-agent desk (Stage 5.3, D47): topology and parallelism, per-analyst tool groups,
the validator and its one retry, node timeouts, as_of, spend, refusals and the key canary.
Models are `DeskModel` fakes routed by node; the tools are the real desk-mcp tools on the
seeded test database."""

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import cast, func, select
from sqlalchemy.types import Text

from desk.agents import desk_graph, llm
from desk.agents.desk_graph import validate
from desk.agents.schemas import DeskSignal
from desk.mcp_server.tools import TOOLS
from desk.models import AgentSnapshot, CandleDaily, Conversation, LlmSpend, Message
from tests.agent_fakes import DeskModel, ask, sse
from tests.api_fakes import ADMIN, CANARY, MEMBER, auth

KEY = {"X-LLM-Key": CANARY}
BODY = {"coin": "BTC", "provider": "openrouter"}
ANALYSTS = ("technical", "context")
OPENINGS = ("bull_open", "bear_open")
REBUTTALS = ("bull_rebut", "bear_rebut")


@pytest.fixture
def desk(monkeypatch):
    """`desk(**fields)` makes the run use a `DeskModel`; returns it."""

    def use(**fields) -> DeskModel:
        fake = DeskModel(**fields)
        monkeypatch.setattr(llm, "make_chat_model", lambda choice, key: fake)
        return fake

    return use


@pytest.fixture
def settings(monkeypatch):
    """Override `config/settings.yaml` desk values for one test."""

    def use(**values) -> None:
        base = desk_graph.desk_settings()
        monkeypatch.setattr(desk_graph, "desk_settings", lambda: {**base, **values})

    return use


def post(api, body=None, headers=None):
    r = api.post("/api/agent/desk", json=body or BODY, headers=headers or {**auth(MEMBER), **KEY})
    return r, (sse(r.text) if r.status_code == 200 else [])


def sent(fake: DeskModel, node: str, call: int = 0) -> str:
    """The text of every message the model got on one call of a node."""
    return " | ".join(str(m.content) for m in fake.log[node][call][1])


def index(events, name: str, node: str | None = None, nth: int = 0) -> int:
    hits = [i for i, (n, d) in enumerate(events)
            if n == name and (node is None or (d or {}).get("node") == node)]  # fmt: skip
    return hits[nth]


def last_close(api_sessions, coin: str = "BTC") -> float:
    with api_sessions() as s:
        q = select(CandleDaily.close).where(CandleDaily.coin == coin)
        return float(s.scalar(q.order_by(CandleDaily.date.desc()).limit(1)))


def long_signal(close: float, **changes: Any) -> dict[str, Any]:
    base = {"stance": "lean_long", "confidence": 0.6, "entry_low": close * 0.97,
            "entry_high": close * 0.99, "invalidation": close * 0.92, "target": close * 1.08,
            "rationale": "Range support holds.", "cites": ["T1"]}  # fmt: skip
    return {**base, **changes}


# --- Topology, parallelism, tools ------------------------------------------------------------


def test_desk_runs_in_graph_order_and_saves_everything(api, api_sessions, desk) -> None:
    fake = desk()
    r, events = post(api)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert events[0][0] == "desk"
    run = events[0][1]
    assert run["coin"] == "BTC" and run["title"] == "Ask the desk: BTC"
    assert run["server_key"] is False and run["reference_close"] == pytest.approx(
        last_close(api_sessions)
    )

    # Every node waits for the ones it depends on.
    for analyst in ANALYSTS:
        for opening in OPENINGS:
            assert index(events, "node_end", analyst) < index(events, "node_start", opening)
    for opening in OPENINGS:
        for rebuttal in REBUTTALS:
            assert index(events, "node_end", opening) < index(events, "node_start", rebuttal)
    for rebuttal in REBUTTALS:
        assert index(events, "node_end", rebuttal) < index(events, "node_start", "head")
    assert index(events, "node_end", "head") < index(events, "node_start", "validator")
    assert [n for n, _ in events[-2:]] == ["signal", "done"]

    # Rebuttals answer both openings; the head sees the reports and the whole debate.
    for rebuttal in REBUTTALS:
        text = sent(fake, rebuttal)
        assert "<bull_open>" in text and "<bear_open>" in text and "<technical_report>" in text
    head_sent = sent(fake, "head")
    assert all(f"<{n}>" in head_sent for n in (*OPENINGS, *REBUTTALS))
    assert "Last daily close" in head_sent

    # Tool calls carry their node and snapshot; findings get ids the debate can cite.
    ends = [d for n, d in events if n == "tool_end"]
    assert {e["node"] for e in ends} == set(ANALYSTS) and all(e["ok"] for e in ends)
    tech = next(d for n, d in events if n == "node_end" and d["node"] == "technical")
    assert tech["status"] == "done" and tech["report"]["findings"][0]["id"] == "T1"
    ctx = next(d for n, d in events if n == "node_end" and d["node"] == "context")
    assert ctx["report"]["findings"][0]["id"] == "C1"
    bull = next(d for n, d in events if n == "node_end" and d["node"] == "bull_open")
    assert bull["case"]["points"][0] == {"text": "The point.", "cites": ["T1"],
                                         "unknown_cites": []}  # fmt: skip

    done = events[-1][1]
    assert done["status"] == "valid" and done["cost_usd"] is None
    assert done["tool_calls"] == 2 and done["model_calls"] == 11  # 2 x (2 turns + report) + 4 + 1
    assert [u["node"] for u in done["usage"]] == [
        "technical", "context", "bull_open", "bear_open", "bull_rebut", "bear_rebut", "head",
        "validator",
    ]  # fmt: skip

    with api_sessions() as s:
        snap = s.get(AgentSnapshot, done["snapshot_id"])
        assert snap.tool == "desk_run" and snap.args["coin"] == "BTC"
        state = snap.result
        assert state["status"] == "valid" and set(state["reports"]) == set(ANALYSTS)
        assert set(state["debate"]) == {*OPENINGS, *REBUTTALS}
        assert state["signal"]["stance"] == "flat" and state["validation"]["ok"] is True
        conv_id = run["conversation_id"]
        tools = s.scalars(select(AgentSnapshot.tool).where(
            AgentSnapshot.conversation_id == conv_id).order_by(AgentSnapshot.id)).all()  # fmt: skip
        assert sorted(tools) == ["desk_run", "get_regime", "get_sentiment"]
        assert tools[-1] == "desk_run"
        msgs = s.scalars(select(Message).where(Message.conversation_id == conv_id)
                         .order_by(Message.id)).all()  # fmt: skip
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert msgs[0].content == "Ask the desk: BTC" and "**flat**" in msgs[1].content
        assert msgs[1].cost is None and msgs[1].tokens_in == 11 * 1000

    # It shows up as a conversation whose answer carries the snapshots.
    detail = api.get(f"/api/agent/conversations/{conv_id}", headers=auth(MEMBER)).json()
    assert "desk_run" in [x["tool"] for x in detail["messages"][1]["snapshots"]]
    opened = api.get(f"/api/agent/snapshots/{done['snapshot_id']}", headers=auth(MEMBER))
    assert opened.status_code == 200 and opened.json()["result"]["coin"] == "BTC"


def test_analysts_and_debaters_run_in_parallel(api, desk) -> None:
    fake = desk(delays={"technical": 0.3, "context": 0.3, "bull_open": 0.3, "bear_open": 0.3})
    r, events = post(api)
    assert events[-1][0] == "done"

    def overlap(a: str, b: str) -> bool:
        (a0, a1), (b0, b1) = fake.windows[a][0], fake.windows[b][0]
        return max(a0, b0) < min(a1, b1)

    assert overlap("technical", "context") and overlap("bull_open", "bear_open")


def _group_tools(*groups: str) -> set[str]:
    return {t.name for t in TOOLS if t.group in groups}


def test_each_analyst_sees_only_its_tool_groups(api, desk) -> None:
    turns = {
        "technical": [ask("get_sentiment", {"days": 3}, call_id="x"), AIMessage("done")],
        "context": [ask("get_calendar", call_id="y"), AIMessage("done")],
    }
    fake = desk(turns=turns)
    _, events = post(api)
    assert set(fake.log["technical"][0][2]) == _group_tools("market", "cycles", "stats")
    assert set(fake.log["context"][0][2]) == _group_tools("context", "views")
    ends = {d["node"]: d for n, d in events if n == "tool_end"}
    assert ends["technical"]["ok"] is False and "Unknown tool" in ends["technical"]["preview"]
    assert ends["context"]["ok"] is True


def test_as_of_is_forced_into_every_tool_call(api, api_sessions, desk) -> None:
    with api_sessions() as s:
        last = s.scalar(select(func.max(CandleDaily.date)).where(CandleDaily.coin == "BTC"))
    as_of = last - dt.timedelta(days=40)
    desk(turns={"technical": [ask("get_regime", {"coin": "BTC", "as_of": last.isoformat()}),
                              AIMessage("done")]})  # fmt: skip
    _, events = post(api, {**BODY, "as_of": as_of.isoformat()})
    run = events[0][1]
    assert run["as_of"] == as_of.isoformat() and run["reference_date"] == as_of.isoformat()
    assert run["title"] == f"Ask the desk: BTC as of {as_of}"
    starts = [d for n, d in events if n == "tool_start"]
    assert starts and all(d["args"]["as_of"] == as_of.isoformat() for d in starts)
    with api_sessions() as s:
        ids = [d["snapshot_id"] for n, d in events if n == "tool_end"]
        dates = [s.get(AgentSnapshot, i).as_of for i in ids]
    assert all(d is not None and d.date() <= as_of for d in dates)


# --- The validator ---------------------------------------------------------------------------


def _signal(**changes: Any) -> DeskSignal:
    return DeskSignal(coin="BTC", **long_signal(100.0, **changes))


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({}, None),
        ({"confidence": 0.97}, "confidence"),
        ({"confidence": 0.45}, "confidence"),
        ({"target": None}, "needs target"),
        ({"entry_low": 99.5, "entry_high": 98.0}, "entry_low 99.5 is above"),
        ({"invalidation": 97.5}, "invalidation 97.5 must be below"),
        ({"target": 98.5}, "target 98.5 must be above"),
        ({"target": 180.0}, "more than 50% away"),
        ({"invalidation": -1.0}, "positive"),
        (
            {
                "stance": "flat",
                **dict.fromkeys(("entry_low", "entry_high", "invalidation", "target")),
            },
            None,
        ),  # fmt: skip
        ({"stance": "flat", "target": 90.0}, None),  # ordering only applies to lean_long
    ],
)
def test_validator_rules(changes: dict, fragment: str | None) -> None:
    errors = validate(_signal(**changes), reference_close=100.0)
    if fragment is None:
        assert errors == []
    else:
        assert any(fragment in e for e in errors), errors


def test_validator_without_a_signal() -> None:
    errors = validate(None, reference_close=100.0, parse_error="the output didn't match")
    assert errors and "No valid signal" in errors[0] and "didn't match" in errors[0]


def test_invalid_signal_is_sent_back_once(api, api_sessions, desk) -> None:
    close = last_close(api_sessions)
    bad, good = long_signal(close, target=close * 0.98), long_signal(close)
    fake = desk(outputs={"head": [bad, good]})
    _, events = post(api)
    assert [d["node"] for n, d in events if n == "node_start"].count("head") == 2
    assert "rejected by the validator" in sent(fake, "head", 1)
    first = next(d for n, d in events if n == "node_end" and d["node"] == "validator")
    assert first["validation"]["ok"] is False and first["validation"]["attempts"] == 1
    final = next(d for n, d in events if n == "signal")
    assert final["validation"] == {"ok": True, "errors": [], "attempts": 2}
    assert final["signal"]["stance"] == "lean_long"
    assert events[-1][1]["status"] == "valid"


def test_signal_invalid_twice_is_reported_not_replaced(api, api_sessions, desk) -> None:
    close = last_close(api_sessions)
    desk(outputs={"head": [long_signal(close, invalidation=None)]})
    _, events = post(api)
    final = next(d for n, d in events if n == "signal")
    assert final["validation"]["ok"] is False and final["validation"]["attempts"] == 2
    assert final["signal"]["stance"] == "lean_long"  # shown with its errors, never made up
    done = events[-1][1]
    assert done["status"] == "invalid"
    with api_sessions() as s:
        answer = s.scalars(select(Message.content).where(Message.role == "assistant")
                           .order_by(Message.id.desc()).limit(1)).one()  # fmt: skip
    assert "validator rejected" in answer


def test_unreadable_head_output_counts_as_invalid(api, desk) -> None:
    desk(outputs={"head": [{"stance": "short", "confidence": 0.7}]})
    _, events = post(api)
    final = next(d for n, d in events if n == "signal")
    assert final["signal"] is None and "schema" in final["validation"]["errors"][0]


def test_unknown_citations_are_flagged(api, desk) -> None:
    desk(outputs={"bear_open": [{"points": [{"text": "Weak.", "cites": ["T1", "T9", "X"]}]}]})
    _, events = post(api)
    bear = next(d for n, d in events if n == "node_end" and d["node"] == "bear_open")
    assert bear["case"]["points"][0]["unknown_cites"] == ["T9", "X"]


# --- Timeouts and failures -------------------------------------------------------------------


def test_a_slow_analyst_is_marked_unavailable_and_the_run_goes_on(api, settings, desk) -> None:
    settings(analyst_timeout_seconds=0.3)
    fake = desk(delays={"technical": 1.0})
    _, events = post(api)
    tech = next(d for n, d in events if n == "node_end" and d["node"] == "technical")
    assert tech["status"] == "unavailable" and "longer than" in tech["report"]["note"]
    assert "technical analyst's report is unavailable" in sent(fake, "head")
    assert events[-1][0] == "done"


def test_a_slow_head_ends_with_a_clean_error_and_saves_the_state(
    api, api_sessions, settings, desk
) -> None:
    settings(node_timeout_seconds=0.3)
    desk(delays={"head": 1.0})
    _, events = post(api)
    head = next(d for n, d in events if n == "node_end" and d["node"] == "head")
    assert head["status"] == "failed" and "longer than" in head["error"]
    name, error = events[-1]
    assert name == "error" and error["code"] == "timeout" and "head" in error["message"]
    with api_sessions() as s:
        state = s.get(AgentSnapshot, error["snapshot_id"]).result
        answer = s.scalars(select(Message.content).where(Message.role == "assistant")
                           .order_by(Message.id.desc()).limit(1)).one()  # fmt: skip
    assert state["status"] == "error" and set(state["debate"]) == {*OPENINGS, *REBUTTALS}
    assert state["signal"] is None and "run stopped" in answer


def test_the_whole_run_has_a_time_limit(api, settings, desk) -> None:
    settings(timeout_seconds=0.5)
    desk(delays={"bull_open": 1.0})
    _, events = post(api)
    assert events[-1][0] == "error" and events[-1][1]["code"] == "timeout"


def test_both_analysts_failing_stops_the_run(api, desk) -> None:
    desk(errors={"technical": RuntimeError("boom"), "context": RuntimeError("boom")})
    _, events = post(api)
    statuses = {d["node"]: d["status"] for n, d in events if n == "node_end"}
    assert statuses["technical"] == statuses["context"] == "unavailable"
    assert events[-1][0] == "error" and "boom" not in events[-1][1]["message"]


# --- Keys, spend, refusals -------------------------------------------------------------------


def test_admin_server_key_records_desk_spend(api, api_sessions, desk) -> None:
    desk()
    _, events = post(api, {"coin": "SOL"}, auth(ADMIN))
    done = events[-1][1]
    assert events[0][1]["server_key"] is True and done["cost_usd"] > 0
    with api_sessions() as s:
        rows = s.scalars(select(LlmSpend).where(LlmSpend.source == "desk")).all()
    assert len(rows) == done["model_calls"]
    assert sum(r.cost for r in rows) == pytest.approx(Decimal(str(done["cost_usd"])))
    assert sum(u["cost_usd"] or 0 for u in done["usage"]) == pytest.approx(done["cost_usd"])


def test_refusals_are_plain_http_errors(api, api_sessions, desk, settings) -> None:
    desk()
    assert post(api, {**BODY, "coin": "DOGE"})[0].status_code == 404
    assert post(api, BODY, auth(MEMBER))[0].status_code == 400  # member without a key
    future = (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=2)).isoformat()
    assert post(api, {**BODY, "as_of": future})[0].status_code == 422
    settings(runs_per_user_per_hour=1)
    assert post(api)[0].status_code == 200
    r, _ = post(api)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    with api_sessions() as s:
        today = dt.datetime.now(dt.UTC).date()
        s.add(LlmSpend(date=today, source="chat", model="claude-haiku-5-5", tokens_in=0,
                       tokens_out=0, cost=Decimal(8)))  # fmt: skip
        s.commit()
    assert post(api, {"coin": "BTC"}, auth(ADMIN))[0].status_code == 402


def test_the_key_never_reaches_storage_or_logs(api, api_sessions, desk, caplog) -> None:
    desk(errors={"bull_open": RuntimeError(f"provider said {CANARY}")})
    with caplog.at_level(logging.DEBUG):
        _, events = post(api)
        _, ok_events = post(api, {"coin": "ETH", "provider": "openrouter"})
    assert CANARY not in str(events) and CANARY not in str(ok_events)
    assert CANARY not in caplog.text
    with api_sessions() as s:
        for col in (cast(AgentSnapshot.result, Text), cast(AgentSnapshot.args, Text)):
            assert not s.scalar(select(func.count()).where(col.contains(CANARY)))
        assert not s.scalar(select(func.count()).where(Message.content.contains(CANARY)))
        assert not s.scalar(select(func.count()).where(Conversation.title.contains(CANARY)))


def test_estimate(api) -> None:
    r = api.get("/api/agent/desk/estimate", params={"provider": "anthropic",
                                                     "model": "claude-haiku-5-5"},
                headers=auth(MEMBER))  # fmt: skip
    body = r.json()["data"]
    assert r.status_code == 200 and body["cost_usd"] > 0 and body["model_calls"] > 7
    assert body["tokens_in"] == sum(n["tokens_in"] for n in body["nodes"])
    r = api.get("/api/agent/desk/estimate", params={"provider": "openrouter"},
                headers=auth(MEMBER))  # fmt: skip
    body = r.json()["data"]
    assert body["model"] == "anthropic/claude-haiku-5.5" and body["cost_usd"] is None
    assert api.get("/api/agent/desk/estimate", headers=auth(MEMBER)).status_code == 400
    server = api.get("/api/agent/desk/estimate", headers=auth(ADMIN)).json()["data"]
    assert server["provider"] == "server" and server["model"] == "claude-haiku-5-5"
