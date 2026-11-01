# Using the desk from the Claude desktop app (`desk-mcp`)

`desk-mcp` is the desk's own MCP server. It exposes the same analytics the web app shows as 19
read-only tools, and it runs on your PC over stdio. The in-app agent (Stage 5) uses the same
server. Checked against the MCP docs on 2026-11-01
(https://modelcontextprotocol.io/docs/develop/connect-local-servers).

## Setup on Windows

1. Make sure the backend runs locally: in `C:\Users\rober\code\crypto-desk\backend`,
   `uv sync` once. The server reads `DATABASE_URL` from the repo's `.env` (the Neon pooled
   URL), so the config below needs no secrets.
2. In Claude desktop: **Settings → Developer → Edit Config**. This opens
   `%APPDATA%\Claude\claude_desktop_config.json` and creates it if missing.
3. Add the server (keep any other servers you already have inside `mcpServers`):

   ```json
   {
     "mcpServers": {
       "crypto-desk": {
         "command": "C:\\Users\\rober\\AppData\\Local\\Programs\\Python\\Python312\\Scripts\\uv.exe",
         "args": ["--directory", "C:\\Users\\rober\\code\\crypto-desk\\backend", "run", "desk-mcp"]
       }
     }
   }
   ```

   The full path to `uv.exe` (from `where uv`) avoids depending on the app's PATH; plain
   `"uv"` works too if it is on the PATH the app sees. Paths must be absolute.
4. Quit Claude desktop completely (also from the tray) and start it again. Check it under the
   "Add files, connectors, and more" button at the bottom left of the message box →
   **Connectors** → **Manage connectors** → `crypto-desk`.

Only some groups? Add `"--groups", "market,stats"` to the end of `args`. Groups: `market`,
`cycles`, `stats`, `context`, `views`.

**Troubleshooting:** logs are in `%APPDATA%\Claude\logs` (`mcp.log`, and
`mcp-server-crypto-desk.log` for the server's own stderr). To test the server outside the app,
run `uv --directory C:\Users\rober\code\crypto-desk\backend run desk-mcp` in a terminal: it
should sit waiting for input (Ctrl+C to stop). The first call after Neon has been idle takes a
few seconds while the database wakes up.

## The tools

Every tool takes an optional `as_of` (UTC date): only data known by the end of that day is
used, so you can ask what the desk would have said on a past date. Answers are compact JSON
`{as_of, sources, data}`; returns and distances are fractions (0.05 = +5%), prices USD, dates
UTC.

| Group | Tools |
|---|---|
| market | `list_coins`, `get_ohlcv`, `get_indicators`, `get_regime`, `get_key_levels`, `get_pivots`, `compare_assets` |
| cycles | `get_cycle_comparison`, `get_yoy` |
| stats | `get_seasonality`, `get_return_distribution`, `get_drawdowns`, `get_correlations` |
| context | `get_onchain`, `get_macro`, `get_sentiment`, `get_news`, `get_calendar` |
| views | `get_external_views` (empty until the MCO stage) |

## Ten questions to try

1. What regime is BTC in, and what are its nearest key levels above and below the price?
2. Compare BTC, ETH and SOL over the last 30 days: who is closest to its all-time high, and how
   correlated are they right now?
3. Where is this BTC cycle compared with 2013, 2017 and 2021 at the same number of days since
   the halving?
4. Is BTC's MVRV high or low right now? What does realized price say about the average
   holder's profit?
5. How has November historically gone for BTC, and how consistent is it (share of up years)?
6. Where does last week's BTC return sit in its history of weekly returns?
7. What is the Fear & Greed index today, and how does it compare with its 30-day average?
8. How have the 10-year yield and the dollar index moved over the past year, and is there an
   FOMC meeting or CPI release in the next two weeks?
9. What did the desk show for ETH on 2024-03-12 (use `as_of`): regime, RSI and drawdown?
10. Which of BTC's past drawdowns is the current one most like in depth, and how long did
    those take to recover?

Not financial advice: the tools describe data, they don't make trading decisions.
