"""Alerts: routing, missing secrets, retries, length limits, escaping, secret-free errors
(Stage 1.4). All HTTP is mocked."""

import httpx
import pytest
import respx
from pydantic import SecretStr

from desk.config import Settings
from desk.notify import Alert, discord, load_routes, send, telegram, truncate

TOKEN = "123:SECRET-TOKEN"
HOOK = "https://discord.com/api/webhooks/1/SECRET-HOOK"
OPS_HOOK = "https://discord.com/api/webhooks/2/SECRET-OPS"
TG_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


def settings(**overrides) -> Settings:
    base = {
        "telegram_bot_token": SecretStr(TOKEN),
        "telegram_chat_id": "42",
        "discord_webhook_url": SecretStr(HOOK),
        "discord_ops_webhook_url": SecretStr(OPS_HOOK),
    }
    return Settings(_env_file=None, **{**base, **overrides})  # fmt: skip


def no_sleep(_: float) -> None:
    pass


def test_repo_routes_keep_admin_events_off_the_public_channel() -> None:
    routes = load_routes()
    assert routes["ops_failure"] == ["telegram", "discord_ops"]
    assert "discord" not in routes["mco_review_pending"]
    assert "discord" in routes["brief_ready"]


def test_routes_reject_admin_event_on_public_channel(tmp_path) -> None:
    bad = tmp_path / "settings.yaml"
    bad.write_text("alerts:\n  ops_failure: [telegram, discord]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="admin-only"):
        load_routes(bad)
    bad.write_text("alerts:\n  brief_ready: [slack]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown channel"):
        load_routes(bad)


@respx.mock
def test_send_routes_to_each_channel_and_skips_missing_secrets() -> None:
    tg = respx.post(TG_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    ops = respx.post(OPS_HOOK).mock(return_value=httpx.Response(204))
    public = respx.post(HOOK).mock(return_value=httpx.Response(204))
    alert = Alert("ops_failure", "Daily job failed", "market FAILED", "https://github.com/x/1")
    assert send(alert, settings(), sleep=no_sleep) == {"telegram": "sent", "discord_ops": "sent"}
    assert public.call_count == 0  # admin-only event never reaches the public channel
    body = tg.calls[0].request.content.decode()
    assert '"chat_id":"42"' in body and "parse_mode" not in body

    status = send(alert, settings(telegram_bot_token=None), sleep=no_sleep)
    assert status["telegram"].startswith("skipped: TELEGRAM_BOT_TOKEN")
    assert status["discord_ops"] == "sent" and ops.call_count == 2


@respx.mock
def test_retries_429_and_5xx_then_reports_failure_without_secrets() -> None:
    waits: list[float] = []
    tg = respx.post(TG_URL).mock(
        side_effect=[
            httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 3}}),
            httpx.Response(502),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    routes = {"level_cross": ["telegram"]}
    status = send(Alert("level_cross", "BTC crossed"), settings(), routes, sleep=waits.append)
    assert status == {"telegram": "sent"}
    assert tg.call_count == 3 and waits == [3.0, 4.0]

    respx.post(HOOK).mock(return_value=httpx.Response(403))
    status = send(Alert("brief_ready", "Brief"), settings(), routes={"brief_ready": ["discord"]},
                  sleep=no_sleep)  # fmt: skip
    assert status == {"discord": "failed: discord: HTTP 403"}
    assert "SECRET" not in str(status)


@respx.mock
def test_network_errors_do_not_leak_the_token() -> None:
    respx.post(TG_URL).mock(side_effect=httpx.ConnectError(f"cannot reach {TG_URL}"))
    status = send(Alert("level_cross", "x"), settings(), routes={"level_cross": ["telegram"]},
                  sleep=no_sleep)  # fmt: skip
    assert status == {"telegram": "failed: telegram: ConnectError"}


def test_length_limits_and_truncation() -> None:
    long = "x" * 5000
    assert len(telegram.format_text(Alert("brief_ready", "T", long))) == telegram.MAX_TEXT
    text = discord.format_text(Alert("brief_ready", "T", long, "https://example.com/run"))
    assert len(text) <= discord.MAX_CONTENT and text.endswith("\nhttps://example.com/run")
    assert truncate("😀" * 3, 4) == "😀…"  # an emoji is 2 UTF-16 units
    assert truncate("short", 10) == "short"


def test_discord_escapes_markdown_and_disables_mentions() -> None:
    hostile = "[click](https://evil.example) @everyone **bold** `code`"
    text = discord.format_text(Alert("new_mco_summary", hostile))
    assert "\\[click\\]\\(https\\://evil.example\\)" in text
    assert "\\@everyone" in text and "\\*\\*bold\\*\\*" in text


@respx.mock
def test_discord_payload_has_no_mentions() -> None:
    hook = respx.post(HOOK).mock(return_value=httpx.Response(204))
    send(Alert("brief_ready", "@everyone"), settings(), routes={"brief_ready": ["discord"]})
    assert '"allowed_mentions":{"parse":[]}' in hook.calls[0].request.content.decode()


def test_bad_event_or_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown alert event"):
        send(Alert("nope", "x"), settings(), routes={})
    with pytest.raises(ValueError, match="http"):
        send(Alert("brief_ready", "x", url="javascript:alert(1)"), settings(), routes={})
