"""Refresh every data source (shared by `desk data update` and the daily job).

Sources run independently: a failure is recorded and the others still run. A source whose API
key is missing is skipped with a note. Each source commits its own transactions.
"""

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, sessionmaker

SOURCES = ("market", "onchain", "sentiment", "macro", "dominance", "news", "calendar")


@dataclass
class SourceResult:
    name: str
    ok: bool = True
    skipped: bool = False
    lines: list[str] = field(default_factory=list)  # human-readable progress
    error: str | None = None


def _counts(added: dict[str, int]) -> str:
    return ", ".join(f"{k} +{n}" for k, n in added.items()) or "nothing to fetch"


def update_all(
    sessions: sessionmaker[Session],
    now: dt.datetime,
    sources: tuple[str, ...] | list[str] = SOURCES,
    coin: str | None = None,
    echo: Callable[[str, bool], None] = lambda line, err: None,
) -> dict[str, SourceResult]:
    """Run the chosen sources in a fixed order; returns one result per source.

    Raises ValueError if `coin` matches no active coin.
    """
    from desk.config import get_settings
    from desk.data import calendar as cal
    from desk.data import coinmetrics, fred, http
    from desk.data import dominance as dom
    from desk.data import market as mkt
    from desk.data import news as rss
    from desk.data import sentiment as fng
    from desk.data.coins import active_coins, seed_coins

    unknown = set(sources) - set(SOURCES)
    if unknown:
        raise ValueError(f"unknown sources {sorted(unknown)}; expected {SOURCES}")
    settings = get_settings()
    with sessions.begin() as session:
        seed_coins(session)
    with sessions() as session:
        coins = active_coins(session, coin)
    if coin and not coins:
        raise ValueError(f"No active coin matches {coin!r}.")

    def run_market(say: Callable[[str], None]) -> None:
        exchange = mkt.make_exchange()
        with coinmetrics.make_client() as cm:
            for c in coins:
                with sessions.begin() as session:
                    added = mkt.update_coin(session, c, exchange, cm, now)
                say(f"{c.symbol}: {_counts(added)}")

    def run_onchain(say: Callable[[str], None]) -> None:
        with coinmetrics.make_client() as cm:
            for c in coins:
                if c.symbol not in coinmetrics.ASSETS:
                    continue
                with sessions.begin() as session:
                    added = coinmetrics.update_onchain(session, cm, c.symbol, now)
                say(f"{c.symbol}: {_counts(added)}")

    def run_sentiment(say: Callable[[str], None]) -> None:
        with http.make_client() as client, sessions.begin() as session:
            say(f"fng +{fng.update(session, client, now)}")

    def run_macro(say: Callable[[str], None]) -> None:
        if settings.fred_api_key is None:
            raise _Skip("FRED_API_KEY is not set")
        with fred.make_client() as client, sessions.begin() as session:
            added = fred.update(session, client, settings.fred_api_key.get_secret_value(), now)
        say(_counts(added))

    def run_dominance(say: Callable[[str], None]) -> None:
        if settings.coingecko_demo_key is None:
            raise _Skip("COINGECKO_DEMO_KEY is not set")
        key = settings.coingecko_demo_key.get_secret_value()
        with dom.make_client(key) as client, sessions.begin() as session:
            say(_counts(dom.update(session, client)))

    def run_news(say: Callable[[str], None]) -> None:
        with sessions() as session:
            aliases = {c.symbol: c.aliases for c in active_coins(session)}
        with http.make_client() as client, sessions.begin() as session:
            added, failed = rss.update(session, client, aliases, now)
        say(f"headlines +{added}")
        if failed:
            raise RuntimeError(f"no items from: {', '.join(failed)}")

    def run_calendar(say: Callable[[str], None]) -> None:
        with sessions.begin() as session:
            n, deleted = cal.sync(session)
        say(f"{n} events in calendar.yaml, {deleted} stale rows removed")

    runners = {
        "market": run_market, "onchain": run_onchain, "sentiment": run_sentiment,
        "macro": run_macro, "dominance": run_dominance, "news": run_news,
        "calendar": run_calendar,
    }  # fmt: skip
    results: dict[str, SourceResult] = {}
    for name in SOURCES:
        if name not in sources:
            continue
        result = results[name] = SourceResult(name)
        echo(f"{name}:", False)

        def say(line: str, result: SourceResult = result) -> None:
            result.lines.append(line)
            echo(f"  {line}", False)

        try:
            runners[name](say)
        except _Skip as skip:
            result.skipped = True
            say(f"skipped: {skip}")
        except Exception as exc:  # one source failing must not stop the others
            result.ok = False
            result.error = f"{type(exc).__name__}: {exc}"
            echo(f"  FAILED: {result.error}", True)
    return results


class _Skip(Exception):
    pass
