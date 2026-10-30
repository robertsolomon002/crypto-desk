"""Settings loaded from the environment and the repo-root `.env` (never committed).

Variable names match `.env.example`. Secrets are `SecretStr` so they never print in reprs or logs.
User LLM keys are NOT settings: they arrive per request in the `X-LLM-Key` header only.
"""

import base64
import binascii
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/desk/config.py -> desk -> src -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]


def issuer_from_publishable_key(key: str) -> str:
    """Decode a publishable key: `pk_test_`/`pk_live_` + unpadded base64 of
    `<frontend-api-host>$` (Clerk docs, "How Clerk works")."""
    prefix, _, encoded = key.partition("_")[2].partition("_")
    if prefix not in ("test", "live") or not encoded:
        raise ValueError("not a Clerk publishable key")
    try:
        host = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError) as e:
        raise ValueError("not a Clerk publishable key") from e
    if not host.endswith("$") or "/" in host:
        raise ValueError("not a Clerk publishable key")
    return "https://" + host.removesuffix("$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Paths (overridable, e.g. in Docker)
    desk_root: Path = REPO_ROOT
    app_env: str = "dev"

    # Database (Neon pooled connection string; local docker-compose Postgres in dev)
    database_url: SecretStr | None = None

    # Auth (Clerk). The issuer is the Frontend API URL; when unset it is decoded from the
    # publishable key (D37). ADMIN_CLERK_IDS (JSON list) are promoted to admin on every request.
    clerk_secret_key: SecretStr | None = None
    clerk_issuer: str | None = None
    vite_clerk_publishable_key: str | None = None
    admin_clerk_ids: list[str] = Field(default_factory=list)

    # LLMs (server keys; Rob's spend is capped in agents/cost.py)
    anthropic_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None

    # Data sources
    fred_api_key: SecretStr | None = None
    coingecko_demo_key: SecretStr | None = None

    # Alerts
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: SecretStr | None = None
    discord_ops_webhook_url: SecretStr | None = None

    # Tracing
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "crypto-desk"
    langsmith_tracing: bool = False

    # Feature flags (Decision 1, Decision 6)
    mco_enabled: bool = True

    # CORS origins for the API (a JSON list in the env, e.g. CORS_ORIGINS=["https://x.pages.dev"])
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:4173"]
    )
    # Extra origins as one regex, matched whole (Starlette's `fullmatch`): the Cloudflare Pages
    # preview deployments, e.g. ^https://[a-z0-9-]+\.crypto-desk\.pages\.dev$ (Stage 2.2).
    cors_origin_regex: str | None = None

    @property
    def clerk_issuer_url(self) -> str | None:
        if self.clerk_issuer:
            return self.clerk_issuer.rstrip("/")
        if self.vite_clerk_publishable_key:
            return issuer_from_publishable_key(self.vite_clerk_publishable_key)
        return None

    @property
    def config_dir(self) -> Path:
        return self.desk_root / "config"

    @property
    def prompts_dir(self) -> Path:
        return self.desk_root / "prompts"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_app_settings(path: Path | None = None) -> dict:
    """`config/settings.yaml` (app-wide, non-secret settings)."""
    path = path or get_settings().config_dir / "settings.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
