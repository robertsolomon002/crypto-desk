"""desk-mcp (Stage 4.2): tool groups, schemas, as_of on every tool, and stdio round trips with
the official SDK client against the seeded API database (never DATABASE_URL from .env)."""

import json
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from desk.mcp_server import tools
from desk.mcp_server.server import build_server, parse_groups
from desk.mcp_server.tools import GROUPS, TOOLS, rounded, table

EXPECTED = {
    "market": {"list_coins", "get_ohlcv", "get_indicators", "get_regime", "get_key_levels",
               "get_pivots", "compare_assets"},
    "cycles": {"get_cycle_comparison", "get_yoy"},
    "stats": {"get_seasonality", "get_return_distribution", "get_drawdowns", "get_correlations"},
    "context": {"get_onchain", "get_macro", "get_sentiment", "get_news", "get_calendar"},
    "views": {"get_external_views"},
}  # fmt: skip

# Minimal arguments per tool for the seeded database (BTC from 2011, last day 2026-10-27).
ARGS = {
    "get_ohlcv": {"coin": "BTC"},
    "get_indicators": {"coin": "BTC"},
    "get_regime": {"coin": "BTC"},
    "get_key_levels": {"coin": "BTC"},
    "get_pivots": {"coin": "BTC"},
    "compare_assets": {"coins": ["BTC", "ETH"]},
    "get_cycle_comparison": {"coin": "BTC"},
    "get_yoy": {"coin": "BTC"},
    "get_seasonality": {"coin": "BTC", "period": "monthly"},
    "get_return_distribution": {"coin": "BTC"},
    "get_drawdowns": {"coin": "BTC"},
    "get_correlations": {"coin": "BTC"},
    "get_onchain": {"coin": "BTC"},
    "get_news": {},
    "get_external_views": {"coin": "BTC"},
}
AS_OF = "2026-10-20"


async def test_groups_select_tools() -> None:
    assert {t.group for t in TOOLS} == set(GROUPS)
    for group, names in EXPECTED.items():
        listed = {t.name for t in await build_server(group).list_tools()}
        assert listed == names
    both = {t.name for t in await build_server("cycles,views").list_tools()}
    assert both == EXPECTED["cycles"] | EXPECTED["views"]
    assert len(await build_server().list_tools()) == sum(len(v) for v in EXPECTED.values())
    with pytest.raises(ValueError, match="unknown groups"):
        parse_groups("market,trading")
    with pytest.raises(ValueError):
        parse_groups(" , ")


async def test_every_tool_has_as_of_a_description_and_is_read_only() -> None:
    for t in await build_server().list_tools():
        props = t.inputSchema["properties"]
        assert "as_of" in props, t.name
        assert "as_of" not in t.inputSchema.get("required", []), t.name
        assert "Returns" in (t.description or ""), t.name
        assert t.annotations and t.annotations.readOnlyHint is True
        assert t.outputSchema is None  # plain compact JSON text, no structured duplicate


def test_rounding_and_tables() -> None:
    assert rounded({"a": [77423.98123, 0.0959920944, float("nan")], "b": "x", "c": 3}) == {
        "a": [77424.0, 0.0959921, None], "b": "x", "c": 3}  # fmt: skip
    recs = [{"date": f"2026-10-{d}", "v": d} for d in (10, 11, 12)]
    assert table(recs, 2) == {"columns": ["date", "v"], "rows": [["2026-10-11", 11],
                              ["2026-10-12", 12]], "total_rows": 3}  # fmt: skip
    assert table([], 5) == {"columns": [], "rows": [], "total_rows": 0}


@pytest.fixture
def seeded(api_sessions, monkeypatch):
    monkeypatch.setattr(tools, "_sessions", lambda: api_sessions)
    return api_sessions


@pytest.mark.parametrize("name", sorted(n for names in EXPECTED.values() for n in names))
def test_every_tool_honours_as_of(seeded, name) -> None:
    fn = getattr(tools, name)
    full = json.loads(fn(**ARGS.get(name, {})))
    cut = json.loads(fn(**ARGS.get(name, {}), as_of=AS_OF))
    assert set(cut) == {"as_of", "sources", "data"}
    if name == "get_calendar":
        assert cut["as_of"] == AS_OF  # the window is centred on as_of
    elif name != "get_external_views":
        assert cut["as_of"] is not None and cut["as_of"] <= AS_OF, cut["as_of"]
        assert full["as_of"] >= cut["as_of"]
    # No date anywhere in the cut answer is after as_of (calendar looks ahead on purpose).
    if name not in {"get_calendar", "get_cycle_comparison"}:
        text = json.dumps(cut["data"])
        dates = [text[i + 1 : i + 11] for i in range(len(text)) if text[i : i + 3] == '"20']
        assert all(d <= AS_OF for d in dates if d[4:5] == "-"), name


def test_as_of_cuts_news_and_rejects_the_future(seeded) -> None:
    titles = [h["title"] for h in json.loads(tools.get_news(as_of="2026-10-27"))["data"]
              ["headlines"]]  # fmt: skip
    assert "Tomorrow's headline" not in titles and "Ether upgrade lands" in titles
    with pytest.raises(ValueError, match="future"):
        tools.get_ohlcv("BTC", as_of="2999-01-01")
    with pytest.raises(ValueError, match="unknown coin"):
        tools.get_ohlcv("NOPE")
    with pytest.raises(ValueError, match="UTC date"):
        tools.get_macro(as_of="last week")


def test_macro_applies_release_lags(seeded) -> None:
    # M2SL for 2026-09-01 is known only 60 days later (D32).
    m2 = next(s for s in json.loads(tools.get_macro(as_of="2026-10-20"))["data"]
              if s["id"] == "M2SL")  # fmt: skip
    assert m2["latest"]["date"] <= "2026-08-21"


def _params(groups: str, url: str) -> StdioServerParameters:
    env = {**os.environ, "DATABASE_URL": url, "PYTHONUTF8": "1"}
    args = ["-m", "desk.mcp_server.server", "--groups", groups]
    return StdioServerParameters(command=sys.executable, args=args, env=env)


async def test_stdio_round_trip(api_engine, api_sessions) -> None:
    url = api_engine.url.render_as_string(hide_password=False)
    async with (
        stdio_client(_params("market,context", url)) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        listed = {t.name for t in (await session.list_tools()).tools}
        assert listed == EXPECTED["market"] | EXPECTED["context"]

        result = await session.call_tool(
            "get_ohlcv", {"coin": "BTC", "limit": 3, "as_of": "2026-10-01"}
        )
        assert not result.isError
        body = json.loads(result.content[0].text)
        assert body["as_of"] == "2026-10-01"
        assert [r[0][:10] for r in body["data"]["rows"]] == [
            "2026-09-29", "2026-09-30", "2026-10-01"]  # fmt: skip

        bad = await session.call_tool("get_ohlcv", {"coin": "NOPE"})
        assert bad.isError and "unknown coin" in bad.content[0].text

        hidden = await session.call_tool("get_yoy", {"coin": "BTC"})  # cycles group is off
        assert hidden.isError and "Unknown tool" in hidden.content[0].text


async def test_stdio_rejects_unknown_groups() -> None:
    with pytest.raises(Exception):  # noqa: B017  # the server exits before the handshake
        async with (
            stdio_client(_params("trading", "postgresql://unused/x")) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
