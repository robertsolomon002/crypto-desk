from desk.config import REPO_ROOT, Settings
from desk.db import normalize_url


def test_env_example_parses_to_empty_values() -> None:
    """The template's inline comments must not leak into values; blanks become None."""
    settings = Settings(_env_file=REPO_ROOT / ".env.example")
    assert settings.database_url is None
    assert settings.anthropic_api_key is None
    assert settings.langsmith_project == "crypto-desk"
    assert settings.langsmith_tracing is True


def test_secrets_are_hidden_in_repr() -> None:
    settings = Settings(_env_file=None, anthropic_api_key="sk-ant-canary-123")
    assert "canary" not in repr(settings)
    assert "canary" not in str(settings.model_dump())


def test_normalize_url() -> None:
    assert normalize_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
