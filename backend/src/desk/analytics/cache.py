"""`analytics_cache`: stored JSON results of registry functions, invalidated by a data
fingerprint (D35).

A row is keyed by (function name, hash of name + coin + params, as_of); `as_of` defaults to the
coin's last candle date. The row also stores a fingerprint of the input data:
`(max(date), count, sum(close))` of the candles it reads plus the same for on-chain series.
A new day or a late correction changes the fingerprint, so the next read recomputes and
overwrites the row.
"""

import datetime as dt
import hashlib
import json
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from desk.analytics import registry
from desk.analytics.inputs import load_inputs
from desk.models import AnalyticsCache, CandleDaily, Coin, SeriesPoint

PRUNE_DAYS = 30


def params_hash(name: str, coin: str, params: dict[str, Any]) -> str:
    raw = json.dumps({"name": name, "coin": coin, "params": params}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _coins_for(session: Session, spec: registry.Spec, coin: str) -> list[str]:
    if spec.needs != "all_coins":
        return [coin]
    return list(session.scalars(select(Coin.symbol).where(Coin.active).order_by(Coin.symbol)))


def fingerprint(session: Session, spec: registry.Spec, coins: list[str]) -> str:
    parts = []
    for c in coins:
        row = session.execute(
            select(func.max(CandleDaily.date), func.count(), func.sum(CandleDaily.close))
            .where(CandleDaily.coin == c)
        ).one()  # fmt: skip
        parts.append(f"{c}:{row[0]}:{row[1]}:{row[2]!r}")
        if spec.needs == "onchain":
            row = session.execute(
                select(func.max(SeriesPoint.date), func.count(), func.sum(SeriesPoint.value))
                .where(SeriesPoint.key.like(f"cm:{c}:%"))
            ).one()  # fmt: skip
            parts.append(f"cm:{c}:{row[0]}:{row[1]}:{row[2]!r}")
    return "|".join(parts)


def get_or_compute(
    session: Session, name: str, coin: str, as_of: dt.date | None = None, **params: Any
) -> tuple[Any, bool]:
    """The JSON result and whether it came from the cache. Commits nothing; the caller does."""
    spec = registry.get(name)
    coin = coin.upper()
    resolved = registry.resolve_params(spec, params)
    coins = _coins_for(session, spec, coin)
    key_as_of = as_of or session.scalar(
        select(func.max(CandleDaily.date)).where(CandleDaily.coin == coin)
    )
    if key_as_of is None:
        raise ValueError(f"no candles for {coin}")
    phash = params_hash(name, coin, resolved)
    fp = fingerprint(session, spec, coins)
    row = session.scalar(
        select(AnalyticsCache).where(
            AnalyticsCache.key == name,
            AnalyticsCache.params_hash == phash,
            AnalyticsCache.as_of == key_as_of,
        )
    )
    if row is not None and row.data.get("fingerprint") == fp:
        return row.data["result"], True

    inputs = load_inputs(session, coins, as_of)
    result = registry.run_json(name, inputs, coin, as_of, **resolved)
    data = {"fingerprint": fp, "coin": coin, "params": resolved, "result": result}
    stmt = insert(AnalyticsCache).values(key=name, params_hash=phash, as_of=key_as_of, data=data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["key", "params_hash", "as_of"],
        set_={"data": stmt.excluded.data, "computed_at": func.now()},
    )
    session.execute(stmt)
    return result, False


def refresh(session: Session, coins: list[str] | None = None) -> dict[str, int]:
    """Precompute every heavy function (default params, latest data) for the active coins and
    prune rows not recomputed for 30 days. Returns {"computed", "cached", "pruned"}."""
    from desk.data.coins import active_coins

    symbols = coins or [c.symbol for c in active_coins(session)]
    inputs = load_inputs(session, symbols)
    counts = {"computed": 0, "cached": 0}
    for spec in registry.SPECS:
        if not spec.heavy:
            continue
        modes = ["halving", "bottom", "top"] if "mode" in spec.params else [None]
        for coin in symbols:
            if not spec.supports(inputs, coin) or inputs.daily[coin].empty:
                continue
            for mode in modes:
                params = {"mode": mode} if mode else {}
                _, hit = get_or_compute(session, spec.name, coin, **params)
                counts["cached" if hit else "computed"] += 1
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=PRUNE_DAYS)
    pruned = session.execute(
        delete(AnalyticsCache).where(AnalyticsCache.computed_at < cutoff)
    ).rowcount
    return {**counts, "pruned": pruned}
