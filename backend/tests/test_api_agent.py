"""`/api/agent/models` and `/api/agent/test-key` (Stage 3.4). Providers are mocked; the live
behavior they mirror is recorded in D42."""

import json

import httpx
import pytest

from desk.agents.keycheck import check_key
from desk.api.main import app
from desk.api.routes import agent
from tests.api_fakes import CANARY, MEMBER, auth, provider_transport

H = {**auth(MEMBER), "X-LLM-Key": CANARY}


@pytest.fixture
def provider(api):
    """Swap the provider transport per test: `provider(status)` returns the request log."""

    def use(status: int = 200) -> list[httpx.Request]:
        transport = provider_transport(status)
        app.dependency_overrides[agent.provider_client] = lambda: httpx.Client(transport=transport)
        return transport.seen

    return use


def test_models_lists_providers_with_openrouter_recommended(api) -> None:
    out = api.get("/api/agent/models", headers=auth(MEMBER)).json()["data"]
    assert [p["id"] for p in out] == ["openrouter", "anthropic", "openai"]
    openrouter = out[0]
    assert openrouter["recommended"] and openrouter["default"] == "anthropic/claude-haiku-5.5"
    assert openrouter["default"] in openrouter["choices"]
    assert out[2]["default"] is None and out[2]["choices"] == []


@pytest.mark.parametrize(
    ("provider_id", "url", "header", "value"),
    [
        ("openrouter", "https://openrouter.ai/api/v1/chat/completions", "authorization",
         f"Bearer {CANARY}"),
        ("anthropic", "https://api.anthropic.com/v1/messages", "x-api-key", CANARY),
    ],
)  # fmt: skip
def test_key_test_makes_one_one_token_call(api, provider, provider_id, url, header, value) -> None:
    seen = provider(200)
    r = api.post("/api/agent/test-key", json={"provider": provider_id}, headers=H)
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] and out["model"] and out["message"].startswith("The key works")
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == url and request.method == "POST"
    assert request.headers[header] == value
    body = json.loads(request.content)
    assert body["max_tokens"] == 1 and body["model"] == out["model"]
    if provider_id == "anthropic":
        assert request.headers["anthropic-version"] == "2023-06-01"


def test_openai_key_test_lists_models_for_free(api, provider) -> None:
    seen = provider(200)
    out = api.post("/api/agent/test-key", json={"provider": "openai"}, headers=H).json()
    assert out["ok"] and out["model"] is None
    assert seen[0].method == "GET" and str(seen[0].url) == "https://api.openai.com/v1/models"


@pytest.mark.parametrize(
    ("status", "text"),
    [(401, "rejected"), (402, "no credit"), (404, "wasn't found"), (429, "Rate limited"),
     (400, "refused"), (503, "error (503)")],
)  # fmt: skip
def test_key_test_explains_failures_in_its_own_words(api, provider, status, text) -> None:
    provider(status)
    body = {"provider": "openrouter", "model": "openai/gpt-5-nano"}
    out = api.post("/api/agent/test-key", json=body, headers=H).json()
    assert not out["ok"] and text in out["message"]
    assert "echo" not in out["message"]  # the provider's own text is never passed on


def test_key_test_needs_a_key_and_a_sane_model(api, provider) -> None:
    seen = provider(200)
    r = api.post("/api/agent/test-key", json={"provider": "openrouter"}, headers=auth(MEMBER))
    assert r.status_code == 400
    bad = {"provider": "openrouter", "model": "https://evil.example/x?y"}
    assert api.post("/api/agent/test-key", json=bad, headers=H).status_code == 422
    assert api.post("/api/agent/test-key", json={"provider": "x"}, headers=H).status_code == 422
    assert seen == []


def test_network_errors_and_redirects_do_not_leak() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with httpx.Client(transport=httpx.MockTransport(boom)) as client:
        out = check_key(client, "anthropic", CANARY, "claude-haiku-5-5")
    assert not out.ok and "reach" in out.message

    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(307, headers={"location": "https://evil.example/"})

    with httpx.Client(transport=httpx.MockTransport(redirect), follow_redirects=False) as client:
        out = check_key(client, "openrouter", CANARY, "anthropic/claude-haiku-5.5")
    assert not out.ok and "307" in out.message


def test_the_route_client_never_follows_redirects() -> None:
    gen = agent.provider_client()
    client = next(gen)
    assert client.follow_redirects is False
    gen.close()
