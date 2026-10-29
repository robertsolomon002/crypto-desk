"""The canary test (Section 9): a user's `X-LLM-Key` never reaches logs, responses or the
database (Stage 2.1). Later stages extend it to LangSmith traces and the agent routes."""

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
    from fastapi.testclient import TestClient

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
        client.options(
            "/api/me",
            headers={
                **key,
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        ),  # fmt: skip
    ]
    assert [r.status_code for r in responses] == [200, 401, 404, 422, 403, 200, 500, 200, 200]
    echoed = responses[5].json()
    assert "x-llm-key" not in echoed["headers"]
    assert echoed["key"] == "**********"  # SecretStr

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
