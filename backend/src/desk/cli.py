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
notify_app = typer.Typer(help="Send alerts (Telegram, Discord).", no_args_is_help=True)

app.add_typer(data_app, name="data")
app.add_typer(analytics_app, name="analytics")
app.add_typer(jobs_app, name="jobs")
app.add_typer(mcp_app, name="mcp")
app.add_typer(admin_app, name="admin")
app.add_typer(api_app, name="api")
app.add_typer(notify_app, name="notify")


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
    from desk.data import market as mkt
    from desk.data.update import SOURCES, update_all
    from desk.db import get_engine, session_factory

    flags = {"market": market, "onchain": onchain, "sentiment": sentiment, "macro": macro,
             "dominance": dominance, "news": news, "calendar": calendar}  # fmt: skip
    chosen = [s for s in SOURCES if flags[s]] or list(SOURCES)
    try:
        results = update_all(
            session_factory(get_engine()),
            mkt.utc_now(),
            chosen,
            coin,
            echo=lambda line, err: typer.echo(line, err=err),
        )
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from None
    failures = [name for name, r in results.items() if not r.ok]
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


def _print_result(obj, tail: int, indent: str = "") -> None:
    """Human-readable output for `desk analytics show`: frames as tables, the rest as fields."""
    import dataclasses

    import pandas as pd

    if isinstance(obj, pd.DataFrame | pd.Series):
        shown = obj.tail(tail) if tail else obj
        with pd.option_context("display.width", 200, "display.max_columns", 30):
            text = shown.to_string()
        typer.echo("\n".join(indent + line for line in text.splitlines()))
        if tail and len(obj) > tail:
            typer.echo(f"{indent}({len(obj)} rows, last {tail} shown; --tail 0 for all)")
    elif isinstance(obj, list) and obj and dataclasses.is_dataclass(obj[0]):
        _print_result(pd.DataFrame([dataclasses.asdict(x) for x in obj]), tail, indent)
    elif dataclasses.is_dataclass(obj):
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            if isinstance(value, pd.DataFrame | pd.Series | list) and not (
                isinstance(value, list) and len(value) < 8
            ):
                typer.echo(f"{indent}{f.name}:")
                _print_result(value, tail, indent + "  ")
            else:
                typer.echo(f"{indent}{f.name}: {value}")
    else:
        typer.echo(f"{indent}{obj}")


@analytics_app.command("list")
def analytics_list() -> None:
    """Every analytics function with its parameters."""
    from desk.analytics.registry import SPECS

    for spec in SPECS:
        params = ", ".join(f"{k}={v}" for k, v in spec.params.items())
        typer.echo(f"{spec.name:22} {spec.description}" + (f" [{params}]" if params else ""))


@analytics_app.command("show")
def analytics_show(
    function: Annotated[str, typer.Argument(help="Name from `desk analytics list`.")],
    coin: Annotated[str, typer.Argument(help="Coin symbol, e.g. BTC.")],
    as_of: Annotated[
        str | None, typer.Option("--as-of", help="UTC date YYYY-MM-DD (default: latest).")
    ] = None,
    param: Annotated[
        list[str] | None, typer.Option("--param", help="Parameter as key=value; repeatable.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON instead of tables.")] = False,
    tail: Annotated[int, typer.Option(help="Rows shown per table (0 = all).")] = 15,
    cached: Annotated[
        bool, typer.Option("--cached", help="Read through analytics_cache (prints JSON).")
    ] = False,
) -> None:
    """Run one analytics function on the database's data, for manual checks."""
    import datetime as dt
    import json

    from desk.analytics import cache, registry
    from desk.analytics.inputs import load_inputs
    from desk.data.coins import active_coins
    from desk.db import get_engine, session_factory

    day = dt.date.fromisoformat(as_of) if as_of else None
    params = dict(p.split("=", 1) for p in param or [])
    spec = registry.get(function)
    sessions = session_factory(get_engine())
    if cached:
        with sessions.begin() as session:
            result, hit = cache.get_or_compute(session, function, coin, day, **params)
        typer.echo(f"({'cache hit' if hit else 'computed and cached'})", err=True)
        typer.echo(json.dumps(result, indent=1))
        return
    with sessions() as session:
        coins = [c.symbol for c in active_coins(session)] if spec.needs == "all_coins" else [coin]
        inputs = load_inputs(session, coins, day)
    if as_json:
        typer.echo(json.dumps(registry.run_json(function, inputs, coin, day, **params), indent=1))
    else:
        _print_result(registry.run(function, inputs, coin, day, **params), tail)


@analytics_app.command("verify-anchors")
def analytics_verify_anchors() -> None:
    """Compare cycle anchors with Coin Metrics (or Bitstamp for the 2013 cycle). Network."""
    from desk.analytics.cycles import load_config
    from desk.analytics.verify import MAX_DAYS, MAX_PRICE_DIFF, verify_anchors
    from desk.data import market
    from desk.db import get_engine, session_factory

    config = load_config().coins
    with session_factory(get_engine())() as session:
        daily = {c: market.load_daily(session, c) for c in config}
    checks = verify_anchors(daily, config)
    for c in checks:
        ref = f"{c.ref_date} {c.ref_price:,.2f}" if c.ref_price is not None else "no data"
        diff = (
            f"{(c.date - c.ref_date).days:+d}d {c.price / c.ref_price - 1:+.2%}"
            if c.ref_price is not None and c.ref_date is not None
            else "-"
        )
        on_date = f"{c.ref_on_date:,.2f}" if c.ref_on_date is not None else "-"
        tie = " near-tie" if c.near_tie and c.ref_date != c.date else ""
        typer.echo(
            f"{'ok  ' if c.ok else 'FAIL'} {c.coin} {c.cycle} {c.kind:6} {c.date} "
            f"{c.price:>12,.2f} ({c.source}) vs {c.ref_source} {ref} [{diff}]; "
            f"{c.ref_source} on {c.date}: {on_date}{tie}"
        )
    failed = [c for c in checks if not c.ok]
    typer.echo(f"{len(checks) - len(failed)}/{len(checks)} within {MAX_PRICE_DIFF:.0%} and "
               f"{MAX_DAYS} days (or a near-tie)")  # fmt: skip
    if failed:
        raise typer.Exit(1)


@analytics_app.command("refresh-cache")
def analytics_refresh_cache() -> None:
    """Precompute the heavy analytics for every active coin into analytics_cache."""
    from desk.analytics import cache
    from desk.db import get_engine, session_factory

    with session_factory(get_engine()).begin() as session:
        counts = cache.refresh(session)
    typer.echo(", ".join(f"{k} {v}" for k, v in counts.items()))


@jobs_app.callback()
def _jobs() -> None: ...


@jobs_app.command("daily")
def jobs_daily(
    summary_file: Annotated[
        Path | None, typer.Option(help="Also write the summary here (read by the alert step).")
    ] = None,
    cache: Annotated[bool, typer.Option(help="Refresh the analytics cache.")] = True,
) -> None:
    """Daily job: update every source, check freshness, refresh the cache, record job_runs.

    Exit code 1 if anything failed; the workflow then sends an ops_failure alert."""
    from desk.db import get_engine, session_factory
    from desk.jobs.daily import run_daily

    result = run_daily(
        session_factory(get_engine()),
        refresh_cache=cache,
        echo=lambda line, err: typer.echo(line, err=err),
    )
    summary = result.summary()
    typer.echo("")
    typer.echo(summary)
    if summary_file:
        summary_file.write_text(summary + "\n", encoding="utf-8")
    if result.status != "success":
        raise typer.Exit(1)


@notify_app.callback()
def _notify() -> None: ...


@notify_app.command("send")
def notify_send(
    event: Annotated[str, typer.Argument(help="Event name from settings.yaml `alerts`.")],
    title: Annotated[str, typer.Option(help="Short title.")],
    body: Annotated[str, typer.Option(help="Message body.")] = "",
    body_file: Annotated[
        Path | None, typer.Option(help="Read the body from a file (used by workflows).")
    ] = None,
    url: Annotated[str | None, typer.Option(help="Link to include (http or https).")] = None,
) -> None:
    """Send one alert to the event's channels. Exit 1 if a configured channel failed."""
    from desk.notify import Alert, send

    if body_file is not None:
        body = (
            body_file.read_text(encoding="utf-8").strip()
            if body_file.exists()
            else "No summary was written; see the run log."
        )
    status = send(Alert(event, title, body, url))
    for channel, state in status.items():
        typer.echo(f"{channel}: {state}")
    if not status:
        typer.echo(f"No channels are routed for {event!r} in settings.yaml.")
    if any(state.startswith("failed") for state in status.values()):
        raise typer.Exit(1)


@notify_app.command("test")
def notify_test() -> None:
    """Send a test message to every configured channel (one per channel)."""
    from desk.notify import Alert, send

    routes = {"ops_failure": ["telegram", "discord_ops"], "brief_ready": ["discord"]}
    failed = False
    for event, channels in routes.items():
        alert = Alert(event, "Test message", "Alerts are configured correctly.")
        for channel, state in send(alert, routes={event: channels}).items():
            typer.echo(f"{channel}: {state}")
            failed |= state.startswith("failed")
    if failed:
        raise typer.Exit(1)


@admin_app.callback()
def _admin() -> None: ...
