"""Seed the `coins` table from `config/coins.yaml` (core coins plus Rob's watchlist)."""

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from desk.config import get_settings
from desk.models import Coin


def load_coins_yaml(path: Path | None = None) -> list[dict]:
    path = path or get_settings().config_dir / "coins.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    core = [{**c, "is_watchlist": False} for c in cfg.get("core") or []]
    watch = [{**c, "is_watchlist": True} for c in cfg.get("watchlist") or []]
    if len(watch) > cfg.get("max_watchlist", 10):
        raise ValueError(f"watchlist has {len(watch)} coins; max is {cfg.get('max_watchlist')}")
    return core + watch


def seed_coins(session: Session, path: Path | None = None) -> int:
    """Upsert every configured coin (name, aliases, market, watchlist flag); returns the count."""
    coins = load_coins_yaml(path)
    for c in coins:
        values = {
            "symbol": c["symbol"],
            "name": c["name"],
            "aliases": list(c.get("aliases") or []),
            "source_market": c["source_market"],
            "is_watchlist": c["is_watchlist"],
        }
        stmt = insert(Coin).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],
            set_={k: stmt.excluded[k] for k in values if k != "symbol"},
        )
        session.execute(stmt)
    return len(coins)


def active_coins(session: Session, symbol: str | None = None) -> list[Coin]:
    q = select(Coin).where(Coin.active).order_by(Coin.is_watchlist, Coin.symbol)
    if symbol:
        q = q.where(Coin.symbol == symbol.upper())
    return list(session.scalars(q))
