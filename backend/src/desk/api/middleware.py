"""ASGI middleware: user LLM key redaction and ETags (D37).

`LlmKeyRedaction` runs outermost. It removes `X-LLM-Key` from the request headers before any
other code sees them and keeps the value only as a `SecretStr` in `scope["state"]["llm_key"]`
(the agent routes read it from there in Stage 5.1). As a second layer, a log record factory
replaces the current request's key with `[redacted]` in any log message.
"""

import contextvars
import hashlib
import logging
from typing import Any

from pydantic import SecretStr
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LLM_KEY_HEADER = b"x-llm-key"
REDACTED = "[redacted]"

_current_key: contextvars.ContextVar[str | None] = contextvars.ContextVar("llm_key", default=None)
_factory_installed = False


def _install_log_redaction() -> None:
    global _factory_installed
    if _factory_installed:
        return
    base = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = base(*args, **kwargs)
        key = _current_key.get()
        if key:
            try:
                message = record.getMessage()
            except Exception:  # a malformed record; leave it to the handler
                return record
            if key in message:
                record.msg, record.args = message.replace(key, REDACTED), None
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


class LlmKeyRedaction:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        _install_log_redaction()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        key = None
        headers = []
        for name, value in scope["headers"]:
            if name.lower() == LLM_KEY_HEADER:
                key = value.decode("latin-1")
            else:
                headers.append((name, value))
        if key is None:
            await self.app(scope, receive, send)
            return
        scope = {**scope, "headers": headers}
        scope.setdefault("state", {})["llm_key"] = SecretStr(key)
        token = _current_key.set(key)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_key.reset(token)


class ETag:
    """Weak ETag on GET 200 JSON responses; 304 when `If-None-Match` matches. Responses are
    `Cache-Control: private, no-cache` (the browser revalidates; shared caches never store)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return
        start: Message | None = None
        body = bytearray()
        passthrough = False

        async def wrapped(message: Message) -> None:
            nonlocal start, passthrough
            if message["type"] == "http.response.start":
                headers = Headers(raw=message["headers"])
                json = headers.get("content-type", "").startswith("application/json")
                if message["status"] != 200 or not json:
                    passthrough = True
                    await send(message)
                else:
                    start = message
                return
            if passthrough:
                await send(message)
                return
            body.extend(message.get("body", b""))
            if message.get("more_body"):
                return
            assert start is not None
            etag = 'W/"' + hashlib.sha256(body).hexdigest()[:32] + '"'
            raw = [(k, v) for k, v in start["headers"] if k.lower() != b"content-length"]
            raw += [(b"etag", etag.encode()), (b"cache-control", b"private, no-cache")]
            if etag in _if_none_match(scope):
                await send({"type": "http.response.start", "status": 304, "headers": raw})
                await send({"type": "http.response.body", "body": b""})
                return
            raw.append((b"content-length", str(len(body)).encode()))
            await send({**start, "headers": raw})
            await send({"type": "http.response.body", "body": bytes(body)})

        await self.app(scope, receive, wrapped)


def _if_none_match(scope: Scope) -> set[str]:
    value = Headers(scope=scope).get("if-none-match", "")
    return {v.strip() for v in value.split(",") if v.strip()}
