"""Settings loaded from the environment and the repo-root `.env` (never committed).

Variable names match `.env.example`. Secrets are `SecretStr` so they never print in reprs or logs.
User LLM keys are NOT settings: they arrive per request in the `X-LLM-Key` header only.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/desk/config.py -> desk -> src -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]


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

    # Auth (Clerk)
    clerk_secret_key: SecretStr | None = None

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

    @property
    def config_dir(self) -> Path:
        return self.desk_root / "config"

    @property
    def prompts_dir(self) -> Path:
        return self.desk_root / "prompts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
