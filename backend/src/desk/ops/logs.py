"""Structured logs on Cloud Run (Stage 8.1, D53).

Cloud Run puts a JSON line written to stdout into `jsonPayload`, moves `severity` to the entry's
severity and shows `message` as its text (docs.cloud.google.com/run/docs/logging, 2026-11-04).
A traceback inside `message` keeps the whole exception in one entry, which Error Reporting
picks up. Locally (no `K_SERVICE`, which Cloud Run sets) logging is left as it is.

The key redaction of `api/middleware.py` runs in the record factory, before any formatter, so
these lines get the redacted message too.
"""

import json
import logging
import os
import sys

SEVERITY = {"DEBUG": "DEBUG", "INFO": "INFO", "WARNING": "WARNING", "ERROR": "ERROR",
            "CRITICAL": "CRITICAL"}  # fmt: skip


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        entry = {
            "severity": SEVERITY.get(record.levelname, "DEFAULT"),
            "message": message,
            "logger": record.name,
        }
        return json.dumps(entry, ensure_ascii=False)


def configure(force: bool = False) -> bool:
    """JSON lines to stdout on Cloud Run; returns whether it configured anything. uvicorn's
    access log is turned down because Cloud Run writes its own request log."""
    if not (force or os.environ.get("K_SERVICE")):
        return False
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return True
