"""`desk` CLI (Typer). Command groups fill in stage by stage."""

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="Crypto Desk command line.", no_args_is_help=True)

data_app = typer.Typer(help="Fetch and inspect data (Stages 1.1 and 1.2).", no_args_is_help=True)
analytics_app = typer.Typer(
    help="Run analytics for manual checks (Stage 1.3).", no_args_is_help=True
)
jobs_app = typer.Typer(help="Scheduled jobs (Stages 1.4, 6.1, 7.1).", no_args_is_help=True)
mcp_app = typer.Typer(help="The desk-mcp server.", no_args_is_help=True)
admin_app = typer.Typer(help="Admin tasks.", no_args_is_help=True)
api_app = typer.Typer(help="Run the API and export its OpenAPI schema.", no_args_is_help=True)

app.add_typer(data_app, name="data")
app.add_typer(analytics_app, name="analytics")
app.add_typer(jobs_app, name="jobs")
app.add_typer(mcp_app, name="mcp")
app.add_typer(admin_app, name="admin")
app.add_typer(api_app, name="api")


@app.command()
def version() -> None:
    """Print the backend version."""
    from desk import __version__

    typer.echo(__version__)


@mcp_app.command("serve")
def mcp_serve() -> None:
    """Run desk-mcp over stdio (same as the `desk-mcp` entry point)."""
    from desk.mcp_server.server import main

    main()


@api_app.command("serve")
def api_serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: Annotated[bool, typer.Option("--reload")] = False,
) -> None:
    """Run the API with uvicorn."""
    import uvicorn

    uvicorn.run("desk.api.main:app", host=host, port=port, reload=reload)


@api_app.command("openapi")
def api_openapi(
    out: Annotated[Path, typer.Option(help="Where to write openapi.json.")],
) -> None:
    """Export the OpenAPI schema (the frontend client is generated from it)."""
    from desk.api.main import write_openapi

    write_openapi(out)
    typer.echo(f"wrote {out}")


@data_app.callback()
def _data() -> None: ...


def _counts(added: dict[str, int]) -> str:
    return ", ".join(f"{k} +{n}" for k, n in added.items()) or "nothing to fetch"


@data_app.command("update")
def data_update(
    market: Annotated[
        bool, typer.Option("--market", help="Daily OHLCV (Coinbase + BTC backfill).")
    ] = False,
    onchain: Annotated[
        bool, typer.Option("--onchain", help="Coin Metrics on-chain metrics (BTC, ETH).")
    ] = False,
    sentiment: Annotated[bool, typer.Option("--sentiment", help="Fear & Greed.")] = False,
    macro: Annotated[
        bool, typer.Option("--macro", help="FRED series (needs FRED_API_KEY).")
    ] = False,
    dominance: Annotated[
        bool, typer.Option("--dominance", help="Dominance snapshot (needs COINGECKO_DEMO_KEY).")
    ] = False,
    news: Annotated[bool, typer.Option("--news", help="RSS headlines.")] = False,
    calendar: Annotated[bool, typer.Option("--calendar", help="Sync calendar.yaml.")] = False,
    coin: Annotated[
        str | None, typer.Option(help="Only this coin (market and on-chain), e.g. BTC.")
    ] = None,
) -> None:
    """Fetch new data into the database (idempotent; safe to re-run).

    With no source flags, every source is refreshed. Sources run independently: a failure is
    reported and the others still run; the exit code is 1 if any source failed. A source whose
    API key is missing is skipped with a warning.
    """
    from collections.abc import Callable

    from desk.config import get_settings
    from desk.data import calendar as cal
    from desk.data import coinmetrics, fred, http
    from desk.data import dominance as dom
    from desk.data import market as mkt
    from desk.data import news as rss
    from desk.data import sentiment as fng
    from desk.data.coins import active_coins, seed_coins
    from desk.db import get_engine, session_factory

    chosen = {
        "market": market, "onchain": onchain, "sentiment": sentiment, "macro": macro,
        "dominance": dominance, "news": news, "calendar": calendar,
    }  # fmt: skip
    if not any(chosen.values()):
        chosen = dict.fromkeys(chosen, True)
    settings = get_settings()
    sessions = session_factory(get_engine())
    now = mkt.utc_now()
    with sessions.begin() as session:
        seed_coins(session)
    with sessions() as session:
        coins = active_coins(session, coin)
    if coin and not coins:
        typer.echo(f"No active coin matches {coin!r}.")
        raise typer.Exit(1)

    def run_market() -> None:
        exchange = mkt.make_exchange()
        with coinmetrics.make_client() as cm:
            for c in coins:
                with sessions.begin() as session:
                    added = mkt.update_coin(session, c, exchange, cm)
                typer.echo(f"  {c.symbol}: {_counts(added)}")

    def run_onchain() -> None:
        with coinmetrics.make_client() as cm:
            for c in coins:
                if c.symbol not in coinmetrics.ASSETS:
                    continue
                with sessions.begin() as session:
                    added = coinmetrics.update_onchain(session, cm, c.symbol, now)
                typer.echo(f"  {c.symbol}: {_counts(added)}")

    def run_sentiment() -> None:
        with http.make_client() as client, sessions.begin() as session:
            typer.echo(f"  fng +{fng.update(session, client, now)}")

    def run_macro() -> None:
        if settings.fred_api_key is None:
            typer.echo("  skipped: FRED_API_KEY is not set")
            return
        with fred.make_client() as client, sessions.begin() as session:
            added = fred.update(session, client, settings.fred_api_key.get_secret_value(), now)
        typer.echo(f"  {_counts(added)}")

    def run_dominance() -> None:
        if settings.coingecko_demo_key is None:
            typer.echo("  skipped: COINGECKO_DEMO_KEY is not set")
            return
        key = settings.coingecko_demo_key.get_secret_value()
        with dom.make_client(key) as client, sessions.begin() as session:
            typer.echo(f"  {_counts(dom.update(session, client))}")

    def run_news() -> None:
        with sessions() as session:
            aliases = {c.symbol: c.aliases for c in active_coins(session)}
        with http.make_client() as client, sessions.begin() as session:
            added, failed = rss.update(session, client, aliases, now)
        typer.echo(f"  headlines +{added}")
        if failed:
            raise RuntimeError(f"no items from: {', '.join(failed)}")

    def run_calendar() -> None:
        with sessions.begin() as session:
            n, deleted = cal.sync(session)
        typer.echo(f"  {n} events in calendar.yaml, {deleted} stale rows removed")

    runners: dict[str, Callable[[], None]] = {
        "market": run_market, "onchain": run_onchain, "sentiment": run_sentiment,
        "macro": run_macro, "dominance": run_dominance, "news": run_news,
        "calendar": run_calendar,
    }  # fmt: skip
    failures = []
    for name, run in runners.items():
        if not chosen[name]:
            continue
        typer.echo(f"{name}:")
        try:
            run()
        except Exception as exc:  # one source failing must not stop the others
            failures.append(name)
            typer.echo(f"  FAILED: {type(exc).__name__}: {exc}", err=True)
    if failures:
        typer.echo(f"Failed sources: {', '.join(failures)}", err=True)
        raise typer.Exit(1)


@data_app.command("status")
def data_status(
    issues: Annotated[int, typer.Option(help="How many validation issues to list per coin.")] = 5,
) -> None:
    """Per coin: date range, rows per source, freshness and validation issues; then every
    series, the news table and the next calendar event."""
    from collections import Counter

    from sqlalchemy import func, select

    from desk.data import calendar as cal
    from desk.data import market as mkt
    from desk.data import series
    from desk.data.coins import active_coins
    from desk.db import get_engine, session_factory
    from desk.models import CandleDaily, News

    today = mkt.utc_now().date()
    with session_factory(get_engine())() as session:
        coins = active_coins(session)
        if not coins:
            typer.echo("No coins yet. Run `desk data update --market`.")
            return
        for c in coins:
            counts = session.execute(
                select(CandleDaily.source, func.count())
                .where(CandleDaily.coin == c.symbol)
                .group_by(CandleDaily.source)
            ).all()
            daily = mkt.load_daily(session, c.symbol)
            if daily.empty:
                typer.echo(f"{c.symbol}: no candles")
                continue
            first, last = daily.index.min().date(), daily.index.max().date()
            per_source = ", ".join(f"{src} {n}" for src, n in sorted(counts))
            found = mkt.validate(daily)
            kinds = Counter(i.kind for i in found)
            typer.echo(
                f"{c.symbol}: {first} -> {last} (age {(today - last).days}d) | {per_source}"
                f" | issues: {dict(kinds) or 'none'}"
            )
            for i in found[:issues]:
                typer.echo(f"    {i.date} {i.kind}: {i.detail}")

        typer.echo("series:")
        for key, n, first, last in series.summary(session):
            typer.echo(f"  {key}: {first} -> {last} (age {(today - last).days}d) | {n} rows")
        n_news, newest = session.execute(select(func.count(), func.max(News.published_at))).one()
        typer.echo(f"news: {n_news} headlines, newest {newest or '-'}")
        upcoming = cal.load_events(session, today, days_ahead=30)
        nxt = f"{upcoming[0]['date']} {upcoming[0]['title']}" if upcoming else "none in 30 days"
        typer.echo(f"calendar: next {nxt}")


@analytics_app.callback()
def _analytics() -> None: ...


@jobs_app.callback()
def _jobs() -> None: ...


@admin_app.callback()
def _admin() -> None: ...
