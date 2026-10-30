# Crypto Desk Roadmap (v3): a personal crypto terminal for Rob and friends

**Prepared for:** Rob (built by Claude Code, one substage per session)
**Date:** 2026-10-26. v3 replaces v1 and v2. The project changed from a weekly forecasting study into a multi-tab web app, so everything earlier is superseded.
**Status:** Stage 0 done (accounts, scaffold, verification spike; findings in `docs/DATA_SOURCES.md`, D20 to D30). Stage 1.1 done (schema, migration `0001`, daily market data; D31). Stage 1.2 done (context, on-chain, macro, news and calendar data; D32). Stage 1.3 done (analytics engine, look-ahead test, cycle anchors verified, cache; D33 to D35). Stage 1.4 done (daily job, alerts, `daily.yml`; D36; first GitHub run 2026-10-29 succeeded and all alert channels delivered). Stage 1 complete. Stage 2.1 done (read API, Clerk auth with roles in the DB, Data tab routes, key redaction, rate limit, ETags; D37). Stage 2.2 done (Cloud Run behind Workload Identity Federation with smoke-tested no-traffic revisions, Cloudflare Pages at `crypto-desk-a9f.pages.dev` with previews, CORS, CSP, `docs/OPS.md`; D38; first deploys 2026-10-30 passed every smoke check). Stage 2 complete. Next: Stage 3.1 (plan mode). `ADMIN_CLERK_IDS` waits for Rob's first login in Stage 3.1 (no Clerk user exists yet; it is now a GitHub repo variable, OPS.md), and the $1 GCP budget alert is a [Rob] step.
**Repo:** `robertsolomon002/crypto-desk` (public code; all data and MCO-derived content stay private in the database). Local folder `C:\Users\rober\code\crypto-desk`.

**What it is:** a private, invite-only web app in the spirit of a paid crypto "terminal", built on free data. It has these tabs:
- **Overview**
- **Charts** (indicators and levels)
- **Cycles** (this cycle vs past cycles)
- **Stats** (seasonality and distributions)
- **On-chain & Macro**
- **MCO** (daily summaries of More Crypto Online's YouTube videos, with his levels and approximate wave counts on our charts)
- **Agent** (chat with a LangGraph agent that uses Rob's own MCP tools and shows exactly which data it used)
- **Signals** (a weekly multi-agent brief, signals and a scorecard)
- **Data** (browse and export every table the app and the agent use)
- **Settings**

**Users:** Rob (admin) and a few invited friends (members). Friends bring their own LLM key, ideally one OpenRouter key. The design must not block opening it up later ("full-fledged").
**Scope:** BTC, ETH and SOL plus a watchlist managed by Rob. Desktop first, usable on a phone.
**Budget:**
- **Hosting:** $0, free tiers only (Section 6).
- **Rob's LLM spend:** estimated $2 to $4 per month, hard cap **$8 per month** enforced in code.
- **Friends:** pay for their own agent use through their own keys.

> **Start here (Claude Code or any agent).** Read Sections 1 to 10 before any work. Do exactly **one substage per session**, in order. Substages marked **(plan mode)** start in plan mode: present the plan and wait for Rob's OK before writing code. After each substage: run the tests it names plus lint (`ruff` for the backend, `eslint` and `tsc --noEmit` for the frontend), commit with `Stage X.Y: <summary>`, tick the box in Section 14, and add one line to `docs/LOG.md`. Steps marked **[Rob]** need a human; stop and tell Rob exactly what to do. **Never guess library, API, quota or pricing behavior** (ccxt, Coin Metrics, FRED, CoinGecko, YouTube, Gemini, Clerk, Cloud Run, Neon, Cloudflare Pages, Lightweight Charts, LangGraph, LangChain, MCP SDK, OpenRouter). Check official docs or the installed source, and record what you found in `docs/DATA_SOURCES.md` or `docs/DECISIONS.md`. If reality disagrees with this roadmap, reality wins: update the roadmap in the same commit and say so.

---

## 1. Product overview (plain English)

Rob trades large-cap crypto over days to weeks and watches MCO (More Crypto Online) for Elliott wave analysis. MCO's own web terminal is paywalled. Rob wants his own terminal, for himself and a few friends, that pulls together:
- charts with indicators;
- cycle and year comparisons;
- seasonality and stats;
- on-chain and macro data;
- digests of MCO's latest public videos;
- an AI agent you can ask questions;
- a weekly signals brief.

Every number the app shows, and every number the agent uses, can be inspected in a **Data** tab. Nothing is a black box.

**Tabs and what each one shows:**

| Tab | Contents | Priority |
|---|---|---|
| **Overview** | Coin cards (price, 1d/7d/30d change, regime, distance from ATH, latest signal, MCO's current bias), Fear & Greed, macro events this week, top headlines, data freshness | v1 |
| **Charts** | TradingView Lightweight Charts candles (1D, 1W; 4H resampled from Coinbase 1h, D22). Indicators: SMA/EMA (20/50/200), the 20-week SMA "bull market support band", Bollinger Bands, RSI, MACD, volume. Overlays: key levels, zigzag swing pivots, MCO levels and approved MCO wave labels. Ratio mode (SOL/BTC, ETH/BTC) | v1 |
| **Cycles** | BTC (and ETH where data allows) cycle overlays: the current cycle vs 2013, 2017 and 2021, aligned by **halving**, **cycle bottom** or **cycle top**; y-axis as a multiple of the anchor price (log) or % drawdown from ATH. "Day N of cycle" stats table. Year-over-year overlay (each year from Jan 1, normalized). ROI-since-bottom table | v1 |
| **Stats** | Monthly returns heatmap (year × month), weekly and day-of-week seasonality, return distribution with the current week's percentile, drawdown chart, rolling volatility, rolling correlation between coins | v1 |
| **On-chain & Macro** | BTC/ETH: MVRV, realized price vs price (derived, D21), NUPL (derived), active addresses, hash rate (BTC), from free Coin Metrics community data. Fear & Greed history. BTC dominance (daily snapshots from Stage 1.2 on; no free history, D23). Macro from FRED: broad dollar index, 10-year yield, fed funds rate, M2, each overlayable on BTC | v1.1 |
| **Agent** | Chat with a LangGraph agent using `desk-mcp` tools. Model picker. Every tool call is shown as a card, and "View data" opens the exact result in the Data tab. Optional "Ask the desk" mode runs the multi-agent desk (Section 3.3). Friends use their own key | v1.1 |
| **MCO** | Feed of daily summaries of MCO's latest public YouTube videos: per coin, bias, primary and alternative scenario, key levels, invalidation and targets, with a link to the video. Bias timeline vs price. MCO levels and approved wave labels can be toggled on the Charts tab. Admin review queue for wave labels | v1.2 |
| **Signals** | Weekly brief from the multi-agent desk; current signals per coin (lean long or flat, confidence, entry zone, invalidation, target); scorecard comparing the desk, two baselines and MCO's bias; alerts to Telegram and Discord | v1.3 |
| **Data** | Browse every table (prices, indicators, cycles, stats, on-chain, macro, news, MCO extracts, agent snapshots, signals), filter, preview as a chart, export CSV, freshness and status | v1 |
| **Settings** | Own LLM key (OpenRouter, Anthropic or OpenAI) with a guided setup and a "test key" button; default model; theme. Admin only: invites, watchlist, usage and cost, MCO review | v1 |

**Not financial advice.** No trading, no exchange keys, no order placement. Every page footer says so.

## 2. Decisions (locked with Rob, 2026-10-26)

1. **Users and access:** invite-only for now (Rob plus a few friends), with roles `admin` (Rob) and `member`. Built multi-user from day one so it can open up later. Features can be switched off per deployment and per role (for example `MCO_ENABLED`).
2. **Friends bring their own LLM key**, and setup must be as simple as possible. The recommended path is one **OpenRouter** key (one signup, one key for Claude, GPT, Gemini and more, with a spending limit they set themselves). Anthropic and OpenAI keys are also accepted. The key is kept **in the friend's browser** and sent with each agent request over HTTPS. The backend never stores or logs it. Rob uses a server-side key, capped by Decision 9.
3. **Coins:** BTC, ETH and SOL, plus a watchlist (max 10) that Rob manages in Settings. Cycle and on-chain tools mostly cover BTC and ETH.
4. **Device:** desktop first (dense, terminal-like layouts), with a simplified but complete phone layout.
5. **Hosting: $0, free tiers only.** The stack is in Section 6. Cold starts of a few seconds after idle are acceptable.
6. **MCO content stays private.** Only his **free public YouTube videos** are used. Every summary is short, attributed and links to the video. MCO-derived data lives only in the private database, never in the public repo, never on a public page, and never in exports for non-admins beyond on-screen display. If the app ever goes public, the MCO tab is switched off unless MCO gives permission. Paywalled content is never ingested.
7. **MCO wave labels are approximate.** They are extracted by an AI from the video and snapped to real swing pivots. **Only labels Rob approves** are shown on charts to members. Extracted levels and invalidation lines can be shown right away, marked "AI-extracted from video".
8. **Signals format (weekly, 1-week horizon):** per coin, `lean_long` or `flat` (no shorts), a confidence (0.5 to 0.95), an entry zone, an invalidation level, a target and a short rationale. The scorecard tracks direction hit rate, calibration (Brier), whether the target or the invalidation was hit first, and a simple paper P&L with costs. It compares four sources: the desk, a coin-flip baseline, a trend-rule baseline, and MCO's extracted bias. The signal definition is versioned; any change creates a new version and never rewrites old records.
9. **Rob's LLM budget:** hard cap **$8 per month** on the server key, enforced in code. If spend gets near the cap, it degrades in this order:
   1. Rob's own chat moves to a cheaper model;
   2. MCO summaries skip lower-priority videos;
   3. the weekly brief writer moves from Sonnet to Haiku.
   Weekly signals are never skipped.
10. **Models:** Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) for agents and the desk, Claude Sonnet 5.5 (`claude-sonnet-5-5`) for the weekly brief writer, and a Gemini Flash-class model for video summaries (Section 3.4). All ids and prices are verified in Stage 0.3. Friends pick any model their key allows; the default is a cheap one. *Updated 2026-10-28 (D24, approved by Rob): Claude Haiku 5.5 (`claude-haiku-5-5`) replaces Haiku 4.5 everywhere; the video model is Gemini 3.5 Flash-Lite with 3.8 Flash as backup (D25).*
11. **Alerts:** Telegram (to Rob) and Discord (a channel Rob's friends can join). Events: weekly brief ready, key-level crossings, new MCO video summarized, ops failures. Ops failures go to admin channels only.
12. **Your own MCP server (`desk-mcp`)** wraps the same analytics functions the API uses. The in-app agent uses it, and Rob can also use it from the Claude desktop app. Each tool is defined once and reused in both places.
13. **Build order:**
    - **v1:** Overview, Charts, Cycles, Stats, Data, Settings.
    - **v1.1:** On-chain & Macro, Agent.
    - **v1.2:** MCO.
    - **v1.3:** Signals.
    - **Hardening.**
    Each version is usable by friends before the next one starts.

## 3. Key designs

### 3.1 Data and analytics (backend package `desk`)

- **Prices:** daily OHLCV from Coinbase through `ccxt` (canonical). Coinbase daily history starts 2015-07-20 (BTC), 2016-05-18 (ETH) and 2021-06-17 (SOL). BTC before that (the 2013 cycle) comes from Coin Metrics community `PriceUSD` (from 2010-07-18, close only); Bitstamp is the fallback exchange (D20). Weekly bars are resampled from daily, with weeks running Monday 00:00 UTC to the next Monday 00:00 UTC. Only closed candles are stored. **Binance is geo-blocked for US cloud IPs and in Ontario: never use it.**
- **Context:** Fear & Greed (alternative.me, full history); BTC dominance (CoinGecko Demo key; no history on Demo, so a daily snapshot from now on, D23); FRED series (free key; as-of reads apply a per-series release lag because FRED dates observations by period, D32); RSS headlines (CoinDesk, Cointelegraph, Decrypt, The Block); a macro calendar YAML (FOMC and CPI dates, from official schedules).
- **On-chain:** Coin Metrics community API for BTC and ETH: `PriceUSD`, `CapMrktCurUSD`, `CapMVRVCur`, `SplyCur`, `AdrActCnt`, `HashRate` (verified free). `CapRealUSD` is not free, so realized cap is derived as market cap / MVRV, realized price as realized cap / supply, and NUPL as (market cap − realized cap) / market cap (D21).
- **Analytics** (pure functions, each with an `as_of` parameter):
  - indicators (SMA/EMA, Bollinger, RSI, MACD, realized volatility);
  - regime label (`uptrend`, `downtrend`, `range`, `high-vol`, with frozen rules in `docs/DECISIONS.md`);
  - key levels (previous week high/low, 20W SMA, 50D/200D SMA, ATH, recent swing high/low);
  - zigzag swing pivots (threshold by volatility);
  - **cycle alignment:** anchors in `config/cycles.yaml` (each cycle runs bottom → halving → top; halvings 2012-11-28, 2016-07-09, 2020-05-11, 2024-04-20; bottoms and tops are the lowest and highest closes in each window, available only once the window has ended, and checked against an independent source, D35), returning day-offset series normalized to the anchor price;
  - year-over-year normalization;
  - seasonality matrices;
  - return distributions;
  - drawdowns;
  - rolling correlations.
- **Look-ahead test:** for random `as_of` values, results on the full data must equal results on data truncated at `as_of`. This matters for signals and agent snapshots.

### 3.2 Agent (LangGraph, Agent tab)

- **Graph:** a tool-calling agent whose tools come from `desk-mcp` through `langchain-mcp-adapters`.
- **Models:** created per request from the user's key:
  - an OpenRouter key goes through LangChain's OpenAI-compatible client with the OpenRouter base URL;
  - Anthropic and OpenAI keys use their own integrations.
  Verify the current APIs in Stage 0.3.
- **Streaming:** Server-Sent Events from FastAPI, streaming tokens plus `tool_start` and `tool_end` events.
- **Data snapshots:** every tool call's arguments and result are saved as an `agent_snapshot` row (user, conversation, tool, args, result JSON, `as_of`, timestamp). The UI shows each tool call as a card, and "View data" opens that snapshot in the Data tab as a table plus a chart.
- **Limits:** at most 10 tool calls per answer, 90-second timeout, and per-user rate limits (for example 30 messages per hour) to protect the free hosting. The admin server key is subject to the Decision 9 cap.
- **System prompt:** an analyst that answers with data, cites the tools it used, and states uncertainty. Headlines and transcripts are untrusted data, and any instructions inside them are ignored. It never gives personal financial advice. Prompts live in `prompts/` and are versioned.
- **Conversations** are stored per user in the database, and each user can delete their own.

### 3.3 Multi-agent desk (used by Signals, and by "Ask the desk" in the Agent tab)

LangGraph `StateGraph`, one run per coin:

```
START ─┬─> technical_analyst (market tools) ─┐
       └─> context_analyst (news, sentiment, ─┴─> bull_open ─┬─> bull_rebut ─┬─> head ─> validator ─> END
           calendar, on-chain, MCO views)        bear_open ─┘   bear_rebut ─┘    ▲        │ invalid, once
                                                                                   └────────┘
```

- **The two analysts** run in parallel, each limited to its own tool group (enforced with `desk-mcp --groups`). Each returns a structured report.
- **Bull and bear** each give an opening case and a rebuttal, with no tools; every claim cites a report field.
- **The head** returns the Decision 8 signal.
- **The validator** is deterministic: schema, ranges, and `invalidation < entry < target` for `lean_long`. It routes back to the head once if the signal is invalid.
- **Models:** all nodes use Haiku. The weekly brief writer (Sonnet 5.5, no tools) turns the reports, debate and signals into the brief.
- **Transcripts:** the full graph state is saved, and the Signals tab can show the debate.

### 3.4 MCO pipeline (private)

1. **Discover (daily, 06:30 UTC):** fetch MCO's channel RSS feed (`https://www.youtube.com/feeds/videos.xml?channel_id=UCngIhBkikUe6e7tZTjpKK7Q`). It returned 404 from a GitHub runner, so fall back to the YouTube Data API v3 uploads playlist (D26). Keep new videos not yet processed. Filter to crypto videos (title or description mentions BTC, ETH, SOL, crypto or altcoins). At most 4 per day, newest first.
2. **Summarize:** send the public video URL to the Gemini API, which can take a YouTube URL as input (verify support, quotas and free-tier limits in Stage 0.3). Fallback if that fails: summarize the title and description only, marked "low detail". YouTube transcript downloads are usually blocked from cloud IPs, so they are not used in CI. The output is a strict JSON schema: per coin mentioned, the bias (`bullish`, `bearish` or `neutral`), the current wave position as text, the primary scenario, the alternative scenario, key levels (price plus label), invalidation, targets, a timeframe, a confidence that the extraction is right (`high`, `medium`, `low`), and `pivot_labels` (wave label, approximate date, approximate price, chart timeframe). Plus a 120-word overall summary.
3. **Snap wave labels:** match each extracted `pivot_label` to the nearest zigzag pivot of the right type (high or low) within a tolerance window (time and price). Unmatched labels are flagged.
4. **Admin review:** Rob sees each video's extracted labels drawn on the chart and approves, edits (drag a label to another pivot) or rejects them. **Only approved labels are visible to members.** Levels and the summary are visible right away, marked "AI-extracted".
5. **Feed the rest of the app:** MCO's bias per coin becomes a scorecard source and a `get_external_views` tool for the agent and desk. Rob can also add manual views (`/note`-style form in Settings: source, coin, bias, levels, invalidation, link) from any analyst.

### 3.5 Signals (weekly)

- **Schedule:** weekly job Monday 00:15 UTC (Sunday evening Toronto).
- **Steps:**
  1. refresh data;
  2. resolve last week's signals;
  3. run the desk per coin (core coins plus watchlist);
  4. compute the baselines: coin flip (confidence 0.5, always `flat`) and the trend rule (`lean_long` with 0.6 if the weekly close is above its 20-week SMA, else `flat` with 0.4);
  5. snapshot MCO's latest bias per coin as a source;
  6. write the `signals` rows (append-only; each row hash-chained to the previous one for tamper evidence);
  7. the brief writer creates the brief;
  8. alerts go out.
- **Daily level watch (no LLM):** pings Telegram and Discord when a close crosses a signal's entry, invalidation or target, or a key level.

### 3.6 Security and privacy

- **Auth:** Clerk (free tier). Access mode "Invite-only" (verified on the free plan, D29). Google or email login. The backend verifies Clerk JWTs on every request. Roles are stored in the DB `users` table (public metadata is not a default token claim; `ADMIN_CLERK_IDS` always maps to admin, D37).
- **User keys:**
  - kept in `localStorage`;
  - sent in a request header only to our backend;
  - never logged (redaction middleware, plus a test that asserts this);
  - protected by a strict Content-Security-Policy and no third-party scripts beyond Clerk and the chart libraries.
  A later option is encrypted server-side storage.
- **Untrusted text:** headlines, video summaries and model outputs are untrusted. They are rendered as text, never HTML. They are never interpolated into shell commands or SQL; use parameterized queries. In workflows, pass them through environment variables, never `${{ }}` inside `run:`.
- **Secrets:** never committed. They live in GitHub Actions secrets and Google Secret Manager. The public repo holds code only.

## 4. Repo layout (monorepo)

```
crypto-desk/
  CLAUDE.md  ROADMAP.md  README.md  LICENSE (MIT)  .env.example  docker-compose.yml (local Postgres)
  backend/
    pyproject.toml  uv.lock  Dockerfile  alembic.ini  migrations/
    src/desk/
      config.py  db.py  models.py              # SQLAlchemy 2.0 models
      data/        market.py  coinmetrics.py  fred.py  sentiment.py  dominance.py  news.py  calendar.py
      analytics/   indicators.py  regime.py  levels.py  pivots.py  cycles.py  seasonality.py  stats.py
                   onchain.py  registry.py (one entry per function)  inputs.py  cache.py  verify.py
      api/         main.py  auth.py  deps.py  common.py  schemas.py  middleware.py  tables.py
                   routes/ (coins, ohlcv, indicators, cycles, stats, onchain, macro,
                   news, calendar, data, agent, mco, signals, admin)
      mcp_server/  server.py  tools.py          # desk-mcp, wraps analytics/ and data readers
      agents/      llm.py (per-request model factory)  chat.py  desk_graph.py  brief_writer.py  schemas.py  cost.py
      mco/         discover.py  summarize.py  snap.py
      signals/     run.py  baselines.py  score.py
      notify/      telegram.py  discord.py
      jobs/        daily.py  weekly.py  levelwatch.py  mco_daily.py
      deploy/      migrate.py (direct-host migrations)  cloudrun.py (service env)  smoke.py   # Stage 2.2
      cli.py       # Typer: desk data|analytics|jobs|mcp|admin|api|notify|db|deploy
    tests/
  frontend/
    package.json  vite.config.ts  tsconfig.json  index.html
    src/
      main.tsx  App.tsx  routes/ (overview, charts, cycles, stats, onchain, agent, mco, signals, data, settings)
      components/  charts/ (CandleChart, LineOverlay, Heatmap, Distribution, CycleOverlay)  ui/  agent/
      lib/  api.ts (generated client)  auth.ts  keys.ts  format.ts  theme.ts
    tests/
  config/   coins.yaml  cycles.yaml  calendar.yaml  feeds.yaml  fred_series.yaml  models.yaml  settings.yaml
  prompts/  agent_v1.md  desk/ (technical_v1, context_v1, bull_v1, bear_v1, head_v1)  brief_v1.md  mco_extract_v1.md
  docs/     DATA_SOURCES.md  DECISIONS.md  ARCHITECTURE.md  USING_WITH_CLAUDE.md  FRIENDS_SETUP.md  OPS.md  LOG.md  PUBLIC_READINESS.md
  .github/workflows/  ci.yml  deploy-backend.yml  deploy-frontend.yml  daily.yml  weekly.yml  levelwatch.yml  mco.yml  probe.yml
```

## 5. Data model (Postgres, Neon)

Core tables, created with Alembic migrations:
- **Market and analytics:**
  - `coins`: symbol, name, aliases, source market, active, is_watchlist, added_at.
  - `candles_daily`: coin, date, OHLCV, source; unique on (coin, date). Coin Metrics backfill rows are close-only (D31).
  - `candles_4h`: coin, bar open time, OHLCV, source; recent history only, resampled from Coinbase 1h (D22). *Added in Stage 1.1.*
  - `series`: key (for example `fng`, `fred:DGS10`, `cm:BTC:CapMVRVCur`, `dominance:btc`), date, value, source; unique on (key, date).
  - `news`: id, source, title, url, published_at, coins[].
  - `calendar_events`.
  - `analytics_cache`: key, params hash, `as_of`, JSON, computed_at; optional, for heavy computations like cycles and stats.
- **Users and agent:**
  - `users`: Clerk id, role, created_at.
  - `conversations` and `messages`: user, role, content, model, tokens, cost (null for user keys).
  - `agent_snapshots`.
- **MCO and views:** `mco_videos`, `mco_extracts`, `mco_wave_labels` (status: `pending`, `approved`, `rejected`, `edited`), `external_views`.
- **Signals and ops:**
  - `signals`: version, week, coin, source, stance, confidence, entry_low, entry_high, invalidation, target, rationale, transcript_ref, prev_hash, hash.
  - `signal_outcomes`, `briefs`.
  - `job_runs`: job, start, end, status, cost, error.
  - `llm_spend`: date, source (server key), model, tokens, cost.

Data stays far below Neon's free storage limit (verify the limit). Daily candles for 4 to 13 coins since 2010 come to a few MB.

## 6. Stack and hosting ($0)

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + TypeScript + Vite, Tailwind CSS, shadcn/ui, TanStack Query, React Router | Standard, fast, app-like tabs; Claude Code knows it well |
| Price charts | **TradingView Lightweight Charts** (open source, Apache 2.0) | Proper financial charts, fast. **Keep the required TradingView attribution** (verify the current license notice) |
| Other charts | Apache ECharts | Heatmaps, distributions, cycle overlays with log axes |
| Frontend hosting | Cloudflare Pages (free) | Free static hosting, generous bandwidth |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, `uv` | Reuses the Python analytics, LangGraph and MCP code |
| Backend hosting | Google Cloud Run (free tier, min instances 0) | Rob already uses it; scales to zero; supports SSE streaming. Set a GCP budget alert at $1 |
| Database | Neon Postgres (free tier) | Rob already uses it; serverless; use the pooled connection string |
| Auth | Clerk (free tier) | Invite-only now, open sign-up later; React SDK; JWT verification in FastAPI |
| Scheduled jobs | GitHub Actions cron (free for public repos) | Runs `desk jobs ...` against Neon |
| Agents | LangGraph + LangChain (Anthropic, OpenAI, OpenRouter via the OpenAI-compatible client) + `langchain-mcp-adapters`; LangSmith free tier for tracing | Same skills as ESSCONTI; agents, evals and observability |
| MCP | Official `mcp` Python SDK (`FastMCP`), stdio | `desk-mcp` for the in-app agent and for Rob's Claude desktop app |
| Video summaries | Gemini API (`gemini-3.5-flash-lite` on the free tier, D25) | Reads public YouTube videos by URL from the cloud |
| Alerts | Telegram Bot API, Discord webhook | Free |

## 7. Budget

- **Hosting:** $0 (Cloudflare Pages, Cloud Run free tier, Neon free, Clerk free, GitHub Actions on a public repo, LangSmith free, Telegram and Discord free). Guard rails: a GCP budget alert at $1; Cloud Run max instances 2; per-user rate limits.
- **Rob's server-key LLM spend (estimates, verified in Stage 0.3):**

| Item | Est. per month |
|---|---|
| Weekly desk on 3 coins + up to ~3 watchlist coins (Haiku 5.5, about 9 calls per coin) | $0.10 to $0.40 |
| Weekly brief writer (Sonnet 5.5) | $0.45 |
| MCO summaries (Gemini 3.5 Flash-Lite, up to ~4 videos a day, free tier; about $0.30 if paid) | $0 |
| Rob's own agent chat (Haiku 5.5 default, capped) | up to $1.00 |
| **Total** | **about $0.50 to $2, hard cap $8** (re-estimated in Stage 0.3 with Haiku 5.5, D24) |

- **Friends:** their own key. A typical friend asking ~50 questions a month on a cheap model spends cents to a dollar or so. `docs/FRIENDS_SETUP.md` explains how to set an OpenRouter spending limit.

## 8. Conventions for every substage

- **Backend:** Python 3.12, `uv`, Ruff (line length 100), type hints, Pydantic v2 schemas, `pytest` plus `pytest-asyncio`. Network calls use recorded fixtures in unit tests. Each source gets one `live`-marked test, skipped unless `RUN_LIVE=1`. LLM tests use fake chat models.
- **Frontend:** TypeScript strict, ESLint, Prettier, Vitest plus React Testing Library for components, and one Playwright smoke test per tab (Playwright is configured on Rob's machine and in CI).
- **API contract:** FastAPI's OpenAPI schema is the source of truth, and the frontend client is generated from it (for example `openapi-typescript`). Regenerate it on every API change.
- **Design direction:**
  - a clean, dense, dark-first "terminal" look with a light theme too;
  - one set of color tokens (positive and negative, series colors, background and surfaces);
  - tabular numbers;
  - consistent number formatting (prices with 2 to 4 significant decimals, percentages to 1 decimal);
  - accessible contrast;
  - every chart has a title, units and a "View data" link to the Data tab.
- **Time:** UTC everywhere in code and the API. The UI shows local time with a UTC hint.
- **Platforms:** dev is on Windows (PowerShell, set `PYTHONUTF8=1`) and CI is on Ubuntu. Use `pathlib` and Python or Node entry points, not shell scripts.
- **Cost:** every server-key LLM call goes through `agents/cost.py`, which records spend in `llm_spend` and enforces Decision 9. Before any manual run with more than 10 LLM calls, print the projected cost.
- **Prompts:** versioned in `prompts/`. A prompt used in production is never edited; add `_v2`.
- **Safety:** no trading code or exchange keys. Never commit secrets. Treat external text as untrusted (Section 3.6).
- **After each substage:** tests and lint pass, commit `Stage X.Y: <summary>`, tick Section 14, and add a line to `docs/LOG.md`.

## 9. Quality bars

- **Data:** weekly resampling and cycle anchors match an independent source; Rob spot-checks 5 values on a public chart.
- **No leakage:** the look-ahead test passes for every analytics function.
- **Keys:** a user's key never appears in logs, the DB, error messages or LangSmith traces (automated test with a canary key).
- **Access control:**
  - members never see unapproved MCO wave labels;
  - non-admins cannot reach admin routes;
  - tests cover every role on every route.
- **Every tab:**
  - loads in under 3 seconds on a warm backend;
  - shows a clear loading state on a cold start;
  - works at 1440 px and at 390 px widths;
  - passes its Playwright smoke test.
- **Agent:** the "View data" link exists for every tool call and opens the exact snapshot.
- **Jobs:** daily jobs have run successfully for 3 consecutive days before friends are invited.

## 10. Risks and mitigations

- **Free tiers change or are tighter than expected** (Cloud Run, Neon, Clerk, Gemini, CoinGecko, Coin Metrics). Mitigation: Stage 0.3 verifies everything; `docs/DECISIONS.md` lists a fallback per service (for example Render or Fly.io for the backend, Supabase for DB and auth); usage alerts.
- **Gemini can't read a video, or quotas are too small.** Mitigation: fallback to title and description only, marked "low detail"; a daily cap; optionally an on-demand "summarize this video" admin button.
- **AI-extracted Elliott wave labels are wrong.** Mitigation: snapping to real pivots, the admin approval step, "approximate" badges, and showing only levels when confidence is low.
- **MCO content and permission.** Mitigation: Decision 6 (private, attributed, linked, free videos only, off if public).
- **Prompt injection through headlines or video content.** Mitigation: untrusted-data wrapping in prompts, read-only tools, schema validation, text-only rendering.
- **User key leakage.** Mitigation: Section 3.6 and the Section 9 canary test. Friends set spending limits on their own keys.
- **Scope creep.** Ten tabs is a lot. Mitigation: the version order in Decision 13, and each version ships to friends before the next one starts.

---

## 11. The roadmap: stages and substages

### Stage 0: Setup and verification
*Checkpoint: accounts exist, the monorepo is scaffolded with green CI, and every data source, free tier, library API and model id is verified.*

- **0.1 [Rob] Accounts and keys** (about 45 minutes).
  1. **GitHub:** create the public repo `crypto-desk` completely empty. In `C:\Users\rober\code\crypto-desk` (which holds `ROADMAP.md` and `CLAUDE.md`), run `git init -b main`, `git remote add origin https://github.com/robertsolomon002/crypto-desk.git`, then commit and push.
  2. **Google Cloud:** a project `crypto-desk` with billing enabled (needed for the free tier), Cloud Run, Artifact Registry and Secret Manager APIs enabled, and **a budget alert at $1**.
  3. **Neon:** a free project `crypto-desk`; copy the pooled connection string.
  4. **Cloudflare:** a free account (Pages).
  5. **Clerk:** an application with Google plus email sign-in and Access mode set to Invite-only (User & authentication → Access mode; the old "restricted" sign-up mode); copy the publishable key and secret key.
  6. **Anthropic API key:** monthly limit $6, auto-reload off.
  7. **Google AI Studio (Gemini) API key.**
  8. **OpenRouter account and key with a $2 limit** (to test the friends' path).
  9. **Free keys:** FRED API key and CoinGecko Demo key.
  10. **Telegram:** create a bot with `@BotFather` and get your chat id via `getUpdates`.
  11. **Discord:** create a webhook in your friends' server channel `#crypto-desk` (and optionally a private `#ops` channel webhook).
  12. **LangSmith:** a free account and key.
  13. **Secrets:** copy `.env.example` to `.env` and fill it in (never committed), then add the same names as GitHub Actions secrets. Claude Code mirrors the backend ones into Google Secret Manager in Stage 2.2. Cloudflare's account id and API token can wait until Stage 2.2.

- **0.2 Scaffold the monorepo.**
  Prompt: "Read ROADMAP.md Sections 1 to 10. Scaffold the repo exactly as in Section 4.
  1. **Backend:** a `uv` project (Python 3.12) with package `desk`, a Typer CLI `desk` and an entry point `desk-mcp`. Dependencies: FastAPI, uvicorn, SQLAlchemy 2.0, Alembic, psycopg (v3), pydantic-settings, ccxt, pandas, numpy, httpx, feedparser, pyyaml, `mcp`, langgraph, langchain-core, langchain-anthropic, langchain-openai, langchain-google-genai, langchain-mcp-adapters, langsmith, `clerk-backend-api` or PyJWT with JWKS. Dev dependencies: pytest, pytest-asyncio, respx, ruff. A Dockerfile and a `docker-compose.yml` with local Postgres.
  2. **Frontend:** Vite, React and TypeScript (strict; pinned to 6.0 until typescript-eslint supports 7, D14), Tailwind, shadcn/ui, TanStack Query, React Router, `lightweight-charts`, `echarts` with `echarts-for-react`, `@clerk/react` (`@clerk/clerk-react` is deprecated, D15), Vitest, React Testing Library, Playwright, ESLint and Prettier.
  3. **Config files** with commented defaults from Sections 2, 3 and 7.
  4. **`.env.example`:** keep the file Rob already has (same variable names) and add any new ones it needs, with comments.
  5. **README stub** with the not-financial-advice notice.
  6. **Docs:** `docs/LOG.md`, `docs/DECISIONS.md` (copy Section 2 as entries D1 to D13), and `docs/ARCHITECTURE.md` (Section 6 plus a component diagram).
  7. **CI** (`ci.yml`): backend lint and tests on Ubuntu and Windows; frontend typecheck, lint and tests; Playwright smoke against `vite preview` with a mocked API.
  8. A health route `/api/health`, and a frontend page that calls it.
  Push and confirm CI is green. Report the exact local dev commands (backend, frontend, local DB)."

- **0.3 Verification spike** (plan mode).
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Write `backend/scripts/probe_sources.py` and `probe.yml` (`workflow_dispatch`) to test, both locally and on a GitHub runner:
     - `ccxt` Coinbase (`coinbase` and `coinbaseexchange`) and Bitstamp daily history depth for BTC, ETH and SOL, and whether 4H candles are available;
     - Coin Metrics community API: which free metrics exist for BTC and ETH (PriceUSD history start, CapMrktCurUSD, CapRealUSD, CapMVRVCur, AdrActCnt, HashRate), and rate limits;
     - FRED (DTWEXBGS, DGS10, DFF, M2SL);
     - Fear & Greed full history;
     - CoinGecko Demo: global dominance current and history availability, and rate limits;
     - each RSS feed;
     - MCO's YouTube channel RSS (find and record the channel id);
     - Hyperliquid funding (optional).
  2. Write `probe_llm.py` (spend cap $0.25):
     - one Haiku and one Sonnet structured-output call;
     - one OpenRouter call through LangChain's OpenAI-compatible client;
     - one Gemini call with **one recent public MCO video URL** returning the Section 3.4 JSON schema; record tokens, cost, latency and quality, and print the extracted levels;
     - a `langchain-mcp-adapters` stdio round trip to a 1-tool dummy server.
  3. Verify from official docs and record with links and dates:
     - free-tier limits for Cloud Run (requests, CPU, SSE support and timeouts), Neon (storage, compute hours), Cloudflare Pages, Clerk (restricted sign-up and invitations on free), Gemini (YouTube URL support, free quotas, data-use terms), and LangSmith;
     - the Lightweight Charts license attribution requirement;
     - current model ids and prices;
     - the current LangGraph and LangChain agent, structured-output and streaming APIs;
     - Telegram and Discord message limits.
  4. Send a test Telegram message and a test Discord message.
  5. Write `docs/DATA_SOURCES.md` and the decision entries, including a fallback per service. Update ROADMAP.md wherever reality differs (for example if on-chain metrics or dominance history are not free)."

### Stage 1: Data platform
*Checkpoint: Neon holds full history for all sources, analytics functions pass their tests (including the look-ahead test), and the daily job refreshes everything on GitHub Actions.*

- **1.1 Schema, migrations and market data** (plan mode).
  Prompt: "Read ROADMAP.md Sections 1 to 10 and `docs/DATA_SOURCES.md`.
  1. Implement `db.py`, the SQLAlchemy models for Section 5 (all tables, so later stages only add columns), and the first Alembic migration.
  2. Implement `data/market.py`:
     - daily OHLCV through `ccxt` with pagination, retries and incremental updates;
     - closed candles only;
     - long BTC history backfill from the source chosen in 0.3, recorded per row as `source`;
     - weekly resampling (Monday 00:00 UTC);
     - validation: gaps, duplicates, OHLC consistency, day moves over 40% flagged.
  3. Seed `coins` from `config/coins.yaml`.
  4. CLI: `desk data update --market` and `desk data status`.
  5. Tests with fixtures and a local Postgres (docker-compose or a pytest Postgres fixture): pagination, incremental update, resampling across month and year boundaries, gap detection, idempotent upserts."

- **1.2 Context, on-chain and macro data.**
  Prompt: "Read ROADMAP.md Sections 1 to 10 and `docs/DATA_SOURCES.md`.
  1. Implement `data/sentiment.py` (Fear & Greed), `coinmetrics.py` (the metrics verified in 0.3, into `series`), `fred.py` (series from `config/fred_series.yaml`), `dominance.py` (history if available, otherwise a daily snapshot), `news.py` (RSS normalize, keyword coin tagging from aliases, dedupe, HTML stripped) and `calendar.py` (YAML).
  2. Write `config/calendar.yaml` with FOMC decision dates and US CPI release dates for 2026-10 to 2027-12 from the official Fed and BLS schedules, with URLs cited; Rob double-checks.
  3. Every reader takes `as_of`.
  4. CLI: `desk data update` refreshes everything.
  5. Tests with fixtures for each source, plus as-of filtering."

- **1.3 Analytics engine** (plan mode).
  Prompt: "Read ROADMAP.md Sections 1 to 10, especially Section 3.1.
  1. Implement `analytics/` as pure, typed functions over DataFrames, each with `as_of`:
     - indicators;
     - regime (write the rules into DECISIONS.md first, never tuned on outcomes);
     - key levels;
     - zigzag pivots (volatility-scaled threshold; returns pivot type, date and price);
     - cycles (anchor modes `halving`, `bottom` and `top` from `config/cycles.yaml`; verify bottom and top dates against the data as the min or max within each documented window; return day-offset series normalized as a multiple of the anchor price, plus drawdown from the cycle ATH; a 'day N of current cycle' comparison table);
     - year-over-year normalized paths;
     - seasonality (monthly and weekly return matrices, day-of-week);
     - return distributions with the current percentile;
     - drawdowns;
     - rolling volatility;
     - rolling correlations;
     - NUPL from Coin Metrics caps.
  2. Add `analytics_cache` with invalidation on new data.
  3. Implement the look-ahead test (50 random `as_of` values per coin and function).
  4. Unit tests against hand-computed values on synthetic series.
  5. CLI `desk analytics show <function> <coin>` for manual checks. Print the current cycle table for BTC in your report."

- **1.4 Daily jobs on GitHub Actions.**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Implement `jobs/daily.py`: update all data, refresh the analytics cache, write a `job_runs` row.
  2. Implement `notify/telegram.py` and `notify/discord.py`: a message interface with per-event routing from `config/settings.yaml`; a missing secret means that channel is skipped with a warning; retries; length limits from 0.3; text escaped.
  3. Write `daily.yml` (cron `20 0 * * *` plus `workflow_dispatch`) using the Neon secret. On failure it sends an `ops_failure` alert to admin channels with the run link.
  4. Use concurrency groups.
  5. Rob triggers the workflow once. Confirm the data landed and alerts work."

### Stage 2: API, auth and deployment
*Checkpoint: a secured FastAPI backend runs on Cloud Run against Neon, and the frontend shell is live on Cloudflare Pages with invite-only login.*

- **2.1 Read API with auth and roles** (plan mode).
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Implement `api/` with routes for coins, OHLCV (1D and 1W, optional 4H), indicators (selectable, with parameters), levels and pivots, cycles (by anchor mode), YoY, seasonality, distributions, drawdowns, correlations, on-chain and macro series, news, calendar, and `data/` (list tables, query a table with filters and paging, CSV export). Every response includes `as_of` and source fields so the UI can show provenance.
  2. Auth: verify Clerk JWTs (JWKS cached), upsert `users`, and add a `require_role` dependency; admin routes for watchlist and invites.
  3. Add per-user rate limiting (in-memory is fine for a single instance; note the limit), plus gzip and ETag caching for heavy analytics.
  4. Add redaction middleware that drops `X-LLM-Key` from logs.
  5. Generate the OpenAPI schema and the frontend client.
  6. Tests: every route with fixtures; role checks on every route; CSV export; the redaction test with a canary key."

- **2.2 Deploy backend and frontend.**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Write `deploy-backend.yml`: build the Docker image, push it to Artifact Registry, and deploy to Cloud Run (min instances 0, max 2, memory and CPU within the free tier, request timeout long enough for SSE, secrets from Secret Manager) using Workload Identity Federation (no JSON keys in GitHub). Mirror the backend secrets into Secret Manager. *Updated 2026-10-30 (D38): only the secrets the Cloud Run service reads are mirrored (`DATABASE_URL`, `CLERK_SECRET_KEY`; the Anthropic and LangSmith keys join in 5.1), because Secret Manager's free tier is 6 active versions; the jobs keep using GitHub secrets. The frontend is at `crypto-desk-a9f.pages.dev` (the bare name was taken), and new revisions are smoke-tested with no traffic before they go live.*
  2. Write `deploy-frontend.yml` for Cloudflare Pages, with production and preview builds and the API base URL as an env var.
  3. Configure CORS for the Pages domains only, plus a strict Content-Security-Policy for the frontend.
  4. Run migrations on deploy (a separate step, never on app start).
  5. Post-deploy smoke tests: health, one authenticated call.
  6. Write `docs/OPS.md` (first version): URLs, how to deploy, roll back and read logs.
  Report the live URLs."

### Stage 3: Terminal v1 (Overview, Charts, Cycles, Stats, Data, Settings)
*Checkpoint: Rob and two invited friends use the live app; every v1 tab works on desktop and phone and passes its smoke test.*

- **3.1 App shell, auth, theme and Overview** (plan mode).
  Prompt: "Read ROADMAP.md Sections 1 to 10, especially the design direction in Section 8.
  1. Build the app shell:
     - Clerk sign-in. [Rob] signs in once (check whether invite-only means he must invite himself first), then adds his `user_…` id to `ADMIN_CLERK_IDS` in `.env` and the deploy secrets (D37);
     - a top bar with a coin selector (core plus watchlist), tabs in Section 1 order (tabs for later versions hidden behind feature flags);
     - light and dark themes from one token set;
     - a responsive layout (desktop-first; on phone, tabs move to a bottom bar or menu);
     - a global loading state that explains cold starts ('waking up the server…');
     - error boundaries;
     - a footer with the not-advice notice and the data-sources credit.
  2. Build the Overview tab: coin cards, Fear & Greed gauge, this week's macro events, top headlines and a data-freshness strip. Each element has a 'View data' link to the Data tab.
  3. Tests: components with mocked API; a Playwright smoke test for the shell and Overview at 1440 px and 390 px."

- **3.2 Charts tab** (plan mode).
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Build the Charts tab with Lightweight Charts (keep the TradingView attribution):
     - candles plus volume;
     - timeframe switch;
     - log or linear scale;
     - an indicator picker (SMA/EMA 20/50/200, the 20W SMA band, Bollinger; RSI and MACD in synced sub-panes);
     - overlays: key levels (labeled price lines), zigzag pivots (markers);
     - placeholders for the MCO levels and wave label toggles, hidden until v1.2;
     - ratio mode (pick two coins, plot A/B);
     - crosshair readout with OHLC and indicator values;
     - the chosen settings saved per user in localStorage;
     - a 'View data' link for the visible range.
  2. Make it performant for the full BTC history.
  3. Tests: indicator math matches the backend for a fixture; Playwright smoke."

- **3.3 Cycles and Stats tabs.**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Build the Cycles tab (ECharts):
     - anchor-mode switch (halving, bottom, top);
     - y-mode switch (multiple of anchor on a log axis, or % drawdown from cycle ATH);
     - past cycles as muted lines and the current cycle highlighted, with a 'today' marker;
     - hover shows each cycle's value on the same day offset;
     - the 'day N of current cycle' table;
     - a YoY overlay sub-view;
     - an ROI-since-bottom table.
  2. Build the Stats tab:
     - monthly returns heatmap (diverging colors, values in cells);
     - weekly and day-of-week seasonality bars;
     - return distribution histogram with the current week marked and its percentile;
     - drawdown area chart;
     - rolling volatility;
     - rolling correlation matrix and lines.
  3. Everything uses the coin selector, and each chart has 'View data'. Use colorblind-safe palettes.
  4. Tests: Playwright smoke for both tabs."

- **3.4 Data and Settings tabs, then invite friends.**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Build the Data tab:
     - a list of tables with descriptions and freshness;
     - a table view with filters (coin, date range), sorting and paging;
     - a quick chart preview of any numeric column;
     - CSV export;
     - deep links (`/data?table=...&coin=...&from=...`) used by every 'View data' link.
  2. Build Settings:
     - theme;
     - default model;
     - the **LLM key setup wizard**, inactive until v1.1 but built now: provider choice with OpenRouter recommended; three short steps with links (sign up, create a key, set a spending limit); paste the key; 'Test key' with a 1-token call through the backend; a clear note that the key stays in this browser.
     - admin only: watchlist management (add or remove with eligibility checks: a Coinbase USD market and at least 1 year of history), invite users via Clerk, a usage page.
  3. Write `docs/FRIENDS_SETUP.md`: how to log in, get an OpenRouter key and set its limit, and what the tabs do.
  4. Tests: Playwright smoke; key-storage unit tests."
  **[Rob]** invites 1 or 2 friends after daily jobs have run successfully for 3 days (Section 9), collects feedback, and pastes it into the next session as a short list for the agent to fix.

### Stage 4: On-chain & Macro tab and `desk-mcp` (v1.1, part 1)
*Checkpoint: the On-chain & Macro tab is live; `desk-mcp` exposes the analytics as tools and works in Rob's Claude desktop app.*

- **4.1 On-chain & Macro tab.**
  Prompt: "Read ROADMAP.md Sections 1 to 10 and `docs/DATA_SOURCES.md`.
  1. Build the tab:
     - BTC and ETH on-chain panels (MVRV with historical bands, price vs realized price, NUPL, active addresses, BTC hash rate), each with a short plain-English explainer and 'View data';
     - Fear & Greed history with price;
     - BTC dominance;
     - macro panels (broad dollar index, 10-year yield, fed funds, M2 with its YoY change), each with an 'overlay on BTC' toggle and a correlation readout.
     Hide any panel whose data was unavailable in 0.3, and note it on the panel.
  2. Tests: Playwright smoke."

- **4.2 `desk-mcp` server and Claude desktop setup.**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Implement `mcp_server/` with the official `mcp` SDK (`FastMCP`, stdio), wrapping the same analytics and data functions as the API, each defined once and reused in both places. Tools:
     - market: `list_coins`, `get_ohlcv`, `get_indicators`, `get_regime`, `get_key_levels`, `get_pivots`, `compare_assets`;
     - cycles: `get_cycle_comparison`, `get_yoy`;
     - stats: `get_seasonality`, `get_return_distribution`, `get_drawdowns`, `get_correlations`;
     - context: `get_onchain`, `get_macro`, `get_sentiment`, `get_news`, `get_calendar`;
     - views (stub until Stage 6): `get_external_views`.
  2. Every tool has an `as_of` parameter and a description written for an LLM reader (returns, units, example). Outputs are compact JSON with rounded numbers.
  3. Implement `--groups` access control (`market`, `cycles`, `stats`, `context`, `views`).
  4. Tests over stdio with the SDK client: tool lists per group, schemas, `as_of` honored.
  5. Write `docs/USING_WITH_CLAUDE.md`: the Windows Claude desktop config (`uv --directory C:\\Users\\rober\\code\\crypto-desk\\backend run desk-mcp`, with `DATABASE_URL` from `.env`) and 10 example questions."
  **[Rob]** adds it to the Claude desktop app and tries 5 questions.

### Stage 5: Agent tab (v1.1, part 2)
*Checkpoint: Rob and friends chat with the agent using their own keys (Rob uses the capped server key); every answer shows its tool calls, and each one opens its exact data in the Data tab.*

- **5.1 Agent backend** (plan mode).
  Prompt: "Read ROADMAP.md Sections 1 to 10, especially Sections 3.2 and 3.6.
  1. Implement `agents/llm.py`, a per-request model factory:
     - an OpenRouter key goes through the OpenAI-compatible client with the OpenRouter base URL and the chosen model;
     - an Anthropic or OpenAI key uses its own integration;
     - an admin with no key uses the server key with `cost.py` enforcement.
  2. Implement `agents/chat.py`: a LangGraph tool-calling agent with tools loaded from `desk-mcp` through `langchain-mcp-adapters` (all groups); the `prompts/agent_v1.md` system prompt; at most 10 tool calls; a 90-second timeout; conversation memory from `messages`.
  3. Add `POST /api/agent/chat` (SSE) streaming token, `tool_start` (name, args) and `tool_end` (snapshot id, short preview) events, and writing `agent_snapshots` for every tool call. Also add `GET /api/agent/snapshots/{id}`, plus conversation list and delete routes.
  4. Keys come only from the `X-LLM-Key` header and are never logged or persisted. Extend the canary test to cover LangSmith traces (strip the key and headers from trace metadata).
  5. Add per-user rate limits.
  6. Tests with fake chat models: tool flow, the limit and timeout, snapshot writing, an admin over the cap getting a clear error, a member without a key getting a clear error, provider routing."

- **5.2 Agent UI.**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Build the Agent tab:
     - a conversation list;
     - a chat view with streaming and Markdown rendering (sanitized, no raw HTML);
     - a model picker (filtered to the user's provider; cheap default);
     - tool-call cards inline (tool name, arguments in plain words, a small preview, and a 'View data' button opening `/data?snapshot=<id>`);
     - a 'data used' summary at the end of each answer;
     - suggested starter questions ('Where is BTC in its cycle vs 2017?', 'Is SOL above its 20-week band?', 'What macro events could move crypto this week?');
     - if no key is set, a friendly prompt to open the Settings wizard.
  2. Extend the Data tab to render a snapshot (table plus chart).
  3. Turn on the key wizard's 'Test key'.
  4. Tests: component tests with a mocked SSE stream; Playwright smoke with a mocked backend."

- **5.3 The multi-agent desk and 'Ask the desk' mode** (plan mode).
  Prompt: "Read ROADMAP.md Sections 1 to 10, especially Section 3.3.
  1. Implement `agents/desk_graph.py` exactly as diagrammed:
     - parallel analysts, each with its own `--groups` tool session;
     - parallel bull and bear openings, then parallel rebuttals;
     - the head returns the Decision 8 schema;
     - a deterministic validator with one retry.
     Write the prompts in `prompts/desk/` with strict word limits. Debaters cite report fields. The head is told the debate is advocacy, not evidence of probability, and is given calibration guidance.
  2. Expose it in the Agent tab as an 'Ask the desk' toggle for a chosen coin, streaming each node's progress as cards (analyst reports, debate, final signal). It uses the user's key and model; Haiku-class is recommended, and the UI shows a per-run cost estimate first.
  3. Save the full state to `agent_snapshots`.
  4. Tests with fake models: topology and parallelism, per-node tools, validator retry, a node timeout handled cleanly.
  5. One live run on SOL with the server key; report the per-node cost."

### Stage 6: MCO tab (v1.2)
*Checkpoint: new MCO videos are summarized daily into the private MCO tab; his levels can be shown on charts; approved wave labels appear for members; the agent can use his views.*

- **6.1 MCO ingest pipeline** (plan mode).
  Prompt: "Read ROADMAP.md Sections 1 to 10, especially Section 3.4 and Decision 6, and the Gemini findings in `docs/DATA_SOURCES.md`.
  **[Rob] first:** enable the YouTube Data API v3 in the `crypto-desk-gemini` project, create an API key restricted to it, and add `YOUTUBE_API_KEY` to `.env` and GitHub secrets (D26).
  1. Implement `mco/discover.py`: channel RSS with the YouTube Data API uploads playlist as fallback (D26), the crypto filter, a cap of 4 per day, and dedupe by video id.
  2. Implement `mco/summarize.py`: send the public video URL to Gemini with `prompts/mco_extract_v1.md`, get strict JSON (Section 3.4), validate it with Pydantic, repair once, and fall back to title and description marked 'low detail'. Record cost in `llm_spend`.
  3. Implement `mco/snap.py`: match `pivot_labels` to zigzag pivots of the right type within a tolerance (default ±5 daily bars and ±3% price on 1D; scale for 1W); store the result as `pending`, with unmatched labels flagged.
  4. Write `jobs/mco_daily.py` and `mco.yml` (cron `30 6 * * *` plus `workflow_dispatch`). It sends a `new_mco_summary` alert (title, per-coin bias, link) to Telegram and Discord.
  5. **Privacy:**
     - no MCO-derived text in logs, the repo, CI artifacts or public routes;
     - all MCO routes require login, and the review routes require admin;
     - `MCO_ENABLED` flag.
  6. Tests: schema validation, fallback, snapping on synthetic pivots, the privacy checks (route auth, no repo writes).
  7. Run it once live on the latest 2 videos and show Rob the extracted JSON next to the video links so he can judge quality."

- **6.2 MCO tab, chart overlays and external views.**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Build the MCO tab:
     - a feed of video cards (thumbnail, title, date, link, overall summary, per-coin bias chips, levels, invalidation, targets, scenarios, extraction confidence) with filters by coin;
     - a per-coin bias timeline over price (markers coloured by bias);
     - an 'AI-extracted, may be imperfect, always check the video' notice;
     - attribution and links everywhere.
  2. In the Charts tab, enable the 'MCO levels' toggle (labeled lines with the video date) and the 'MCO waves' toggle (approved labels only, for members).
  3. Implement `external_views`: MCO extracts plus Rob's manual views (a Settings form for admin: source, coin, bias, levels, invalidation, link). Wire `get_external_views` into `desk-mcp` (`views` group) and the desk's context analyst.
  4. Tests: role checks (members never see pending labels), Playwright smoke."

- **6.3 Wave-label review queue (admin).**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Build the admin review view:
     - per video, the chart with pending labels drawn at their snapped pivots, unmatched labels listed beside it, and the video embedded or linked;
     - actions per label: approve, reject, or move it to another pivot (click a pivot marker) or edit its text;
     - approve-all for a video.
     Every action is audited (who, when, before and after).
  2. Add a 'pending review' badge for the admin and a Telegram note when new labels await review.
  3. Tests: state transitions, the audit trail, members only ever see `approved` or `edited` labels."

### Stage 7: Signals tab (v1.3)
*Checkpoint: every Sunday evening the desk writes signals and a brief; the Signals tab shows the brief, the current signals, the debate and a scorecard comparing the desk, two baselines and MCO; alerts go to Telegram and Discord.*

- **7.1 Weekly signals job.**
  Prompt: "Read ROADMAP.md Sections 1 to 10, especially Section 3.5 and Decision 8.
  1. Implement `signals/baselines.py` (coin flip and trend rule) and `signals/run.py`:
     - refresh data;
     - resolve last week's signals;
     - run the desk per coin with the server key (core coins plus up to 3 watchlist coins, the watchlist skipped under Decision 9 degradation);
     - compute the baselines;
     - record MCO's latest bias per coin as a source (`lean_long` if bullish, `flat` otherwise, confidence from the extraction, or 0.6 if none);
     - write append-only, hash-chained `signals` rows with signal version `v1`.
  2. Implement `agents/brief_writer.py` (Sonnet 5.5, no tools, Haiku under degradation): per coin, setup, bull case, bear case, what would change the view, levels to watch; plus a 5-line summary. Store it in `briefs`.
  3. Write `jobs/weekly.py`, `weekly.yml` (cron `15 0 * * 1`), `jobs/levelwatch.py` and `levelwatch.yml` (daily, no LLM: crossings of entry, invalidation, target and key levels). Alerts: `brief_ready` and `level_cross` to Telegram and Discord.
  4. Do a dry run (`--dry-run`) on the current week and report the signals, cost and wall time. The total must be at most $0.50 per week; otherwise propose cuts.
  5. Tests: baselines; hash chain and append-only enforcement (a DB trigger or app check); level-watch logic."

- **7.2 Scoring and Signals UI.**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Implement `signals/score.py`:
     - direction hit rate;
     - Brier score on confidence;
     - target-before-invalidation rate within the week (from daily highs and lows; ambiguous same-day hits counted as invalidation first, which is conservative);
     - paper P&L for `lean_long` weeks with 0.2% cost per side;
     - per-source and per-coin results, with sample size and 'early days' warnings under 12 weeks.
  2. Build the Signals tab:
     - the latest brief;
     - a current signals table (source × coin);
     - for each desk signal, an expandable debate view;
     - the scorecard (sources compared, with cumulative charts);
     - history;
     - the not-advice notice;
     - 'View data' links throughout.
  3. Tests: scoring on hand-computed cases; Playwright smoke."

### Stage 8: Hardening and "full-fledged" readiness
*Checkpoint: the app is monitored, documented, backed up and cheap to run; there is a clear checklist for opening it up later; the project is CV-ready.*

- **8.1 Ops, monitoring and cost.**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Add an admin Health page: last run per job, data freshness per source, `llm_spend` month-to-date vs the cap and the degradations applied, error counts, Cloud Run and Neon usage (manual links are fine if there is no free API).
  2. Add a weekly ops summary to the admin Telegram.
  3. Backups: a weekly `pg_dump` of the non-reproducible tables (users, conversations, `mco_*`, `external_views`, signals, briefs) to a private artifact or private storage, kept encrypted and out of the public repo. Verify the Neon free-tier backup or branch options first.
  4. Finish `docs/OPS.md`: runbooks for a failed job, a broken source, rotating keys, a free-tier limit hit, and onboarding a friend.
  5. Error tracking: Sentry's free tier, or structured logs only; decide and record it.
  6. Load-check the agent under 3 concurrent users."

- **8.2 Public-readiness review, README and CV.**
  Prompt: "Read ROADMAP.md Sections 1 to 10.
  1. Write `docs/PUBLIC_READINESS.md`, listing what must change before the app can open beyond friends: the MCO tab off unless permission is given (Decision 6); open sign-up and abuse limits; terms and disclaimer; data-source terms of use (Coin Metrics community, CoinGecko, FRED attribution); costs at 100 and 1,000 users; moving user keys to encrypted server-side storage; and a paid-tier option if ever wanted.
  2. Write a polished README with screenshots of each tab, the architecture diagram, how to run it locally, how to use `desk-mcp` with Claude, and the not-advice notice. Exclude MCO content from screenshots.
  3. Write `docs/RESUME_NOTES.md`:
     - 3 resume bullets using only real facts (tabs, data sources, the MCP server, the LangGraph desk, users, agent tool-call provenance, cost engineering);
     - a 60-second spoken summary;
     - an interview cheat sheet covering: the MCP tool design and group-based access control; agent provenance ('view the data it used'); the multi-agent graph; BYO-key security; free-tier architecture; analytics correctness and the look-ahead test; and what Rob would build next."

---

## 12. Effort and timeline (rough, with Claude Code)

About 26 agent prompts plus 3 [Rob] steps.

| Version | Stages | Rough effort |
|---|---|---|
| **v1** | 0 to 3 | about 1 to 2 weeks of evenings. Friends invited at the end. |
| **v1.1** | 4 and 5 | about 1 week |
| **v1.2** | 6 | about 3 to 5 days |
| **v1.3** | 7 | about 3 to 4 days |
| **Hardening** | 8 | ongoing |

Each version ships to friends before the next one starts. No fixed dates: priority stays with job applications and course work.

**Minimum useful cut:** v1 (the terminal without the agent).

## 13. Out of scope (for now)

- trading, exchange accounts, portfolio tracking with real balances;
- intraday data below 4H;
- paid data;
- MCO paywalled content;
- a public launch (see `docs/PUBLIC_READINESS.md`);
- native mobile apps;
- fine-tuning models.

## 14. Progress tracker

- [x] 0.1 Accounts and keys [Rob] · [x] 0.2 Scaffold monorepo · [x] 0.3 Verification spike
- [x] 1.1 Schema and market data · [x] 1.2 Context, on-chain, macro · [x] 1.3 Analytics engine · [x] 1.4 Daily jobs
- [x] 2.1 Read API and auth · [x] 2.2 Deploy
- [ ] 3.1 Shell and Overview · [ ] 3.2 Charts · [ ] 3.3 Cycles and Stats · [ ] 3.4 Data, Settings, invite friends [Rob]
- [ ] 4.1 On-chain & Macro tab · [ ] 4.2 desk-mcp and Claude desktop [Rob]
- [ ] 5.1 Agent backend · [ ] 5.2 Agent UI · [ ] 5.3 Multi-agent desk
- [ ] 6.1 MCO ingest · [ ] 6.2 MCO tab and overlays · [ ] 6.3 Wave-label review
- [ ] 7.1 Weekly signals job · [ ] 7.2 Scoring and Signals UI
- [ ] 8.1 Ops and monitoring · [ ] 8.2 Public readiness, README, CV

## 15. Open items

- Resolved in Stage 0.3 (see `docs/DATA_SOURCES.md` and D20 to D30): on-chain coverage (realized cap derived), dominance history (not free; daily snapshots), Gemini YouTube URLs (free preview, 8 h/day), Clerk invite-only (free), Cloud Run streaming (supported, timeout up to 60 min), Coinbase 4H (no; resampled from 1h), MCO channel id.
- Still open from Stage 0.3:
  - Gemini free-tier RPM/RPD are only visible in AI Studio; check them there before Stage 6.1, and retry `gemini-3.8-flash` (503 during the probe);
  - YouTube Data API key for MCO discovery from CI (Stage 6.1, D26).
- [Rob] Double-check `config/calendar.yaml` (FOMC and CPI dates for 2026-10 to 2027-12) against the Fed and BLS pages; BLS blocks scripts, so the 2027 CPI dates were not machine-verified. Add 2028 dates by late 2027.
- [Rob] Spot-check the BTC 2013-cycle bottom (2011-11-18, $2.11 from Coin Metrics) on a public long-history chart: Bitstamp, the only other free source, disagrees (D35). Also spot-check 5 values (Section 9), e.g. the anchors in D35.
- Whether Rob wants other YouTube analysts added in the same pipeline (each needs the same private, attributed treatment).
- Whether friends should get their own watchlists (v1 has one shared watchlist managed by Rob).
- Optional later: Telegram or Discord bot commands (for example `/price SOL`, `/cycle`) that answer from the API.
