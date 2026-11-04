"""Operations (Stage 8.1, D53): the Health report, error counts, structured logs, the weekly
ops summary and backups."""

from desk.config import load_app_settings


def ops_settings() -> dict:
    return load_app_settings().get("ops") or {}
