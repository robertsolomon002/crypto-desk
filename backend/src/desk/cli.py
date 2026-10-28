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


@analytics_app.callback()
def _analytics() -> None: ...


@jobs_app.callback()
def _jobs() -> None: ...


@admin_app.callback()
def _admin() -> None: ...
