"""Deploy helpers (Stage 2.2): direct-host migrations, Cloud Run env file, smoke test, CORS and
`azp` for the Pages preview origins."""

import json
import os
import uuid

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from desk.api.auth import AuthError, ClerkVerifier
from desk.config import get_settings
from desk.db import normalize_url
from desk.deploy import smoke
from desk.deploy.cloudrun import EnvError, service_env, to_yaml
from desk.deploy.migrate import direct_url, upgrade
from tests import api_fakes

PAGES = "https://crypto-desk.pages.dev"
PREVIEW_REGEX = r"^https://[a-z0-9-]+\.crypto-desk\.pages\.dev$"
PK = "pk_test_dGVzdC1pbnN0YW5jZS5jbGVyay5hY2NvdW50cy5kZXYk"

# --- Migrations over the direct host -----------------------------------------------------------


def test_direct_url_strips_the_neon_pooler_suffix() -> None:
    pooled = (
        "postgresql://u:p%40ss@ep-cool-name-a1b2c3-pooler.us-east-2.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    assert direct_url(pooled) == (
        "postgresql+psycopg://u:p%40ss@ep-cool-name-a1b2c3.us-east-2.aws.neon.tech/neondb"
        "?channel_binding=require&sslmode=require"
    )


def test_direct_url_leaves_other_hosts_alone() -> None:
    assert direct_url("postgresql://desk:desk@localhost:5432/desk") == (
        "postgresql+psycopg://desk:desk@localhost:5432/desk"
    )
    # only the first label, and only as a suffix
    assert "pooler-db.example.com" in direct_url("postgresql://u:p@pooler-db.example.com/d")


@pytest.fixture
def empty_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Postgres test; set TEST_DATABASE_URL (see docker-compose.yml)")
    admin = create_engine(normalize_url(url), isolation_level="AUTOCOMMIT")
    name = f"desk_test_{uuid.uuid4().hex[:8]}"
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield admin.url.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def test_upgrade_migrates_an_empty_database_and_is_idempotent(empty_database: str) -> None:
    before, head = upgrade(empty_database)
    assert before is None and head is not None
    assert upgrade(empty_database) == (head, head)
    engine = create_engine(empty_database)
    try:
        assert {"coins", "candles_daily", "users"} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


# --- Cloud Run env file ------------------------------------------------------------------------


def test_service_env_is_valid_yaml_of_strings() -> None:
    env = service_env(
        cors_origins=[PAGES + "/"],
        cors_origin_regex=PREVIEW_REGEX,
        clerk_publishable_key=PK,
        admin_clerk_ids=["user_abc123"],
    )
    loaded = yaml.safe_load(to_yaml(env))
    assert all(isinstance(v, str) for v in loaded.values())
    assert json.loads(loaded["CORS_ORIGINS"]) == [PAGES]  # trailing slash dropped
    assert loaded["CORS_ORIGIN_REGEX"] == PREVIEW_REGEX
    assert json.loads(loaded["ADMIN_CLERK_IDS"]) == ["user_abc123"]
    assert loaded["APP_ENV"] == "prod"
    # nothing secret ever goes in this file
    assert not {"DATABASE_URL", "CLERK_SECRET_KEY"} & set(loaded)


def test_service_env_without_regex_or_admins() -> None:
    env = service_env(
        cors_origins=[PAGES], cors_origin_regex=None, clerk_publishable_key=PK, admin_clerk_ids=[]
    )
    assert "CORS_ORIGIN_REGEX" not in env
    assert env["ADMIN_CLERK_IDS"] == "[]"


@pytest.mark.parametrize(
    "overrides",
    [
        {"cors_origins": []},
        {"cors_origins": ["http://crypto-desk.pages.dev"]},
        {"cors_origins": ["https://crypto-desk.pages.dev/app"]},
        {"cors_origins": ["*"]},
        {"cors_origin_regex": r"https://.*\.pages\.dev"},  # unanchored
        {"cors_origin_regex": "^https://(unclosed$"},
        {"clerk_publishable_key": "sk_test_abc"},
        {"admin_clerk_ids": ["robert"]},
    ],
)
def test_service_env_rejects_bad_settings(overrides: dict) -> None:
    args = {
        "cors_origins": [PAGES],
        "cors_origin_regex": PREVIEW_REGEX,
        "clerk_publishable_key": PK,
        "admin_clerk_ids": [],
    }
    with pytest.raises(EnvError):
        service_env(**{**args, **overrides})


# --- CORS and azp for preview deployments -----------------------------------------------------


@pytest.fixture
def preview_app(monkeypatch: pytest.MonkeyPatch):
    from desk.api.main import create_app

    monkeypatch.setenv("CORS_ORIGINS", json.dumps([PAGES]))
    monkeypatch.setenv("CORS_ORIGIN_REGEX", PREVIEW_REGEX)
    get_settings.cache_clear()
    try:
        yield TestClient(create_app())
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    ("origin", "allowed"),
    [
        (PAGES, True),
        ("https://3f2a9c1b.crypto-desk.pages.dev", True),
        ("https://feature-x.crypto-desk.pages.dev", True),
        ("https://evil.example", False),
        ("https://crypto-desk.pages.dev.evil.example", False),
        ("https://x.crypto-desk.pages.dev.evil.example", False),
        ("http://3f2a9c1b.crypto-desk.pages.dev", False),
        ("https://other-project.pages.dev", False),
    ],
)
def test_cors_preflight_for_pages_origins(preview_app: TestClient, origin: str, allowed: bool):
    resp = preview_app.options(
        "/api/coins", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )
    assert (resp.headers.get("access-control-allow-origin") == origin) is allowed


def _preview_verifier() -> ClerkVerifier:
    return ClerkVerifier(
        api_fakes.ISSUER,
        [PAGES],
        PREVIEW_REGEX,
        jwks_client=api_fakes.FakeJwks(api_fakes.PRIVATE_KEY.public_key()),
    )


def test_azp_from_a_preview_origin_is_accepted() -> None:
    token = api_fakes.token(api_fakes.MEMBER, azp="https://3f2a9c1b.crypto-desk.pages.dev")
    assert _preview_verifier().verify(token).sub == api_fakes.MEMBER


@pytest.mark.parametrize(
    "azp", ["https://x.crypto-desk.pages.dev.evil.example", "https://evil.example"]
)
def test_azp_outside_the_regex_is_rejected(azp: str) -> None:
    with pytest.raises(AuthError):
        _preview_verifier().verify(api_fakes.token(api_fakes.MEMBER, azp=azp))


# --- Smoke test --------------------------------------------------------------------------------


class FakeApi:
    """The deployed API: health (after `cold` failures), 401 without a token, CORS for PAGES,
    and /api/me + /api/coins for the smoke user's JWT."""

    def __init__(self, cold: int = 0, role: str = "member", open_: bool = False) -> None:
        self.cold, self.role, self.open = cold, role, open_

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/health":
            if self.cold:
                self.cold -= 1
                return httpx.Response(503)
            return httpx.Response(200, json={"status": "ok", "version": "0.1.0"})
        if request.method == "OPTIONS":
            origin = request.headers.get("origin")
            headers = {"access-control-allow-origin": origin} if origin == PAGES else {}
            return httpx.Response(200 if headers else 400, headers=headers)
        if not self.open and request.headers.get("authorization") != "Bearer jwt-smoke":
            return httpx.Response(401)
        if path == "/api/me":
            return httpx.Response(200, json={"clerk_id": "user_smoke", "role": self.role})
        if path == "/api/coins":
            data = [{"symbol": s} for s in ("BTC", "ETH", "SOL")]
            return httpx.Response(200, json={"as_of": None, "sources": [], "data": data})
        return httpx.Response(404)


class FakeClerk:
    def __init__(self, existing: bool = True, session_status: int = 200) -> None:
        self.existing, self.session_status = existing, session_status
        self.calls: list[tuple[str, str]] = []
        self.created_user: dict | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer sk_test_secret"
        path = request.url.path.removeprefix("/v1")
        self.calls.append((request.method, path))
        if request.method == "GET" and path == "/users":
            assert request.url.params["external_id"] == smoke.SMOKE_EXTERNAL_ID
            return httpx.Response(200, json=[{"id": "user_smoke"}] if self.existing else [])
        if path == "/users":
            self.created_user = json.loads(request.content)
            return httpx.Response(200, json={"id": "user_smoke"})
        if path == "/sessions":
            if self.session_status != 200:
                body = {"errors": [{"code": "operation_not_allowed", "message": "x sk_test"}]}
                return httpx.Response(self.session_status, json=body)
            return httpx.Response(200, json={"id": "sess_1"})
        if path == "/sessions/sess_1/tokens":
            assert json.loads(request.content) == {"expires_in_seconds": smoke.TOKEN_SECONDS}
            return httpx.Response(200, json={"object": "token", "jwt": "jwt-smoke"})
        if path == "/sessions/sess_1/revoke":
            return httpx.Response(200, json={"id": "sess_1", "status": "revoked"})
        return httpx.Response(404)


def _run(api: FakeApi, clerk: FakeClerk | None = None, **kwargs) -> list[str]:
    return smoke.run(
        "https://desk-api.example.run.app/",
        transport=httpx.MockTransport(api),
        clerk_transport=httpx.MockTransport(clerk or FakeClerk()),
        sleep=lambda _: None,
        **kwargs,
    )


def test_smoke_happy_path_and_session_is_revoked() -> None:
    clerk = FakeClerk()
    report = _run(FakeApi(cold=2), clerk, origin=PAGES, clerk_secret_key="sk_test_secret")
    assert report[0].startswith("health ok")
    assert any("CORS allows" in line for line in report)
    assert report[-1].endswith("coins BTC, ETH, SOL")
    assert clerk.calls[-1] == ("POST", "/sessions/sess_1/revoke")
    assert not any("jwt-smoke" in line or "sk_test_secret" in line for line in report)


def test_smoke_creates_the_test_user_once() -> None:
    clerk = FakeClerk(existing=False)
    _run(FakeApi(), clerk, clerk_secret_key="sk_test_secret")
    assert clerk.created_user == {
        "external_id": "desk-smoke",
        "email_address": ["desk-smoke+clerk_test@example.com"],
        "skip_password_requirement": True,
    }


def test_smoke_fails_if_the_smoke_user_is_not_a_plain_member() -> None:
    clerk = FakeClerk()
    with pytest.raises(smoke.SmokeError, match="must be a member"):
        _run(FakeApi(role="admin"), clerk, clerk_secret_key="sk_test_secret")
    assert clerk.calls[-1] == ("POST", "/sessions/sess_1/revoke")  # revoked even on failure


def test_smoke_reports_clerk_errors_without_secrets() -> None:
    with pytest.raises(smoke.SmokeError) as e:
        _run(FakeApi(), FakeClerk(session_status=403), clerk_secret_key="sk_test_secret")
    assert "operation_not_allowed" in str(e.value) and "sk_test" not in str(e.value)


def test_smoke_fails_when_health_never_comes_up() -> None:
    with pytest.raises(smoke.SmokeError, match="never answered"):
        _run(FakeApi(cold=100))


def test_smoke_fails_when_auth_is_not_enforced() -> None:
    with pytest.raises(smoke.SmokeError, match="expected 401"):
        _run(FakeApi(open_=True))


def test_smoke_fails_on_a_cors_mismatch() -> None:
    with pytest.raises(smoke.SmokeError, match="CORS preflight"):
        _run(FakeApi(), origin="https://not-allowed.pages.dev")


@pytest.mark.parametrize(
    ("secret", "warning"), [(None, "no Clerk secret"), ("sk_live_abc", "production Clerk")]
)
def test_smoke_skips_the_authenticated_call(secret: str | None, warning: str) -> None:
    clerk = FakeClerk()
    report = _run(FakeApi(), clerk, clerk_secret_key=secret)
    assert warning in report[-1] and not clerk.calls
