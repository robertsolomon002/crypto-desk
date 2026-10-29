"""Alerts to Telegram and Discord with per-event routing from `config/settings.yaml` (D11).

`send(Alert(...))` looks up the event's channels, formats the text for each channel, and sends
it. A channel whose secret is missing is skipped with a warning; a failed channel never stops
the others, and `send` never raises for delivery problems. Admin-only events (ops failures,
MCO review) may not be routed to the public Discord channel.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

from desk.config import Settings, get_settings

log = logging.getLogger(__name__)

EVENTS = ("brief_ready", "level_cross", "new_mco_summary", "mco_review_pending", "ops_failure")
ADMIN_ONLY = {"ops_failure", "mco_review_pending"}
CHANNELS = ("telegram", "discord", "discord_ops")
PUBLIC = {"discord"}
RETRIES = 3
MAX_WAIT = 30.0


class NotifyError(RuntimeError):
    """A delivery failure. Messages never contain tokens or webhook URLs."""


@dataclass(frozen=True)
class Alert:
    event: str
    title: str
    body: str = ""
    url: str | None = None  # must be http(s)


def load_routes(path: Path | None = None) -> dict[str, list[str]]:
    path = path or get_settings().config_dir / "settings.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    routes = {k: list(v or []) for k, v in (cfg.get("alerts") or {}).items()}
    for event, channels in routes.items():
        if event not in EVENTS:
            raise ValueError(f"unknown alert event {event!r} in settings.yaml")
        bad = set(channels) - set(CHANNELS)
        if bad:
            raise ValueError(f"{event}: unknown channel(s) {sorted(bad)}")
        if event in ADMIN_ONLY and PUBLIC & set(channels):
            raise ValueError(f"{event} is admin-only and may not go to {sorted(PUBLIC)}")
    return routes


def truncate(text: str, limit: int) -> str:
    """Cut to `limit` UTF-16 code units (how Telegram and Discord count), ending with '…'."""

    def units(s: str) -> int:
        return len(s.encode("utf-16-le")) // 2

    if units(text) <= limit:
        return text
    out = []
    used = 1  # room for the ellipsis
    for ch in text:
        u = units(ch)
        if used + u > limit:
            break
        out.append(ch)
        used += u
    return "".join(out).rstrip() + "…"


def with_retries(
    request: Callable[[], httpx.Response],
    what: str,
    retry_after: Callable[[httpx.Response], float | None],
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """Retry 429 (after the server's wait, capped at 30 s), 5xx and network errors."""
    for attempt in range(1, RETRIES + 1):
        try:
            resp = request()
        except httpx.HTTPError as exc:
            if attempt == RETRIES:
                raise NotifyError(f"{what}: {type(exc).__name__}") from None
            sleep(2.0**attempt)
            continue
        if resp.status_code == 429 and attempt < RETRIES:
            sleep(min(retry_after(resp) or 2.0**attempt, MAX_WAIT))
            continue
        if resp.status_code >= 500 and attempt < RETRIES:
            sleep(2.0**attempt)
            continue
        if resp.is_success:
            return resp
        raise NotifyError(f"{what}: HTTP {resp.status_code}")
    raise AssertionError("unreachable")


def send(
    alert: Alert,
    settings: Settings | None = None,
    routes: dict[str, list[str]] | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, str]:
    """Deliver to every channel routed for the event; returns channel -> sent | skipped: … |
    failed: …"""
    from desk.notify import discord, telegram

    if alert.event not in EVENTS:
        raise ValueError(f"unknown alert event {alert.event!r}")
    if alert.url is not None and not alert.url.startswith(("https://", "http://")):
        raise ValueError("alert url must be http(s)")
    settings = settings or get_settings()
    channels = (routes if routes is not None else load_routes()).get(alert.event, [])
    status: dict[str, str] = {}
    own_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(20.0))
    try:
        for channel in channels:
            try:
                if channel == "telegram":
                    if not (settings.telegram_bot_token and settings.telegram_chat_id):
                        raise _Missing("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
                    telegram.send(client, settings.telegram_bot_token.get_secret_value(),
                                  settings.telegram_chat_id, alert, sleep)  # fmt: skip
                else:
                    secret = (settings.discord_webhook_url if channel == "discord"
                              else settings.discord_ops_webhook_url)  # fmt: skip
                    if secret is None:
                        name = "DISCORD_WEBHOOK_URL" if channel == "discord" else (
                            "DISCORD_OPS_WEBHOOK_URL")  # fmt: skip
                        raise _Missing(f"{name} not set")
                    discord.send(client, secret.get_secret_value(), alert, sleep)
                status[channel] = "sent"
            except _Missing as exc:
                log.warning("alert %s: %s skipped (%s)", alert.event, channel, exc)
                status[channel] = f"skipped: {exc}"
            except NotifyError as exc:
                log.warning("alert %s: %s failed (%s)", alert.event, channel, exc)
                status[channel] = f"failed: {exc}"
    finally:
        if own_client:
            client.close()
    return status


class _Missing(Exception):
    pass
