"""Discord webhook alerts.

Discord renders Markdown in webhook content, so the title and body are escaped (masked links,
formatting and quotes cannot be injected by untrusted text) and `allowed_mentions` is empty, so
no message can ping @everyone, roles or users. Content is capped at 2000 characters
(docs/DATA_SOURCES.md). The webhook URL is a secret, so errors never include it.
"""

import re
import time
from collections.abc import Callable

import httpx

from desk.notify import Alert, truncate, with_retries

MAX_CONTENT = 2000
_MARKDOWN = re.compile(r"([\\*_~`|>\[\]()#\-<@:])")


def escape(text: str) -> str:
    return _MARKDOWN.sub(r"\\\1", text)


def format_text(alert: Alert) -> str:
    url = f"\n{alert.url}" if alert.url else ""
    head = f"**Crypto Desk · {escape(alert.title)}**"
    body = f"\n{escape(alert.body)}" if alert.body else ""
    room = MAX_CONTENT - len(head) - len(url)
    return head + truncate(body, max(room, 0)) + url


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return float(resp.headers.get("Retry-After") or resp.json()["retry_after"])
    except (ValueError, KeyError, TypeError):
        return None


def send(
    client: httpx.Client,
    webhook_url: str,
    alert: Alert,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    payload = {"content": format_text(alert), "allowed_mentions": {"parse": []}}
    with_retries(lambda: client.post(webhook_url, json=payload), "discord", _retry_after, sleep)
