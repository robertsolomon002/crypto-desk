"""Telegram Bot API alerts (`sendMessage`).

Messages are sent as plain text (no `parse_mode`), so nothing in a title or body is
interpreted as markup. Text is capped at 4096 characters (docs/DATA_SOURCES.md). The bot token
is part of the URL, so errors never include the URL.
"""

import time
from collections.abc import Callable

import httpx

from desk.notify import Alert, truncate, with_retries

API = "https://api.telegram.org"
MAX_TEXT = 4096


def format_text(alert: Alert) -> str:
    parts = [f"Crypto Desk · {alert.title}"]
    if alert.body:
        parts.append(alert.body)
    if alert.url:
        parts.append(alert.url)
    return truncate("\n\n".join(parts), MAX_TEXT)


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return float(resp.json()["parameters"]["retry_after"])
    except (ValueError, KeyError, TypeError):
        return None


def send(
    client: httpx.Client,
    token: str,
    chat_id: str,
    alert: Alert,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    payload = {"chat_id": chat_id, "text": format_text(alert), "disable_web_page_preview": True}
    with_retries(
        lambda: client.post(f"{API}/bot{token}/sendMessage", json=payload),
        "telegram",
        _retry_after,
        sleep,
    )
