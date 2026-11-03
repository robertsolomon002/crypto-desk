"""The canary test (Section 9): a user's `X-LLM-Key` never reaches logs, responses or the
database (Stage 2.1). Later stages extend it to LangSmith traces and the agent routes."""

import json
import logging

import pytest
from fastapi import APIRouter, Request
from sqlalchemy import text

from desk.api.main import app
from desk.api.middleware import REDACTED, LlmKeyRedaction
from tests.api_fakes import CANARY, MEMBER, auth

LOGGERS = ["", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "httpx", "sqlalchemy"]


@pytest.fixture
def probe_routes():
    """Routes that log the request and its headers carelessly, and one that crashes."""
    router = APIRouter()
    log = logging.getLogger("desk.test.careless")

    @router.get("/api/_test/echo-headers")
    def echo(request: Request) -> dict:
        log.warning("headers: %s", dict(request.headers))
        log.warning("state key repr: %r", request.state.llm_key)
        return {"headers": dict(request.headers), "key": str(request.state.llm_key)}

    @router.get("/api/_test/crash")
    def crash(request: Request) -> dict:
        raise RuntimeError(f"boom with headers {dict(request.headers)}")

    @router.get("/api/_test/log-raw")
    def log_raw(request: Request) -> dict:
        key = request.state.llm_key.get_secret_value()  # what the agent will do in 5.1
        logging.getLogger("desk.test.careless").error("calling the model with key %s", key)
        logging.getLogger("desk.test.careless").error(f"f-string key {key}")
        return {"ok": True}

    before = list(app.router.routes)
    app.include_router(router)
    app.openapi_schema = None
    yield
    app.router.routes[:] = before
    app.openapi_schema = None


def test_canary_never_leaks(api, api_sessions, probe_routes, caplog) -> None:
    import httpx
    from fastapi.testclient import TestClient

    from desk.api.routes import agent
    from tests.api_fakes import provider_transport

    transport = provider_transport(401)
    app.dependency_overrides[agent.provider_client] = lambda: httpx.Client(transport=transport)

    client = TestClient(app, raise_server_exceptions=False)
    for name in LOGGERS:  # caplog restores each level after the test
        caplog.set_level(logging.DEBUG, logger=name)
    key = {"X-LLM-Key": CANARY}
    responses = [
        client.get("/api/me", headers={**auth(MEMBER), **key}),
        client.get("/api/me", headers=key),  # 401
        client.get("/api/ohlcv/NOPE", headers={**auth(MEMBER), **key}),  # 404
        client.get("/api/indicators/BTC?sma=1", headers={**auth(MEMBER), **key}),  # 422
        client.get("/api/admin/users", headers={**auth(MEMBER), **key}),  # 403
        client.get("/api/_test/echo-headers", headers=key),
        client.get("/api/_test/crash", headers=key),  # 500
        client.get("/api/_test/log-raw", headers=key),
        # The Settings key test sends the key on to the (faked) provider, whose error body
        # echoes the request headers, as OpenAI's 401 does with part of the key.
        client.post(
            "/api/agent/test-key", json={"provider": "openai"}, headers={**auth(MEMBER), **key}
        ),  # fmt: skip
        client.options(
            "/api/me",
            headers={
                **key,
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        ),  # fmt: skip
    ]
    assert [r.status_code for r in responses] == [200, 401, 404, 422, 403, 200, 500, 200, 200,
                                                  200]  # fmt: skip
    echoed = responses[5].json()
    assert "x-llm-key" not in echoed["headers"]
    assert echoed["key"] == "**********"  # SecretStr

    assert transport.seen[0].headers["authorization"] == f"Bearer {CANARY}"  # it did go out
    assert responses[8].json()["ok"] is False
    for r in responses:
        assert CANARY not in r.text
        assert CANARY not in str(r.headers)
    logged = "\n".join(
        f"{rec.getMessage()} {rec.exc_text or ''} {rec.args!r}" for rec in caplog.records
    )
    assert "calling the model with key" in logged and REDACTED in logged
    assert CANARY not in logged
    assert CANARY not in caplog.text

    with api_sessions() as s:
        for table in s.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )).scalars():  # fmt: skip
            hit = s.execute(text(f'SELECT count(*) FROM "{table}" t WHERE t::text LIKE :c'),
                            {"c": f"%{CANARY}%"}).scalar()  # fmt: skip
            assert hit == 0, table


async def test_middleware_strips_the_header_for_every_layer() -> None:
    seen = {}

    async def inner(scope, receive, send):
        seen.update(scope)

    mw = LlmKeyRedaction(inner)
    scope = {"type": "http", "headers": [(b"x-llm-key", CANARY.encode()), (b"a", b"b")]}
    await mw(scope, None, None)
    assert seen["headers"] == [(b"a", b"b")]
    assert seen["state"]["llm_key"].get_secret_value() == CANARY
    assert CANARY not in repr(seen)


# --- Stage 5.1: the agent chat and LangSmith traces ------------------------------------------


def _openrouter_transport(status: int = 200):
    """OpenRouter's Chat Completions stream: a tool call first, then an answer. A 401 echoes
    the request headers, as OpenAI does with part of the key."""
    import httpx

    seen: list = []

    def chunk(delta: dict, finish=None, usage=None) -> str:
        body = {"id": "gen-1", "object": "chat.completion.chunk", "created": 1,
                "model": "anthropic/claude-haiku-5.5",
                "choices": [] if usage else [{"index": 0, "delta": delta,
                                              "finish_reason": finish}]}  # fmt: skip
        if usage:
            body["usage"] = usage
        return "data: " + json.dumps(body) + "\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": f"bad {request.headers}"}})
        usage = {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55}
        if len(seen) == 1:
            call = {"index": 0, "id": "call_1", "type": "function",
                    "function": {"name": "list_coins", "arguments": "{}"}}  # fmt: skip
            parts = [chunk({"role": "assistant", "tool_calls": [call]}),
                     chunk({}, "tool_calls"), chunk({}, usage=usage)]  # fmt: skip
        else:
            parts = [chunk({"role": "assistant", "content": "Three coins "}),
                     chunk({"content": "(list_coins)."}), chunk({}, "stop"),
                     chunk({}, usage=usage)]  # fmt: skip
        body = "".join(parts) + "data: [DONE]\n\n"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    transport.seen = seen  # type: ignore[attr-defined]
    return transport


def _scan_db(api_sessions) -> None:
    with api_sessions() as s:
        for table in s.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )).scalars():  # fmt: skip
            hit = s.execute(text(f'SELECT count(*) FROM "{table}" t WHERE t::text LIKE :c'),
                            {"c": f"%{CANARY}%"}).scalar()  # fmt: skip
            assert hit == 0, table


@pytest.mark.parametrize("status", [200, 401])
def test_canary_never_leaks_through_chat(
    api, real_llm, api_sessions, monkeypatch, caplog, status
) -> None:
    """A real `ChatOpenAI` on OpenRouter's URL (HTTP mocked) with the canary key: the key goes
    out to the provider and nowhere else: not the SSE stream, logs or any database row."""
    import functools

    import httpx
    from langchain_openai import ChatOpenAI

    from desk.agents import llm
    from tests.agent_fakes import sse

    transport = _openrouter_transport(status)
    monkeypatch.setattr(llm, "ChatOpenAI", functools.partial(
        ChatOpenAI, http_async_client=httpx.AsyncClient(transport=transport)))  # fmt: skip
    for name in LOGGERS:
        caplog.set_level(logging.DEBUG, logger=name)
    body = {"message": "Which coins do you track?", "provider": "openrouter"}
    r = api.post("/api/agent/chat", json=body, headers={**auth(MEMBER), "X-LLM-Key": CANARY})
    assert r.status_code == 200
    events = sse(r.text)
    assert transport.seen[0].headers["authorization"] == f"Bearer {CANARY}"  # it did go out
    assert str(transport.seen[0].url) == "https://openrouter.ai/api/v1/chat/completions"
    if status == 200:
        assert [e[0] for e in events if e[0] != "token"] == ["conversation", "tool_start",
                                                             "tool_end", "done"]  # fmt: skip
        sent = json.loads(transport.seen[1].content)
        assert sent["messages"][-1]["role"] == "tool" and "BTC" in sent["messages"][-1]["content"]
        assert sent["stream_options"] == {"include_usage": True}
        assert events[-1][1]["tokens_in"] == 100
    else:
        assert events[-1] == ("error", {"code": "provider", "message":
                                        "Your key was rejected by the provider. Check it in "
                                        "Settings."})  # fmt: skip
    assert CANARY not in r.text and CANARY not in str(r.headers)
    assert CANARY not in caplog.text
    assert all(CANARY not in f"{rec.getMessage()} {rec.args!r}" for rec in caplog.records)
    _scan_db(api_sessions)


class _CaptureSession:
    """Stands in for LangSmith's `requests.Session`: keeps every body it would have posted."""

    def __init__(self) -> None:
        self.bodies: list[str] = []
        self.headers: dict = {}

    def request(self, method, url, *args, **kwargs):
        import requests

        data = kwargs.get("data", kwargs.get("json"))
        if hasattr(data, "read"):
            data = data.read()
        self.bodies.append(data.decode("utf-8", "replace") if isinstance(data, bytes)
                           else str(data))  # fmt: skip
        r = requests.Response()
        r.status_code, r._content, r.url = 200, b"{}", url
        return r

    def mount(self, *args, **kwargs) -> None:
        pass

    def close(self) -> None:
        pass


def test_canary_never_reaches_langsmith(api, api_sessions, monkeypatch) -> None:
    """Server-key runs are traced through `ScrubbingClient`; a secret that leaks into what the
    tracer serializes (here a model field holding it) is redacted. Key runs aren't traced."""
    from langchain_core.messages import AIMessage
    from langchain_core.tracers.langchain import wait_for_all_tracers
    from pydantic import SecretStr

    from desk.agents import llm, tracing
    from tests.agent_fakes import ScriptedModel, ask, sse
    from tests.api_fakes import ADMIN

    class LeakyModel(ScriptedModel):
        """Reports the key in its invocation params, which the tracer records, the way an
        integration would with a key in its base URL."""

        api_key: SecretStr = SecretStr(CANARY)

        @property
        def _identifying_params(self) -> dict:
            return {"endpoint": f"https://x.test/?key={CANARY}", "api_key": CANARY}

    session = _CaptureSession()
    client = tracing.ScrubbingClient(api_key="lsv2_test", api_url="https://ls.test",
                                     session=session, auto_batch_tracing=False)  # fmt: skip
    monkeypatch.setattr(tracing, "tracing_enabled", lambda: True)
    monkeypatch.setattr(tracing, "trace_client", lambda: client)
    monkeypatch.setattr(tracing, "server_secrets", lambda: [CANARY])
    leaky = LeakyModel(script=[ask("list_coins"), AIMessage("Three coins.")])
    monkeypatch.setattr(llm, "make_chat_model", lambda choice, key: leaky)

    r = api.post("/api/agent/chat", json={"message": "Which coins?"}, headers=auth(ADMIN))
    assert sse(r.text)[-1][0] == "done"
    wait_for_all_tracers()
    traced = "\n".join(session.bodies)
    assert len(session.bodies) >= 4 and "Which coins?" in traced  # it was traced
    assert CANARY not in traced and REDACTED in traced

    # A user's key run is never traced, even with tracing on.
    session.bodies.clear()
    body = {"message": "Which coins?", "provider": "openrouter"}
    r = api.post("/api/agent/chat", json=body, headers={**auth(MEMBER), "X-LLM-Key": CANARY})
    assert sse(r.text)[-1][0] == "done"
    wait_for_all_tracers()
    assert session.bodies == []
    _scan_db(api_sessions)
