"""Post-deploy smoke test: health, auth enforced, CORS, then one authenticated call (D38).

The authenticated call uses a dedicated Clerk test user (external id `desk-smoke`), created on
first use through the Backend API. Its session comes from `POST /v1/sessions`, which Clerk's spec
marks "intended only for use in testing, and is not available for production instances", so with
an `sk_live_` key that part is skipped with a warning. The session is revoked at the end. The user
gets an ordinary `member` row in `users`; the smoke test fails if it is ever anything else.

Messages never contain the token or the Clerk secret.
"""

import time
from collections.abc import Callable

import httpx

CLERK_API = "https://api.clerk.com/v1"
SMOKE_EXTERNAL_ID = "desk-smoke"
# `+clerk_test` addresses are Clerk's test addresses: no real email is ever sent
SMOKE_EMAIL = "desk-smoke+clerk_test@example.com"
TOKEN_SECONDS = 120


class SmokeError(Exception):
    pass


def _clerk_error(resp: httpx.Response, what: str) -> SmokeError:
    try:
        codes = [e.get("code") for e in resp.json().get("errors", [])]
    except ValueError:
        codes = []
    return SmokeError(f"Clerk {what}: HTTP {resp.status_code} {codes}")


def wait_for_health(
    client: httpx.Client, attempts: int = 12, wait: float = 5.0, sleep: Callable = time.sleep
) -> dict:
    """Retry through a cold start (Section 9 allows a few seconds)."""
    last = "no response"
    for i in range(attempts):
        try:
            resp = client.get("/api/health")
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                return resp.json()
            last = f"HTTP {resp.status_code}"
        except httpx.HTTPError as e:
            last = type(e).__name__
        if i < attempts - 1:
            sleep(wait)
    raise SmokeError(f"/api/health never answered ok ({last})")


def check_auth_required(client: httpx.Client) -> None:
    resp = client.get("/api/coins")
    if resp.status_code != 401:
        raise SmokeError(f"/api/coins without a token: expected 401, got {resp.status_code}")


def check_cors(client: httpx.Client, origin: str) -> None:
    headers = {"Origin": origin, "Access-Control-Request-Method": "GET"}
    resp = client.options("/api/coins", headers=headers)
    allowed = resp.headers.get("access-control-allow-origin")
    if resp.status_code != 200 or allowed != origin:
        raise SmokeError(f"CORS preflight from {origin}: HTTP {resp.status_code}, {allowed!r}")
    evil = {**headers, "Origin": "https://evil.example"}
    if client.options("/api/coins", headers=evil).headers.get("access-control-allow-origin"):
        raise SmokeError("CORS allows https://evil.example")


def smoke_user_session(clerk: httpx.Client) -> tuple[str, str]:
    """Find or create the smoke user, open a session, return (session id, session JWT)."""
    resp = clerk.get("/users", params={"external_id": SMOKE_EXTERNAL_ID})
    if resp.status_code != 200:
        raise _clerk_error(resp, "list users")
    users = resp.json()
    users = users.get("data", []) if isinstance(users, dict) else users
    if users:
        user_id = users[0]["id"]
    else:
        body = {
            "external_id": SMOKE_EXTERNAL_ID,
            "email_address": [SMOKE_EMAIL],
            "skip_password_requirement": True,
        }
        resp = clerk.post("/users", json=body)
        if resp.status_code != 200:
            raise _clerk_error(resp, "create smoke user")
        user_id = resp.json()["id"]
    resp = clerk.post("/sessions", json={"user_id": user_id})
    if resp.status_code != 200:
        raise _clerk_error(resp, "create session")
    session_id = resp.json()["id"]
    resp = clerk.post(f"/sessions/{session_id}/tokens", json={"expires_in_seconds": TOKEN_SECONDS})
    if resp.status_code != 200:
        revoke(clerk, session_id)
        raise _clerk_error(resp, "create session token")
    return session_id, resp.json()["jwt"]


def revoke(clerk: httpx.Client, session_id: str) -> None:
    clerk.post(f"/sessions/{session_id}/revoke")


def check_authenticated(client: httpx.Client, jwt: str) -> str:
    auth = {"Authorization": f"Bearer {jwt}"}
    me = client.get("/api/me", headers=auth)
    if me.status_code != 200:
        raise SmokeError(f"/api/me with the smoke user's token: HTTP {me.status_code}")
    if me.json().get("role") != "member":
        raise SmokeError(f"the smoke user must be a member, is {me.json().get('role')!r}")
    coins = client.get("/api/coins", headers=auth)
    if coins.status_code != 200:
        raise SmokeError(f"/api/coins with the smoke user's token: HTTP {coins.status_code}")
    symbols = [c["symbol"] for c in coins.json()["data"]]
    if "BTC" not in symbols:
        raise SmokeError(f"/api/coins has no BTC: {symbols}")
    return ", ".join(symbols)


def run(
    base_url: str,
    *,
    origin: str | None = None,
    clerk_secret_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
    clerk_transport: httpx.BaseTransport | None = None,
    sleep: Callable = time.sleep,
) -> list[str]:
    """Run every check; returns one line per passed check, raises SmokeError on the first
    failure."""
    report = []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30, transport=transport) as client:
        health = wait_for_health(client, sleep=sleep)
        report.append(f"health ok (version {health.get('version')})")
        check_auth_required(client)
        report.append("auth enforced (401 without a token)")
        if origin:
            check_cors(client, origin)
            report.append(f"CORS allows {origin} and refuses others")
        if not clerk_secret_key:
            report.append("WARNING: no Clerk secret key, authenticated call skipped")
            return report
        if clerk_secret_key.startswith("sk_live_"):
            report.append("WARNING: production Clerk instance, authenticated call skipped")
            return report
        headers = {"Authorization": f"Bearer {clerk_secret_key}"}
        with httpx.Client(
            base_url=CLERK_API, headers=headers, timeout=30, transport=clerk_transport
        ) as clerk:
            session_id, jwt = smoke_user_session(clerk)
            try:
                symbols = check_authenticated(client, jwt)
            finally:
                revoke(clerk, session_id)
        report.append(f"authenticated as the smoke user (member): coins {symbols}")
    return report
