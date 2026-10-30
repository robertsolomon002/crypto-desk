"""Clerk token verification, user upsert, admin promotion, rate limit (Stage 2.1)."""

import base64
import time

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from desk.api import deps
from desk.api.auth import AuthError, bearer_token
from desk.config import get_settings, issuer_from_publishable_key
from desk.models import User
from tests import api_fakes
from tests.api_fakes import ADMIN, MEMBER, OTHER_KEY, auth, token

# --- Verifier (no database) -------------------------------------------------------------------


def test_valid_token() -> None:
    claims = api_fakes.verifier().verify(token(MEMBER))
    assert claims.sub == MEMBER


@pytest.mark.parametrize(
    "bad",
    [
        {"exp": int(time.time()) - 60},  # expired beyond the 5 s leeway
        {"nbf": int(time.time()) + 60},  # not yet valid
        {"iss": "https://evil.clerk.accounts.dev"},
        {"azp": "https://evil.example"},
        {"sts": "pending"},
        {"sub": None},
    ],
)
def test_rejected_claims(bad) -> None:
    with pytest.raises(AuthError):
        api_fakes.verifier().verify(token(MEMBER, **bad))


def test_missing_azp_is_allowed() -> None:
    assert api_fakes.verifier().verify(token(MEMBER, azp=None)).sub == MEMBER


def test_wrong_signing_key_and_garbage() -> None:
    v = api_fakes.verifier()
    with pytest.raises(AuthError):
        v.verify(token(MEMBER, key=OTHER_KEY))
    with pytest.raises(AuthError):
        v.verify("not.a.jwt")


def test_hs256_token_is_rejected() -> None:
    import jwt

    forged = jwt.encode({"iss": api_fakes.ISSUER, "sub": MEMBER, "exp": time.time() + 60,
                         "iat": time.time()}, "s" * 32, algorithm="HS256",
                        headers={"kid": api_fakes.KID})  # fmt: skip
    with pytest.raises(AuthError):
        api_fakes.verifier().verify(forged)


def test_auth_error_never_contains_the_token() -> None:
    t = token(MEMBER, key=OTHER_KEY)
    with pytest.raises(AuthError) as e:
        api_fakes.verifier().verify(t)
    assert t not in str(e.value)


@pytest.mark.parametrize("header", [None, "", "Basic abc", "Bearer ", "Bearer"])
def test_bearer_token_parsing(header) -> None:
    with pytest.raises(AuthError):
        bearer_token(header)
    assert bearer_token("Bearer abc") == "abc"


def test_issuer_from_publishable_key() -> None:
    key = "pk_test_" + base64.b64encode(b"example.accounts.dev$").decode().rstrip("=")
    assert issuer_from_publishable_key(key) == "https://example.accounts.dev"
    assert issuer_from_publishable_key("pk_test_ZXhhbXBsZS5hY2NvdW50cy5kZXYk") == (
        "https://example.accounts.dev"
    )  # Clerk's documented example
    for bad in ("sk_test_abc", "pk_test_", "pk_prod_ZXhhbXBsZS5hY2NvdW50cy5kZXYk", "pk_test_!!"):
        with pytest.raises(ValueError):
            issuer_from_publishable_key(bad)


def test_rate_limiter_sliding_window() -> None:
    now = [1000.0]
    limiter = deps.RateLimiter(2, clock=lambda: now[0])
    limiter.check("u")
    limiter.check("u")
    with pytest.raises(HTTPException) as e:
        limiter.check("u")
    assert e.value.status_code == 429
    assert int(e.value.headers["Retry-After"]) >= 1
    limiter.check("other")  # per key
    now[0] += 61
    limiter.check("u")


# --- Through the app (Postgres) ---------------------------------------------------------------


def test_anonymous_and_bad_tokens_get_401(api) -> None:
    assert api.get("/api/me").status_code == 401
    r = api.get("/api/me", headers={"Authorization": "Bearer junk"})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert api.get("/api/me", headers=auth(MEMBER, exp=int(time.time()) - 60)).status_code == 401


def test_health_needs_no_auth(api) -> None:
    assert api.get("/api/health").status_code == 200


def test_first_request_creates_a_member_once(api, api_sessions) -> None:
    for _ in range(3):
        r = api.get("/api/me", headers=auth("user_new"))
        assert (r.json()["clerk_id"], r.json()["role"]) == ("user_new", "member")
    deps._user_cache.clear()
    api.get("/api/me", headers=auth("user_new"))
    with api_sessions() as s:
        assert len(s.scalars(select(User).where(User.clerk_id == "user_new")).all()) == 1


def test_admin_clerk_ids_promote(api, api_sessions, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_CLERK_IDS", '["user_boss"]')
    get_settings.cache_clear()
    try:
        assert api.get("/api/me", headers=auth("user_boss")).json()["role"] == "admin"
        with api_sessions.begin() as s:  # demoted in the DB: promoted again on the next login
            s.scalar(select(User).where(User.clerk_id == "user_boss")).role = "member"
        deps._user_cache.clear()
        assert api.get("/api/me", headers=auth("user_boss")).json()["role"] == "admin"
    finally:
        get_settings.cache_clear()


def test_seeded_admin(api) -> None:
    assert api.get("/api/me", headers=auth(ADMIN)).json()["role"] == "admin"


def test_rate_limit_through_the_app(api, monkeypatch) -> None:
    limiter = deps.RateLimiter(3)
    monkeypatch.setattr(deps, "rate_limiter", lambda: limiter)
    codes = [api.get("/api/me", headers=auth(MEMBER)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = api.get("/api/me", headers=auth(MEMBER))
    assert "retry-after" in r.headers
    assert api.get("/api/me", headers=auth(ADMIN)).status_code == 200  # per user
