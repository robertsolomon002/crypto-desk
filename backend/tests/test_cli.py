from typer.testing import CliRunner

from desk import __version__
from desk.cli import app

runner = CliRunner()


def test_help_lists_command_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in ("data", "analytics", "jobs", "mcp", "admin", "api"):
        assert group in result.output


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_openapi_export(tmp_path) -> None:
    out = tmp_path / "openapi.json"
    result = runner.invoke(app, ["api", "openapi", "--out", str(out)])
    assert result.exit_code == 0
    assert "/api/health" in out.read_text(encoding="utf-8")
