# Crypto Desk

A private, invite-only crypto terminal for a few friends, built entirely on free data and free hosting. It covers:
- charts with indicators and key levels;
- this cycle against past ones, plus seasonality and return stats;
- on-chain and macro data;
- an AI agent that shows exactly which data it used;
- a weekly multi-agent signals brief with a scorecard.

Every number in the app can be opened, filtered and exported in a Data tab.

> **Not financial advice.** This project is for information and education only. It does no trading, holds no exchange keys and places no orders.

![Overview tab: coin cards with price, change, regime, distance from the all-time high and the desk's latest signal; Fear & Greed; macro events; headlines](docs/screenshots/overview.png)

## What's in it

| Tab | What it shows |
|---|---|
| **Overview** | Coin cards (price, 1D/7D/30D change, regime, distance from the all-time high, the desk's latest signal), Fear & Greed, this week's macro events, headlines, and a freshness strip for every source |
| **Charts** | TradingView Lightweight Charts candles (1D, 1W, 4H) with SMA/EMA, the 20-week bull-market support band, Bollinger Bands, RSI, MACD and volume; key levels and swing pivots; ratio mode (ETH/BTC, SOL/BTC) |
| **Cycles** | BTC's cycles aligned by halving, bottom or top, as a multiple of the anchor price or % from the high; day-N table; year over year; ROI since the bottom |
| **Stats** | Monthly-returns heatmap, weekly and day-of-week seasonality, return distributions with this week's percentile, drawdowns, rolling volatility and correlation |
| **On-chain & Macro** | MVRV, price vs realized price, NUPL, active addresses and hash rate (Coin Metrics community data); Fear & Greed history; dominance; four FRED series overlaid on BTC |
| **Agent** | Chat with a LangGraph agent whose tools come from the desk's own MCP server. Every tool call is a card, and "View data" opens the exact result it used. "Ask the desk" runs the multi-agent debate on one coin |
| **Signals** | The weekly brief; per coin a `lean_long` or `flat` call with confidence, levels and rationale; the bull/bear debate behind it; a scorecard against a coin flip and a trend rule |
| **Data** | Every table the app and agent use: filter, page, chart and export as CSV |
| **Settings** | Theme; a guided setup for your own LLM key (OpenRouter recommended) with a one-token test. For the admin: watchlist, invites, users, outside views, usage and cost |
| **MCO** (private) | Summaries of one analyst's free public YouTube videos with his levels per scenario. Private to the deployment and never shown in this README (see [Decision 6](ROADMAP.md#2-decisions-locked-with-rob-2026-10-26)) |

Admins also get a [Health page](docs/OPS.md#health-page-and-the-weekly-summary-stage-81-d53) showing jobs, data freshness, LLM spend against the cap, error counts and free-tier usage.

### Screenshots

The screenshots come from a local copy of the database on 2026-11-04, with MCO switched off. The Agent answer and the Signals week are real runs from that local copy (the production weekly job first runs on 2026-11-09).

| | |
|---|---|
| ![Charts: BTC daily candles, log scale, with 50/200-day SMAs, the 20-week band, key levels and RSI](docs/screenshots/charts.png) | ![Cycles: BTC's 2013, 2017, 2021 and current cycles aligned by halving, with the day-927 table](docs/screenshots/cycles.png) |
| **Charts**: indicators and key levels | **Cycles**: this cycle against 2013, 2017 and 2021 |
| ![Stats: BTC monthly-returns heatmap since 2010, weekly and day-of-week seasonality](docs/screenshots/stats.png) | ![On-chain: MVRV with bands, price vs realized price, NUPL zones, active addresses](docs/screenshots/onchain-macro.png) |
| **Stats**: seasonality and return stats | **On-chain & Macro** |
| ![Agent: a question about BTC's cycle and key levels, two tool-call cards with View data, and the cited answer](docs/screenshots/agent.png) | ![Signals: the weekly brief, per-coin desk views with bull and bear cases, and the signal grid](docs/screenshots/signals.png) |
| **Agent**: every tool call can be opened | **Signals**: the weekly brief and desk calls |
| ![Data: the candles_daily table with filters and CSV export](docs/screenshots/data.png) | ![Settings: guided OpenRouter key setup with a test button](docs/screenshots/settings.png) |
| **Data**: every table, filterable and exportable | **Settings**: bring your own key |
| ![Health (admin): overdue jobs, data freshness per source, server-key spend against the cap, error counts](docs/screenshots/health.png) | ![Overview on a 390 px phone screen with the bottom tab bar](docs/screenshots/overview-phone.png) |
| **Health** (admin) | **Phone** layout |

## How it works

```mermaid
flowchart LR
  subgraph Browser
    UI["React app<br/>(Cloudflare Pages)"]
    KEY[("User LLM key<br/>localStorage")]
  end
  CLERK["Clerk<br/>(auth, invites)"]
  subgraph CloudRun["Cloud Run (min 0, max 2)"]
    API["FastAPI"]
    AGENT["LangGraph agent<br/>and desk"]
    MCP["desk-mcp"]
    AN["analytics<br/>(pure, as_of)"]
  end
  DB[("Neon Postgres")]
  JOBS["GitHub Actions cron<br/>daily / weekly / levelwatch / mco / ops"]
  SRC["Free data: Coinbase (ccxt), Coin Metrics,<br/>FRED, alternative.me, CoinGecko, RSS"]
  LLM["LLM providers"]
  CLAUDE["Claude desktop app"]

  UI -- "JWT + X-LLM-Key" --> API
  KEY -.-> UI
  UI <--> CLERK
  API --> AN
  API --> AGENT --> MCP --> AN
  AN --> DB
  AGENT --> LLM
  JOBS --> SRC
  JOBS --> DB
  CLAUDE -- "stdio" --> MCP
```

- **One analytics core.** Pure Python functions that take an `as_of` date. The API routes and the MCP tools call the same functions, so the agent's numbers match the screen. A look-ahead test checks that results on full data equal results on data truncated at `as_of`.
- **`desk-mcp`.** The desk's own MCP server: 19 read-only tools in 5 groups (market, cycles, stats, context, views). The in-app agent loads it in-process. Each desk analyst gets only its own groups. You can also add it to the Claude desktop app.
- **The multi-agent desk.** A LangGraph `StateGraph` per coin:
  1. a technical and a context analyst run in parallel;
  2. bull and bear each open and rebut, citing the analysts' findings;
  3. a head writes the signal;
  4. a deterministic validator checks it, with one retry.
  The weekly job writes the signals to an append-only, hash-chained table.
- **Bring your own key.** Friends' LLM keys stay in their browser and are sent per request in `X-LLM-Key`. They are never logged, stored or traced, and a canary test checks this. The owner's server key has a hard cap of $8 a month, enforced in code, with three degradation steps on the way.
- **$0 hosting:** Cloudflare Pages, Cloud Run (scales to zero), Neon Free, Clerk Free, and GitHub Actions on a public repo. The jobs write; the API mostly reads.

More: [architecture](docs/ARCHITECTURE.md) · [decisions](docs/DECISIONS.md) · [data sources and their terms](docs/DATA_SOURCES.md) · [operations and runbooks](docs/OPS.md) · [the roadmap](ROADMAP.md) · [what it would take to go public](docs/PUBLIC_READINESS.md).

## Run it locally (Windows PowerShell)

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 24, and Docker Desktop (for a local Postgres).

```powershell
# One-time
Copy-Item .env.example .env            # then fill it in; never commit .env
$env:PYTHONUTF8 = "1"
cd backend; uv sync; cd ..
cd frontend; npm install; npx playwright install chromium; cd ..

# Local Postgres; set DATABASE_URL=postgresql://desk:desk@localhost:5432/desk in .env
docker compose up -d db

# Schema and data (backend/): migrate, then fetch every free source and build the cache
cd backend; uv run desk db upgrade; uv run desk jobs daily; uv run desk data status

# Backend API on http://127.0.0.1:8000 (docs at /docs)
cd backend; uv run desk api serve --reload

# Frontend on http://localhost:5173 (proxies /api to the backend)
cd frontend; npm run dev
```

Sign-in uses [Clerk](https://clerk.com): set `VITE_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` from a free Clerk app, and put your own Clerk user id in `ADMIN_CLERK_IDS`. Optional keys (FRED, CoinGecko Demo, Anthropic, Gemini, Telegram, Discord) are listed in `.env.example`. A source whose key is missing is skipped.

**Checks:**
- `backend/`: `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest`. The Postgres tests also need `$env:TEST_DATABASE_URL="postgresql://desk:desk@localhost:5432/desk"`; they create and drop their own database and never touch Neon.
- `frontend/`: `npm run typecheck`, `npm run lint`, `npm test` and `npm run test:e2e`.

After any API change: run `uv run desk api openapi --out ../frontend/openapi.json` in `backend/`, then `npm run gen:api` in `frontend/`. CI fails if either is stale.

## Use the desk from Claude

`desk-mcp` runs on your machine over stdio and reads the same database:

```json
{
  "mcpServers": {
    "crypto-desk": {
      "command": "uv",
      "args": ["--directory", "C:\\path\\to\\crypto-desk\\backend", "run", "desk-mcp"]
    }
  }
}
```

Add it in Claude desktop under **Settings → Developer → Edit Config**, then restart the app. Then ask things like "Where is BTC against its key levels?" or "How does this cycle compare with 2017 by halving?". To expose only some tool groups, add `"--groups", "market,stats"`. Full guide: [docs/USING_WITH_CLAUDE.md](docs/USING_WITH_CLAUDE.md).

## Layout

- `backend/`: Python 3.12 (uv), FastAPI, SQLAlchemy, Alembic, LangGraph, the `desk` CLI and the `desk-mcp` server
- `frontend/`: React, TypeScript, Vite, Tailwind, shadcn/ui, Lightweight Charts, ECharts
- `config/`: coins, cycle anchors, feeds, FRED series, models, prices and app settings
- `prompts/`: versioned prompts for the agent, the desk, the brief writer and video extraction
- `docs/`: decisions, architecture, data sources, operations and the build log
- `.github/workflows/`: CI, deploys and the scheduled jobs

## Credits and data terms

- Price charts use [TradingView Lightweight Charts](https://www.tradingview.com/lightweight-charts/); its attribution is kept in the app.
- Data comes from:
  - [Coinbase](https://www.coinbase.com) through [ccxt](https://github.com/ccxt/ccxt);
  - [Coin Metrics community data](https://docs.coinmetrics.io/packages/coin-metrics-community-data) (Creative Commons BY-NC);
  - [alternative.me](https://alternative.me/crypto/fear-and-greed-index/) (Fear & Greed);
  - [CoinGecko](https://www.coingecko.com) (dominance; data provided by CoinGecko);
  - [FRED](https://fred.stlouisfed.org);
  - the CoinDesk, Cointelegraph, Decrypt and The Block RSS feeds (titles and links only).
- This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.
- Each source's terms are in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) and [docs/PUBLIC_READINESS.md](docs/PUBLIC_READINESS.md).

## License

MIT for the code. No market data or third-party content is included in this repository.
