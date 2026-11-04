"""Test doubles for the API: a local RSA key standing in for Clerk's JWKS, token minting, and a
seeded database (Stage 2.1)."""

import datetime as dt
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
import numpy as np
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.orm import Session

from desk.api.auth import ClerkVerifier
from desk.data import market, news, series
from desk.data.coins import seed_coins
from desk.models import CalendarEvent, McoExtract, McoVideo, McoWaveLabel, User

ISSUER = "https://test-instance.clerk.accounts.dev"
ORIGIN = "http://localhost:5173"
KID = "test-kid"
LAST_DAY = dt.date(2026, 10, 27)
CANARY = "sk-or-v1-canary-7f3a9c2e5b8d1f4a"


@dataclass
class _Key:
    key: Any


class FakeJwks:
    """Stands in for `jwt.PyJWKClient`: resolves our test `kid` to the test public key."""

    def __init__(self, public_key: Any) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> _Key:
        if jwt.get_unverified_header(token).get("kid") != KID:
            raise jwt.PyJWKClientError("unknown kid")
        return _Key(self.public_key)


PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def verifier() -> ClerkVerifier:
    return ClerkVerifier(ISSUER, [ORIGIN], jwks_client=FakeJwks(PRIVATE_KEY.public_key()))


def token(sub: str, /, key: Any = PRIVATE_KEY, **overrides: Any) -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": sub, "sid": "sess_1", "azp": ORIGIN, "iat": now - 5,
              "nbf": now - 5, "exp": now + 60, "v": 2, **overrides}  # fmt: skip
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})


def auth(sub: str, /, **overrides: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(sub, **overrides)}"}


COINS = ["BTC", "ETH", "SOL"]
SEEDED = {
    "coins",
    "candles_daily",
    "series",
    "news",
    "calendar_events",
    "users",
    "mco_videos",
    "mco_extracts",
    "mco_wave_labels",
}

MEMBER = "user_member"
OTHER_MEMBER = "user_other"
ADMIN = "user_admin"


def _candles(coin: str, start: dt.date, seed: int) -> list[dict]:
    days = (LAST_DAY - start).days + 1
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, days)))
    return [
        {"coin": coin, "date": start + dt.timedelta(days=i), "open": c, "high": c * 1.02,
         "low": c * 0.98, "close": c, "volume": 1.0, "source": "coinbase"}
        for i, c in enumerate(closes.tolist())
    ]  # fmt: skip


def _days(start: dt.date, seed: int, scale: float = 1.0) -> list[tuple[dt.date, float]]:
    rng = np.random.default_rng(seed)
    days = (LAST_DAY - start).days + 1
    return [(start + dt.timedelta(days=i), float(scale * rng.uniform(1, 2))) for i in range(days)]


def seed(session: Session) -> None:
    """Three coins (BTC from 2011 so cycles have anchors), context series, news, calendar,
    and one admin user (members are created on first sight)."""
    seed_coins(session)
    market.upsert_candles(session, _candles("BTC", dt.date(2011, 1, 1), 1))
    market.upsert_candles(session, _candles("ETH", dt.date(2023, 1, 1), 2))
    market.upsert_candles(session, _candles("SOL", dt.date(2024, 1, 1), 3))
    start = dt.date(2024, 1, 1)
    series.upsert_series(session, "fng", _days(start, 4, 50), "alternative.me")
    for i, (sid, scale) in enumerate({"DGS10": 4, "DTWEXBGS": 120, "DFF": 5}.items()):
        series.upsert_series(session, f"fred:{sid}", _days(start, 10 + i, scale), "fred")
    series.upsert_series(session, "fred:M2SL", [(dt.date(2026, m, 1), 21000.0 + m)
                                                for m in range(1, 10)], "fred")  # fmt: skip
    for coin in ("btc", "eth"):
        series.upsert_series(session, f"dominance:{coin}", _days(dt.date(2026, 10, 1), 20), "x")
    for metric, scale in {"CapMrktCurUSD": 1e12, "CapMVRVCur": 2, "SplyCur": 2e7,
                          "AdrActCnt": 1e6, "HashRate": 1e8}.items():  # fmt: skip
        series.upsert_series(session, f"cm:BTC:{metric}", _days(start, 30, scale), "coinmetrics")
    news.store(session, [
        news.NewsItem("CoinDesk", "=HYPERLINK(\"http://evil\") Bitcoin rallies", "https://a.example/1",
                      dt.datetime(2026, 10, 26, 12, tzinfo=dt.UTC), ("BTC",)),
        news.NewsItem("Decrypt", "Ether upgrade lands", "https://a.example/2",
                      dt.datetime(2026, 10, 27, 9, tzinfo=dt.UTC), ("ETH",)),
        news.NewsItem("Decrypt", "Tomorrow's headline", "https://a.example/3",
                      dt.datetime(2026, 10, 28, 9, tzinfo=dt.UTC), ("BTC",)),
    ])  # fmt: skip
    session.add_all([
        CalendarEvent(date=dt.date(2026, 10, 28), time_utc=dt.time(18), kind="fomc",
                      title="FOMC decision", source_url="https://www.federalreserve.gov/"),
        CalendarEvent(date=dt.date(2026, 11, 10), time_utc=dt.time(13, 30), kind="cpi",
                      title="CPI (October)", source_url="https://www.bls.gov/"),
    ])  # fmt: skip
    session.add(User(clerk_id=ADMIN, role="admin"))
    seed_mco(session)


MCO_VIDEO = "fakeVideo01"
PENDING_CANARY = "PENDING-LABEL-CANARY"


def seed_mco(session: Session) -> None:
    """One summarized (made-up) MCO video: an approved and a pending label, plus raw
    pivot_labels in the payload that must never reach members (Decision 7)."""
    session.add(
        McoVideo(
            video_id=MCO_VIDEO,
            title="Fake title",
            url="https://www.youtube.com/watch?v=fakeVideo01",
            published_at=dt.datetime(2026, 10, 26, 13, tzinfo=dt.UTC),
            status="done",
        )
    )
    session.add(
        McoVideo(
            video_id="fakeVideo02",
            title="Not yet done",
            url="https://www.youtube.com/watch?v=fakeVideo02",
            published_at=dt.datetime(2026, 10, 27, 13, tzinfo=dt.UTC),
            status="new",
        )
    )
    session.flush()
    view = {
        "coin": "BTC",
        "bias": "bearish",
        "wave_position": "wave B",
        "primary_scenario": "C down",
        "alternative_scenario": "new high",
        "key_levels": [{"price": 60000.0, "label": "support"}],
        "invalidation": 70000.0,
        "targets": [58000.0],
        "timeframe": "weeks",
        "extraction_confidence": "medium",
        "pivot_labels": [
            {
                "wave_label": PENDING_CANARY,
                "pivot_kind": "high",
                "approx_date": "2026-10-20",
                "approx_price": 65000.0,
                "chart_timeframe": "1d",
            }
        ],
    }
    ex = McoExtract(
        video_id=MCO_VIDEO,
        model="gemini-3.5-flash-lite",
        prompt_version="mco_extract_v1",
        payload={"coins": [view], "summary": "Fake summary.", "checks": []},
        summary="Fake summary.",
    )
    session.add(ex)
    session.flush()
    for label, status in (("1", "approved"), ("PENDING", "pending"), ("X", "rejected")):
        session.add(
            McoWaveLabel(
                extract_id=ex.id,
                coin="BTC",
                label=label,
                timeframe="1d",
                approx_date=dt.date(2026, 10, 20),
                approx_price=65000.0,
                pivot_kind="high",
                pivot_date=dt.date(2026, 10, 20),
                pivot_price=65100.0,
                status=status,
            )
        )


class FakeExchange:
    """ccxt's Coinbase for the watchlist checks: `markets` maps a market to (active, spot,
    name); markets in `young` have no candles a year back (D42)."""

    def __init__(self, markets: dict[str, tuple[bool, bool, str]] | None = None,
                 young: set[str] | None = None) -> None:  # fmt: skip
        default = {f"{s}/USD": (True, True, s.title()) for s in ("LINK", "AAA", "BBB", "CCC")}
        self.markets = default if markets is None else markets
        self.young = young or set()
        self.calls: list[tuple[str, int]] = []

    def load_markets(self) -> dict:
        return {m: {"active": a, "spot": s, "info": {"base_name": n}}
                for m, (a, s, n) in self.markets.items()}  # fmt: skip

    def fetch_ohlcv(self, market: str, timeframe: str, since: int, limit: int) -> list:
        self.calls.append((market, since))
        return [] if market in self.young else [[since, 1, 1, 1, 1, 1]]


def provider_transport(status: int = 200) -> httpx.MockTransport:
    """Every LLM provider call answers `status`; the requests are kept for assertions."""

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"error": {"message": "echo " + str(request.headers)}})

    transport = httpx.MockTransport(handler)
    transport.seen = seen  # type: ignore[attr-defined]
    return transport


SIGNAL_WEEK = dt.date(2026, 10, 19)  # resolved
OPEN_WEEK = dt.date(2026, 10, 26)  # not yet resolved
DESK_SNAPSHOT = 9001
BRIEF_CANARY = "brief-canary-3c1f"


def desk_state(coin: str = "BTC") -> dict[str, Any]:
    """A saved `desk_run` result (DeskRunState) with one report, one case and the signal."""
    return {
        "coin": coin, "as_of": "2026-10-25", "model": "claude-haiku-5-5", "status": "valid",
        "error": None, "reference_close": 100.0, "reference_date": "2026-10-25",
        "reports": {"technical": {"analyst": "technical", "status": "done",
                                  "summary": "Made-up report.",
                                  "findings": [{"id": "T1", "claim": "Above the 20W SMA."}]}},
        "debate": {"bull_open": {"side": "bull", "phase": "opening",
                                 "points": [{"text": "Trend is up.", "cites": ["T1"]}]}},
        "signal": {"coin": coin, "stance": "lean_long", "confidence": 0.6, "entry_low": 95.0,
                   "entry_high": 98.0, "invalidation": 90.0, "target": 110.0,
                   "rationale": "Made-up rationale.", "cites": ["T1"]},
        "validation": {"ok": True, "errors": [], "attempts": 1},
        "usage": [{"node": "technical", "tokens_in": 10, "tokens_out": 5, "model_calls": 1}],
    }  # fmt: skip


def seed_signals(session: Session) -> dict[str, int]:
    """Two weeks of signals (Stage 7.2): the resolved week with a desk run, baselines, MCO and
    a brief; the open week with a desk and a coin-flip row. Returns ids by name."""
    from desk.models import AgentSnapshot, Brief, Conversation, SignalOutcome
    from desk.signals import chain
    from desk.signals.chain import Proposed

    jobs = User(clerk_id="user_jobs", role="member")
    session.add(jobs)
    session.flush()
    session.add(Conversation(id=DESK_SNAPSHOT, user_id=jobs.id, title="Ask the desk: BTC"))
    session.flush()
    session.add(
        AgentSnapshot(id=DESK_SNAPSHOT, user_id=jobs.id, conversation_id=DESK_SNAPSHOT,
                      tool="desk_run", args={"coin": "BTC"}, result=desk_state())
    )  # fmt: skip
    session.flush()
    desk = Proposed(
        coin="BTC", source="desk", stance="lean_long", confidence=0.6, entry_low=95.0,
        entry_high=98.0, invalidation=90.0, target=110.0, rationale="Made-up rationale.",
        transcript_ref=f"snapshot:{DESK_SNAPSHOT}",
    )  # fmt: skip
    rows = chain.append(session, 1, SIGNAL_WEEK, [
        desk,
        Proposed(coin="BTC", source="coinflip", stance="flat", confidence=0.5),
        Proposed(coin="BTC", source="trend", stance="lean_long", confidence=0.6),
        Proposed(coin="BTC", source="mco", stance="lean_long", confidence=0.7, invalidation=80.0,
                 target=120.0, rationale="MCO's latest video: bullish (AI-extracted)."),
        Proposed(coin="ETH", source="coinflip", stance="flat", confidence=0.5),
    ])  # fmt: skip
    ids = {f"{r.coin}:{r.source}": r.id for r in rows}
    outcomes = {  # week closed up 100 -> 105, the target 110 never touched
        "BTC:desk": (True, 0.16, "neither", 0.046),
        "BTC:coinflip": (False, 0.25, None, 0.0),
        "BTC:trend": (True, 0.16, None, 0.046),
        "BTC:mco": (True, 0.09, "neither", 0.046),
        "ETH:coinflip": (True, 0.25, None, 0.0),
    }
    for name, (hit, brier, first, pnl) in outcomes.items():
        session.add(SignalOutcome(signal_id=ids[name], reference_close=100.0, week_close=105.0,
                                  direction_hit=hit, brier=brier, first_hit=first,
                                  paper_pnl=pnl))  # fmt: skip
    session.add(Brief(week=SIGNAL_WEEK, model="claude-sonnet-5-5", prompt_version="brief_v1",
                      content=f"# Brief\n\n{BRIEF_CANARY}",
                      payload={"summary": [f"Line {i} {BRIEF_CANARY}" for i in range(5)],
                               "coins": [{"coin": "BTC", "setup": "Made-up setup.",
                                          "bull_case": "Up.", "bear_case": "Down.",
                                          "what_would_change": "A close below 90.",
                                          "levels_to_watch": [{"label": "desk invalidation",
                                                               "price": 90.0}]}]}))  # fmt: skip
    later = chain.append(session, 1, OPEN_WEEK, [
        Proposed(coin="BTC", source="desk", stance="flat", confidence=0.55),
        Proposed(coin="BTC", source="coinflip", stance="flat", confidence=0.5),
    ])  # fmt: skip
    ids["open:BTC:desk"] = later[0].id
    session.flush()
    return ids
