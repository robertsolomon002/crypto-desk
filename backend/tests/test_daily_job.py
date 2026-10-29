"""Daily job against Postgres: job_runs rows, freshness check, failure reporting, CLI exit code
and summary file (Stage 1.4). Sources are faked; their real paths are tested in
test_market_db and test_context_db.

Needs TEST_DATABASE_URL (e.g. the docker-compose Postgres); skipped otherwise.
"""

import datetime as dt

from sqlalchemy import select
from typer.testing import CliRunner

from desk.cli import app
from desk.config import get_settings
from desk.data import market, series
from desk.data.coins import seed_coins
from desk.data.update import SOURCES, SourceResult
from desk.jobs import daily
from desk.models import JobRun

D = dt.date
NOW = dt.datetime(2026, 10, 30, 0, 25, tzinfo=dt.UTC)


def fill(sessions, last: D, coins=("BTC", "ETH", "SOL")) -> None:
    with sessions.begin() as s:
        seed_coins(s)
        for coin in coins:
            market.upsert_candles(s, [
                {"coin": coin, "date": last - dt.timedelta(days=i), "open": 1.0, "high": 1.0,
                 "low": 1.0, "close": 1.0 + i, "volume": 1.0, "source": "coinbase"}
                for i in range(40)
            ])  # fmt: skip
        series.upsert_series(s, "fng", [(last, 50.0)], "test")
        series.upsert_series(s, "cm:BTC:CapMVRVCur", [(last - dt.timedelta(days=3), 1.5)], "test")


def fake_update(failed: str | None = None):
    def update(sessions, now, echo=lambda line, err: None):
        return {
            name: SourceResult(name, ok=name != failed, lines=[f"{name} +1"],
                               error="RuntimeError: boom" if name == failed else None)
            for name in SOURCES
        }  # fmt: skip

    return update


def runs(sessions) -> list[JobRun]:
    with sessions() as s:
        return list(s.scalars(select(JobRun).order_by(JobRun.id)))


def test_success_records_a_job_run_and_refreshes_the_cache(pg_sessions) -> None:
    fill(pg_sessions, NOW.date() - dt.timedelta(days=1))
    result = daily.run_daily(pg_sessions, NOW, update=fake_update())
    assert result.status == "success" and result.problems == []
    assert result.cache and result.cache["computed"] > 0
    (row,) = runs(pg_sessions)
    assert row.job == "daily" and row.status == "success" and row.ended_at and row.error is None
    # on-chain 3 days old: a note, not a failure
    assert result.notes == ["cm:BTC:CapMVRVCur last value 2026-10-26 (4 days old)"]
    assert "Daily job 2026-10-30 00:25 UTC: success" in result.summary()


def test_failed_source_and_stale_candles_fail_the_run(pg_sessions) -> None:
    fill(pg_sessions, NOW.date() - dt.timedelta(days=1), coins=("BTC", "ETH"))
    with pg_sessions.begin() as s:  # SOL is two days behind
        market.upsert_candles(s, [{"coin": "SOL", "date": D(2026, 10, 28), "open": 1.0,
                                   "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
                                   "source": "coinbase"}])  # fmt: skip
    result = daily.run_daily(pg_sessions, NOW, refresh_cache=False, update=fake_update("news"))
    assert result.status == "failed"
    assert result.problems == [
        "news FAILED: RuntimeError: boom",
        "stale: SOL last candle 2026-10-28 (expected 2026-10-29)",
    ]
    (row,) = runs(pg_sessions)
    assert row.status == "failed" and "news FAILED" in row.error and "stale: SOL" in row.error


def test_unexpected_error_is_recorded(pg_sessions) -> None:
    def broken(sessions, now, echo=None):
        raise ConnectionError("database went away")

    result = daily.run_daily(pg_sessions, NOW, update=broken)
    assert result.status == "failed" and result.error == "ConnectionError: database went away"
    assert runs(pg_sessions)[0].status == "failed"


def test_cli_exit_code_and_summary_file(pg_sessions, pg_engine, monkeypatch, tmp_path) -> None:
    fill(pg_sessions, dt.datetime.now(dt.UTC).date() - dt.timedelta(days=1))
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    out = tmp_path / "summary.txt"
    try:
        monkeypatch.setattr(daily, "update_all", fake_update())
        ok = CliRunner().invoke(app, ["jobs", "daily", "--no-cache", "--summary-file", str(out)])
        monkeypatch.setattr(daily, "update_all", fake_update("market"))
        bad = CliRunner().invoke(app, ["jobs", "daily", "--no-cache", "--summary-file", str(out)])
    finally:
        get_settings.cache_clear()
    assert ok.exit_code == 0, ok.output
    assert bad.exit_code == 1 and "market FAILED: RuntimeError: boom" in bad.output
    assert out.read_text(encoding="utf-8").startswith("Daily job ")
    assert "failed" in out.read_text(encoding="utf-8").splitlines()[0]


def test_notify_send_cli_reads_body_file(monkeypatch, tmp_path) -> None:
    sent = []

    def fake_send(alert):
        sent.append(alert)
        return {"telegram": "sent"}

    monkeypatch.setattr("desk.notify.send", fake_send)
    body = tmp_path / "b.txt"
    body.write_text("summary text\n", encoding="utf-8")
    args = ["notify", "send", "ops_failure", "--title", "Daily job failed", "--url",
            "https://github.com/x/actions/runs/1"]  # fmt: skip
    result = CliRunner().invoke(app, [*args, "--body-file", str(body)])
    missing = CliRunner().invoke(app, [*args, "--body-file", str(tmp_path / "none.txt")])
    assert result.exit_code == 0 and missing.exit_code == 0
    assert sent[0].body == "summary text" and sent[0].event == "ops_failure"
    assert sent[1].body == "No summary was written; see the run log."
