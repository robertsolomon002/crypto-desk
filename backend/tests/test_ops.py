"""Operations (Stage 8.1, D53): the Health report, error counts, the weekly summary, backups,
structured logs and the admin Health route.

The report and route tests need TEST_DATABASE_URL (docker-compose Postgres); the backup's
subprocesses are faked here (the real pg_dump/gpg round trip is in docs/DECISIONS.md D53).
"""

import datetime as dt
import json
import logging
import subprocess
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from desk.api.main import app
from desk.api.routes import admin
from desk.data import market, series
from desk.data.coins import seed_coins
from desk.models import AppError, JobRun, LlmSpend, McoVideo
from desk.notify import load_routes
from desk.ops import backup, errors, health, logs
from desk.ops.summary import format_summary
from tests.api_fakes import ADMIN, MEMBER, auth

NOW = dt.datetime(2026, 11, 9, 7, 0, tzinfo=dt.UTC)
TODAY = NOW.date()


def run(job: str, hours_ago: float, status: str = "success", error: str | None = None) -> JobRun:
    start = NOW - dt.timedelta(hours=hours_ago)
    return JobRun(job=job, started_at=start, ended_at=start + dt.timedelta(seconds=42),
                  status=status, error=error)  # fmt: skip


@pytest.fixture
def ops_db(pg_sessions):
    """Core coins with fresh candles, one stale on-chain series, a mix of job runs, spend at
    85% of the cap, two app errors and a failed MCO video."""
    with pg_sessions.begin() as s:
        seed_coins(s)
        for coin in ("BTC", "ETH", "SOL"):
            market.upsert_candles(s, [{"coin": coin, "date": TODAY - dt.timedelta(days=1),
                                       "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1,
                                       "source": "coinbase"}])  # fmt: skip
        series.upsert_series(s, "fng", [(TODAY, 50.0)], "test")
        series.upsert_series(s, "cm:BTC:CapMVRVCur", [(TODAY - dt.timedelta(days=1), 1.5)], "t")
        series.upsert_series(s, "cm:ETH:CapMVRVCur", [(TODAY - dt.timedelta(days=9), 1.5)], "t")
        s.add_all([
            run("daily", 7), run("daily", 31, "failed", "market FAILED: timeout"),
            run("levelwatch", 6), run("mco", 30), run("weekly", 7, "failed", "desk BTC invalid"),
            run("weekly", 175), run("backup", 200),
        ])  # fmt: skip
        s.add(LlmSpend(date=TODAY, source="desk", model="m", tokens_in=1, tokens_out=1,
                       cost=Decimal("6.80")))  # fmt: skip
        s.add(McoVideo(video_id="v1", title="Private title", url="https://y/v1",
                       published_at=NOW - dt.timedelta(days=1), status="failed",
                       error="gemini:503"))  # fmt: skip
        s.add_all([
            AppError(where="GET /api/overview", kind="OperationalError", status=500,
                     created_at=NOW - dt.timedelta(hours=2)),
            AppError(where="GET /api/overview", kind="OperationalError", status=500,
                     created_at=NOW - dt.timedelta(hours=1)),
            AppError(where="agent.chat", kind="provider", created_at=NOW - dt.timedelta(days=30)),
        ])  # fmt: skip
    return pg_sessions


def test_report_jobs_overdue_and_failures(ops_db) -> None:
    with ops_db() as s:
        r = health.report(s, NOW)
    jobs = {j.job: j for j in r.jobs}
    assert list(jobs) == ["daily", "levelwatch", "mco", "weekly", "backup"]
    assert not jobs["daily"].overdue and jobs["daily"].failures == 1 and jobs["daily"].runs == 2
    assert jobs["daily"].last_seconds == 42 and jobs["daily"].last_error.startswith("market")
    assert jobs["mco"].overdue  # 30 h > 26 h
    # The newest weekly run failed and the success before it is 175 h old (> 170 h).
    assert jobs["weekly"].last_status == "failed" and jobs["weekly"].overdue
    assert jobs["backup"].overdue
    assert "mco: no successful run in 26 h" in r.problems and not r.ok


def test_report_freshness_spend_errors_usage(ops_db) -> None:
    with ops_db() as s:
        r = health.report(s, NOW)
    fresh = {f.detail: f for f in r.freshness}
    assert not fresh["BTC daily candles"].stale and fresh["BTC daily candles"].age_days == 1
    assert fresh["ETH Coin Metrics"].stale and not fresh["BTC Coin Metrics"].stale
    assert fresh["CoinGecko snapshot"].last_date is None and fresh["CoinGecko snapshot"].stale
    assert fresh["newest desk signal week"].stale  # no signals yet

    sp = r.spend
    assert sp.month == "2026-11" and sp.spent_usd == pytest.approx(6.8) and sp.cap_usd == 8
    assert sp.degraded and not sp.exhausted
    assert all(d.active for d in sp.degradations) and len(sp.degradations) == 3
    assert sp.projected_usd == pytest.approx(6.8 / 9 * 30, rel=1e-3)
    assert [x.source for x in sp.by_source] == ["desk"]

    e = r.errors
    assert [(c.where, c.kind, c.count) for c in e.app] == [
        ("GET /api/overview", "OperationalError", 2)
    ]  # the 30-day-old row is outside the window
    assert e.job_failures == 2 and e.mco_failures == 1 and e.total == 5

    assert r.usage.database_bytes > 0 and r.usage.storage_limit_bytes == 1024**3
    assert r.usage.tables and all(link.url.startswith("https://") for link in r.usage.links)


def test_report_hides_mco_when_off(ops_db, monkeypatch) -> None:
    monkeypatch.setattr(health, "_mco_on", lambda: False)
    with ops_db() as s:
        r = health.report(s, NOW)
    assert "mco" not in [j.job for j in r.jobs]
    assert "MCO" not in [f.source for f in r.freshness] and r.errors.mco_failures == 0


def test_summary_is_counts_only(ops_db) -> None:
    with ops_db() as s:
        title, body = format_summary(health.report(s, NOW))
    assert title.startswith("Weekly ops:") and "to look at" in title
    assert "- daily: success 7 h ago; 2 runs, 1 failed" in body
    assert "- mco: success 30 h ago; 1 runs, 0 failed OVERDUE" in body
    with ops_db.begin() as s:
        s.query(JobRun).filter(JobRun.job == "backup").delete()
    with ops_db() as s:
        _, body = format_summary(health.report(s, NOW))
    assert "- backup: never ran OVERDUE" in body
    assert "LLM spend 2026-11: $6.80 of $8.00" in body and "DEGRADED" in body
    assert "Errors (7 days): 5 (2 app, 2 job runs, 1 MCO videos)" in body
    assert "Private title" not in body and "gemini" not in body  # no MCO text or codes


def test_errors_record_counts_and_prune(pg_sessions) -> None:
    errors.record(pg_sessions, "GET /api/x" + "y" * 200, "ValueError", 500)
    with pg_sessions() as s:
        rows = errors.counts(s, NOW - dt.timedelta(days=3650))
    assert len(rows) == 1 and len(rows[0][0]) == 128 and rows[0][2] == 1
    with pg_sessions.begin() as s:
        assert errors.prune(s, dt.datetime.now(dt.UTC) + dt.timedelta(seconds=5)) == 1


def test_errors_record_never_raises() -> None:
    class Broken:
        def begin(self):
            raise RuntimeError("database down")

    errors.record(Broken(), "GET /x", "E")  # type: ignore[arg-type]


def test_ops_summary_is_admin_only() -> None:
    assert load_routes()["ops_summary"] == ["telegram"]


# --- Backup -----------------------------------------------------------------------------------

URL = "postgresql://desk_owner:s3cret-pw@ep-x-pooler.us-east-2.aws.neon.tech/desk?sslmode=require"
TABLES = ["coins", "users", "signals"]
LISTING = "\n".join(f"; 1; 0 0 TABLE DATA public {t} owner" for t in TABLES)


class FakeRun:
    """Stands in for pg_dump, pg_restore and gpg: writes their output files, records calls."""

    def __init__(self, fail: str | None = None, tables: int = len(TABLES)) -> None:
        self.calls: list[tuple[list[str], bytes | None, dict | None]] = []
        self.fail, self.tables = fail, tables

    def __call__(self, args, input=None, capture_output=True, check=False, env=None):
        self.calls.append((list(args), input, env))
        tool = args[0]
        if tool == self.fail:  # each tool echoes the secret it was given
            secret = b"s3cret-pw" if tool == "pg_dump" else (input or b"")
            stderr = b"FATAL: password " + secret + b" rejected"
            return subprocess.CompletedProcess(args, 2, b"", stderr)
        if tool == "pg_dump":
            Path(next(a for a in args if a.startswith("--file="))[7:]).write_bytes(b"PGDMP" * 10)
        if tool == "gpg":
            Path(args[args.index("--output") + 1]).write_bytes(b"sealed" * 5)
        out = "\n".join(LISTING.splitlines()[: self.tables]).encode()
        return subprocess.CompletedProcess(args, 0, out if tool == "pg_restore" else b"", b"")


@pytest.fixture
def backup_cfg(monkeypatch):
    cfg = {"backup": {"bucket": "bk", "prefix": "weekly/", "tables": TABLES}}
    monkeypatch.setattr(backup, "ops_settings", lambda: cfg)


@respx.mock
def test_backup_dumps_encrypts_uploads_and_records(pg_sessions, tmp_path, backup_cfg) -> None:
    gcs = respx.post("https://storage.googleapis.com/upload/storage/v1/b/bk/o").mock(
        return_value=httpx.Response(200, json={"name": "x"}))  # fmt: skip
    fake = FakeRun()
    r = backup.run_backup(pg_sessions, URL, tmp_path, "pass phrase", "tok", now=NOW, run=fake)
    assert r.status == "success", r.error
    assert r.name == "desk-2026-11-09-r0004.dump.gpg" and r.tables == 3
    assert r.uploaded == "gs://bk/weekly/desk-2026-11-09-r0004.dump.gpg"
    dump_args, _, env = fake.calls[0]
    assert dump_args[0] == "pg_dump" and "--data-only" in dump_args
    assert [a for a in dump_args if a.startswith("--table=")] == [
        "--table=public.coins",
        "--table=public.users",
        "--table=public.signals",
    ]
    target = next(a for a in dump_args if a.startswith("--dbname="))
    assert "-pooler" not in target and "s3cret-pw" not in " ".join(dump_args)  # direct host
    assert env["PGPASSWORD"] == "s3cret-pw"
    gpg_args, stdin, _ = fake.calls[2]
    assert stdin == b"pass phrase" and "pass phrase" not in " ".join(gpg_args)
    req = gcs.calls[0].request
    assert req.url.params["ifGenerationMatch"] == "0" and req.url.params["uploadType"] == "media"
    assert req.headers["authorization"] == "Bearer tok" and req.content == b"sealed" * 5
    assert list(tmp_path.iterdir()) == []  # plain and sealed files both gone
    with pg_sessions() as s:
        row = s.scalars(select(JobRun).where(JobRun.job == "backup")).one()
    assert row.status == "success" and row.ended_at is not None and row.error is None


@pytest.mark.parametrize(
    ("fake", "passphrase", "expect"),
    [
        (FakeRun(), None, "BACKUP_PASSPHRASE is not set"),
        (
            FakeRun(fail="pg_dump"),
            "pass phrase",
            "pg_dump exited 2: FATAL: password [redacted] rejected",
        ),
        (FakeRun(tables=2), "pass phrase", "the dump holds 2 tables, expected 3"),
        (FakeRun(fail="gpg"), "pass phrase", "gpg exited 2: FATAL: password [redacted] rejected"),
    ],
)
def test_backup_failures_are_recorded_without_secrets(pg_sessions, tmp_path, backup_cfg, fake,
                                                      passphrase, expect) -> None:  # fmt: skip
    r = backup.run_backup(pg_sessions, URL, tmp_path, passphrase, None, now=NOW, run=fake)
    assert r.status == "failed" and r.error.startswith(expect)
    assert "s3cret" not in r.error and "pass phrase" not in r.error
    assert not list(tmp_path.glob("*.dump"))  # the plain dump never stays behind
    with pg_sessions() as s:
        assert s.scalar(select(JobRun.status).where(JobRun.job == "backup")) == "failed"


@respx.mock
def test_backup_upload_refuses_to_overwrite(pg_sessions, tmp_path, backup_cfg) -> None:
    respx.post("https://storage.googleapis.com/upload/storage/v1/b/bk/o").mock(
        return_value=httpx.Response(412))  # fmt: skip
    r = backup.run_backup(pg_sessions, URL, tmp_path, "p", "tok", now=NOW, run=FakeRun())
    assert r.status == "failed" and "already exists" in r.error


def test_backup_without_token_keeps_the_encrypted_file(pg_sessions, tmp_path, backup_cfg) -> None:
    r = backup.run_backup(pg_sessions, URL, tmp_path, "p", None, now=NOW, run=FakeRun(),
                          record=False)  # fmt: skip
    assert r.status == "success" and r.uploaded is None and r.run_id is None
    assert [p.name for p in tmp_path.iterdir()] == ["desk-2026-11-09-r0004.dump.gpg"]


def test_backup_tables_are_the_non_reproducible_ones() -> None:
    from desk.models import Base
    from desk.ops import ops_settings

    tables = ops_settings()["backup"]["tables"]
    assert set(tables) <= {t.name for t in Base.metadata.sorted_tables}
    assert {"users", "messages", "mco_extracts", "signals", "briefs", "llm_spend"} <= set(tables)
    assert not {"candles_daily", "series", "news", "analytics_cache"} & set(tables)


# --- Structured logs --------------------------------------------------------------------------


def test_json_formatter_keeps_the_traceback_in_one_entry() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        rec = logging.LogRecord("desk.x", logging.ERROR, __file__, 1, "failed %s", ("here",),
                                sys.exc_info())  # fmt: skip
    entry = json.loads(logs.JsonFormatter().format(rec))
    assert entry["severity"] == "ERROR" and entry["logger"] == "desk.x"
    assert entry["message"].startswith("failed here\nTraceback") and "ValueError: boom" in (
        entry["message"])  # fmt: skip


def test_configure_only_on_cloud_run(monkeypatch) -> None:
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert logs.configure() is False
    root = logging.getLogger()
    before = (list(root.handlers), root.level)
    try:
        assert logs.configure(force=True) is True
        assert isinstance(root.handlers[0].formatter, logs.JsonFormatter)
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
    finally:
        root.handlers, _ = before
        root.setLevel(before[1])
        logging.getLogger("uvicorn.access").setLevel(logging.NOTSET)


# --- API --------------------------------------------------------------------------------------


def test_health_route_is_admin_only(api) -> None:
    r = api.get("/api/admin/health", headers=auth(ADMIN))
    assert r.status_code == 200
    body = r.json()
    assert {"jobs", "freshness", "spend", "errors", "usage", "problems"} <= set(body)
    assert body["spend"]["cap_usd"] == 8
    assert api.get("/api/admin/health", headers=auth(MEMBER)).status_code == 403


def test_unhandled_errors_are_counted_and_still_500(api, api_sessions, monkeypatch) -> None:
    def boom(session, now=None):
        raise RuntimeError("secret detail sk-ant-123")

    monkeypatch.setattr(admin, "health_report", boom)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/admin/health", headers=auth(ADMIN)).status_code == 500
    with api_sessions() as s:
        rows = s.execute(select(AppError.where, AppError.kind, AppError.status)).all()
    assert rows == [("GET /api/admin/health", "RuntimeError", 500)]


def test_agent_errors_are_counted_by_code(api, api_sessions, monkeypatch) -> None:
    from desk.agents import llm
    from tests.agent_fakes import ScriptedModel, answer

    class Failing(ScriptedModel):
        async def _astream(self, *a, **k):
            raise RuntimeError("provider down")
            yield  # pragma: no cover

    monkeypatch.setattr(llm, "make_chat_model", lambda c, k: Failing(script=[answer]))
    r = api.post("/api/agent/chat", json={"message": "hi"}, headers=auth(ADMIN))
    assert "event: error" in r.text
    with api_sessions() as s:
        assert s.scalar(select(func.count()).select_from(AppError)
                        .where(AppError.where == "agent.chat",
                               AppError.kind == "provider")) == 1  # fmt: skip


@pytest.mark.parametrize(
    ("path", "template", "expect"),
    [
        ("/api/admin/health", "/admin/health", "/api/admin/health"),
        ("/api/admin/users/7", "/users/{user_id}", "/api/admin/users/{user_id}"),
        ("/api/health", "/api/health", "/api/health"),
        ("/nope", None, "unmatched"),
    ],
)
def test_route_template(path, template, expect) -> None:
    from types import SimpleNamespace

    from desk.api.middleware import route_template

    scope = {"path": path, "route": SimpleNamespace(path=template) if template else None}
    assert route_template(scope) == expect
