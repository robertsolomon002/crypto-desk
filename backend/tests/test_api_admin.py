"""Admin routes: watchlist, Clerk invites (mocked), users and roles (Stage 2.1)."""

import json

import httpx
import pytest
import respx

from desk.api.main import app
from desk.api.routes import admin
from tests.api_fakes import ADMIN, MEMBER, auth

CLERK = "https://api.clerk.com/v1"
INVITE = {
    "id": "inv_2abc",
    "object": "invitation",
    "email_address": "friend@example.com",
    "status": "pending",
    "created_at": 1761696000000,
    "updated_at": 1761696000000,
}
H = auth(ADMIN)


@pytest.fixture
def clerk(api):
    def client():
        with httpx.Client(base_url=CLERK, headers={"Authorization": "Bearer sk_test_x"}) as c:
            yield c

    app.dependency_overrides[admin.clerk_client] = client
    with respx.mock(base_url=CLERK) as mock:
        yield mock


# --- Watchlist --------------------------------------------------------------------------------


def test_watchlist_add_remove_readd(api) -> None:
    r = api.post("/api/admin/watchlist", json={"symbol": "LINK", "name": "Chainlink",
                                               "aliases": ["chainlink"]}, headers=H)  # fmt: skip
    assert r.status_code == 201
    assert r.json()["source_market"] == "LINK/USD"
    assert "LINK" in [c["symbol"] for c in api.get("/api/coins", headers=H).json()["data"]]
    assert api.delete("/api/admin/watchlist/LINK", headers=H).status_code == 204
    assert api.get("/api/admin/watchlist", headers=H).json() == []
    assert "LINK" not in [c["symbol"] for c in api.get("/api/coins", headers=H).json()["data"]]
    r = api.post("/api/admin/watchlist", json={"symbol": "LINK", "name": "Chainlink"}, headers=H)
    assert r.status_code == 201 and r.json()["active"]


def test_watchlist_rules(api, monkeypatch) -> None:
    def add(symbol: str) -> int:
        body = {"symbol": symbol, "name": symbol}
        return api.post("/api/admin/watchlist", json=body, headers=H).status_code

    assert add("BTC") == 409  # core coin
    assert add("link") == 422  # symbols are upper case
    assert add("A/B") == 422
    assert api.delete("/api/admin/watchlist/BTC", headers=H).status_code == 404
    monkeypatch.setattr(admin, "max_watchlist", lambda: 2)
    assert [add("AAA"), add("BBB"), add("CCC")] == [201, 201, 409]


# --- Invites ----------------------------------------------------------------------------------


def test_invites_proxy_to_clerk(api, clerk) -> None:
    listed = clerk.get("/invitations").respond(json=[INVITE])
    created = clerk.post("/invitations").respond(json=INVITE)
    revoked = clerk.post("/invitations/inv_2abc/revoke").respond(
        json={**INVITE, "status": "revoked"}
    )
    out = api.get("/api/admin/invites?status=pending", headers=H).json()
    assert out[0]["email_address"] == "friend@example.com"
    assert out[0]["created_at"].startswith("2025-10-29")  # milliseconds since the epoch
    assert listed.calls.last.request.url.params["status"] == "pending"

    body = {"email": "friend@example.com", "redirect_url": "https://desk.example"}
    r = api.post("/api/admin/invites", json=body, headers=H)
    assert r.status_code == 201
    sent = json.loads(created.calls.last.request.content)
    assert sent == {"email_address": "friend@example.com", "notify": True,
                    "redirect_url": "https://desk.example"}  # fmt: skip
    assert created.calls.last.request.headers["authorization"] == "Bearer sk_test_x"

    assert api.delete("/api/admin/invites/inv_2abc", headers=H).json()["status"] == "revoked"
    assert revoked.called


def test_invite_list_paginated_shape(api, clerk) -> None:
    clerk.get("/invitations").respond(json={"data": [INVITE], "total_count": 1})
    assert len(api.get("/api/admin/invites", headers=H).json()) == 1


def test_invite_errors(api, clerk) -> None:
    clerk.post("/invitations").respond(
        422, json={"errors": [{"code": "duplicate_record", "message": "duplicate",
                               "long_message": "That email address is already invited."}]},
    )  # fmt: skip
    r = api.post("/api/admin/invites", json={"email": "friend@example.com"}, headers=H)
    assert r.status_code == 422
    assert r.json()["detail"] == "That email address is already invited."
    clerk.get("/invitations").mock(side_effect=httpx.ConnectError("down"))
    assert api.get("/api/admin/invites", headers=H).status_code == 502


def test_invite_input_validation(api, clerk) -> None:
    assert api.post("/api/admin/invites", json={"email": "nope"}, headers=H).status_code == 422
    bad = {"email": "a@b.co", "redirect_url": "javascript:alert(1)"}
    assert api.post("/api/admin/invites", json=bad, headers=H).status_code == 422
    assert api.delete("/api/admin/invites/..%2Fusers", headers=H).status_code in (404, 422)
    assert not clerk.calls


def test_invites_need_the_secret_key(api, monkeypatch) -> None:
    from desk.config import get_settings

    monkeypatch.setattr(get_settings(), "clerk_secret_key", None)
    assert api.get("/api/admin/invites", headers=H).status_code == 503


# --- Users ------------------------------------------------------------------------------------


def test_role_changes(api) -> None:
    api.get("/api/me", headers=auth(MEMBER))
    users = {u["clerk_id"]: u for u in api.get("/api/admin/users", headers=H).json()}
    member_id, admin_id = users[MEMBER]["id"], users[ADMIN]["id"]
    r = api.patch(f"/api/admin/users/{member_id}", json={"role": "admin"}, headers=H)
    assert r.json()["role"] == "admin"
    # The change applies at once (the user cache is dropped).
    assert api.get("/api/admin/users", headers=auth(MEMBER)).status_code == 200
    api.patch(f"/api/admin/users/{member_id}", json={"role": "member"}, headers=H)
    assert api.get("/api/admin/users", headers=auth(MEMBER)).status_code == 403
    r = api.patch(f"/api/admin/users/{admin_id}", json={"role": "member"}, headers=H)
    assert r.status_code == 409  # the last admin stays
    assert api.patch("/api/admin/users/999", json={"role": "admin"}, headers=H).status_code == 404
    bad = api.patch(f"/api/admin/users/{member_id}", json={"role": "owner"}, headers=H)
    assert bad.status_code == 422
