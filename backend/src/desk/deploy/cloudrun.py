"""The Cloud Run service's plain (non-secret) environment, as a `--env-vars-file` YAML (D38).

Secrets are not here: Cloud Run reads them from Secret Manager (`--set-secrets`). The JSON lists
contain commas, which `--set-env-vars` would split, hence a file. Values are validated so a typo
in a repository variable fails the deploy instead of locking everyone out.
"""

import json
import re
from urllib.parse import urlsplit

import yaml


class EnvError(ValueError):
    pass


def _origin(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/"):
        raise EnvError(f"not an https origin: {value!r}")
    if parts.query or parts.fragment or parts.username:
        raise EnvError(f"not an https origin: {value!r}")
    return f"https://{parts.netloc}"


def service_env(
    *,
    cors_origins: list[str],
    cors_origin_regex: str | None,
    clerk_publishable_key: str,
    admin_clerk_ids: list[str],
    mco_enabled: bool = True,
) -> dict[str, str]:
    origins = [_origin(o) for o in cors_origins]
    if not origins:
        raise EnvError("at least one CORS origin is needed (the Pages production URL)")
    if cors_origin_regex:
        try:
            re.compile(cors_origin_regex)
        except re.error as e:
            raise EnvError(f"bad CORS origin regex: {e}") from None
        if not (cors_origin_regex.startswith("^https://") and cors_origin_regex.endswith("$")):
            raise EnvError("the CORS origin regex must be anchored: ^https://...$")
    if not re.fullmatch(r"pk_(test|live)_[A-Za-z0-9+/=]+", clerk_publishable_key):
        raise EnvError("not a Clerk publishable key")
    for clerk_id in admin_clerk_ids:
        if not re.fullmatch(r"user_[A-Za-z0-9]+", clerk_id):
            raise EnvError(f"not a Clerk user id: {clerk_id!r}")
    env = {
        "APP_ENV": "prod",
        "CORS_ORIGINS": json.dumps(origins),
        "VITE_CLERK_PUBLISHABLE_KEY": clerk_publishable_key,
        "ADMIN_CLERK_IDS": json.dumps(admin_clerk_ids),
        "MCO_ENABLED": "true" if mco_enabled else "false",
    }
    if cors_origin_regex:
        env["CORS_ORIGIN_REGEX"] = cors_origin_regex
    return env


def to_yaml(env: dict[str, str]) -> str:
    # Every value a string, as Cloud Run requires
    return yaml.safe_dump({k: str(v) for k, v in env.items()}, sort_keys=True)
