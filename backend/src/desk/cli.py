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


@data_app.command("update")
def data_update(
    market: Annotated[
        bool, typer.Option("--market", help="Daily OHLCV (Coinbase + BTC backfill).")
    ] = False,
    coin: Annotated[str | None, typer.Option(help="Only this coin, e.g. BTC.")] = None,
) -> None:
    """Fetch new data into the database (idempotent; safe to re-run)."""
    from desk.data import coinmetrics
    from desk.data import market as mkt
    from desk.data.coins import active_coins, seed_coins
    from desk.db import get_engine, session_factory

    if not market:
        typer.echo("Nothing selected. Use --market (more sources arrive in Stage 1.2).")
        raise typer.Exit(1)
    sessions = session_factory(get_engine())
    with sessions.begin() as session:
        seed_coins(session)
    exchange = mkt.make_exchange()
    with coinmetrics.make_client() as cm:
        with sessions() as session:
            coins = active_coins(session, coin)
        if not coins:
            typer.echo(f"No active coin matches {coin!r}.")
            raise typer.Exit(1)
        for c in coins:
            with sessions.begin() as session:
                added = mkt.update_coin(session, c, exchange, cm)
            summary = ", ".join(f"{src} +{n}" for src, n in added.items())
            typer.echo(f"{c.symbol}: {summary}")


@data_app.command("status")
def data_status(
    issues: Annotated[int, typer.Option(help="How many validation issues to list per coin.")] = 5,
) -> None:
    """Per coin: date range, rows per source, freshness and validation issues."""
    from collections import Counter

    from sqlalchemy import func, select

    from desk.data import market as mkt
    from desk.data.coins import active_coins
    from desk.db import get_engine, session_factory
    from desk.models import CandleDaily

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


@analytics_app.callback()
def _analytics() -> None: ...


@jobs_app.callback()
def _jobs() -> None: ...


@admin_app.callback()
def _admin() -> None: ...
