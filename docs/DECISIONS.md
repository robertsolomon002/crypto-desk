# Decisions

One entry per decision, newest last. D1 to D13 are copied from ROADMAP Section 2. Never rewrite an entry: add a new one that supersedes it.

## D1. Users and access

*2026-10-26, locked with Rob (ROADMAP Section 2).*

invite-only for now (Rob plus a few friends), with roles `admin` (Rob) and `member`. Built multi-user from day one so it can open up later. Features can be switched off per deployment and per role (for example `MCO_ENABLED`).

## D2. Friends bring their own LLM key

*2026-10-26, locked with Rob (ROADMAP Section 2).*

, and setup must be as simple as possible. The recommended path is one **OpenRouter** key (one signup, one key for Claude, GPT, Gemini and more, with a spending limit they set themselves). Anthropic and OpenAI keys are also accepted. The key is kept **in the friend's browser** and sent with each agent request over HTTPS. The backend never stores or logs it. Rob uses a server-side key, capped by Decision 9.

## D3. Coins

*2026-10-26, locked with Rob (ROADMAP Section 2).*

BTC, ETH and SOL, plus a watchlist (max 10) that Rob manages in Settings. Cycle and on-chain tools mostly cover BTC and ETH.

## D4. Device

*2026-10-26, locked with Rob (ROADMAP Section 2).*

desktop first (dense, terminal-like layouts), with a simplified but complete phone layout.

## D5. Hosting: $0, free tiers only

*2026-10-26, locked with Rob (ROADMAP Section 2).*

The stack is in Section 6. Cold starts of a few seconds after idle are acceptable.

## D6. MCO content stays private

*2026-10-26, locked with Rob (ROADMAP Section 2).*

Only his **free public YouTube videos** are used. Every summary is short, attributed and links to the video. MCO-derived data lives only in the private database, never in the public repo, never on a public page, and never in exports for non-admins beyond on-screen display. If the app ever goes public, the MCO tab is switched off unless MCO gives permission. Paywalled content is never ingested.

## D7. MCO wave labels are approximate

*2026-10-26, locked with Rob (ROADMAP Section 2).*

They are extracted by an AI from the video and snapped to real swing pivots. **Only labels Rob approves** are shown on charts to members. Extracted levels and invalidation lines can be shown right away, marked "AI-extracted from video".

## D8. Signals format (weekly, 1-week horizon)

*2026-10-26, locked with Rob (ROADMAP Section 2).*

per coin, `lean_long` or `flat` (no shorts), a confidence (0.5 to 0.95), an entry zone, an invalidation level, a target and a short rationale. The scorecard tracks direction hit rate, calibration (Brier), whether the target or the invalidation was hit first, and a simple paper P&L with costs. It compares four sources: the desk, a coin-flip baseline, a trend-rule baseline, and MCO's extracted bias. The signal definition is versioned; any change creates a new version and never rewrites old records.

## D9. Rob's LLM budget

*2026-10-26, locked with Rob (ROADMAP Section 2).*

hard cap **$8 per month** on the server key, enforced in code. If spend gets near the cap, it degrades in this order:
1. Rob's own chat moves to a cheaper model;
2. MCO summaries skip lower-priority videos;
3. the weekly brief writer moves from Sonnet to Haiku.
Weekly signals are never skipped.

## D10. Models

*2026-10-26, locked with Rob (ROADMAP Section 2).*

Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) for agents and the desk, Claude Sonnet 5.5 (`claude-sonnet-5-5`) for the weekly brief writer, and a Gemini Flash-class model for video summaries (Section 3.4). All ids and prices are verified in Stage 0.3. Friends pick any model their key allows; the default is a cheap one.

## D11. Alerts

*2026-10-26, locked with Rob (ROADMAP Section 2).*

Telegram (to Rob) and Discord (a channel Rob's friends can join). Events: weekly brief ready, key-level crossings, new MCO video summarized, ops failures. Ops failures go to admin channels only.

## D12. Your own MCP server (`desk-mcp`)

*2026-10-26, locked with Rob (ROADMAP Section 2).*

wraps the same analytics functions the API uses. The in-app agent uses it, and Rob can also use it from the Claude desktop app. Each tool is defined once and reused in both places.

## D13. Build order

*2026-10-26, locked with Rob (ROADMAP Section 2).*

- **v1:** Overview, Charts, Cycles, Stats, Data, Settings.
 - **v1.1:** On-chain & Macro, Agent.
 - **v1.2:** MCO.
 - **v1.3:** Signals.
 - **Hardening.**
 Each version is usable by friends before the next one starts.

## D14. TypeScript 6.0, not 7.0

*2026-10-28, Stage 0.2.*

create-vite 9.3.3 pins `typescript ~7.0.2`, but the newest `typescript-eslint` (8.72.1) declares the peer range `>=4.8.4 <6.1.0`, and `npm install` fails with ERESOLVE. The frontend pins `typescript ~6.0.3`. `openapi-typescript` 7.13.0 declares the peer `typescript ^5.x`; `package.json` has an npm `overrides` entry so it uses our TypeScript 6, and generation was checked to work (`npm run gen:api`). Revisit when `typescript-eslint` supports TS 7.

## D15. `@clerk/react` instead of `@clerk/clerk-react`

*2026-10-28, Stage 0.2.*

npm marks `@clerk/clerk-react` (5.61.3) as deprecated: "Please use @clerk/react instead" (Clerk Core 3 upgrade guide: https://clerk.com/docs/guides/development/upgrading/upgrade-guides/core-3). The frontend uses `@clerk/react` 6.x. ROADMAP updated.

## D16. Clerk JWTs verified with PyJWT and JWKS

*2026-10-28, Stage 0.2.*

The roadmap allows `clerk-backend-api` or PyJWT with JWKS. The backend uses `pyjwt[crypto]` (one small dependency, standard RS256 verification with a cached JWKS client). Stage 2.1 confirms the issuer, JWKS URL and claims against Clerk's current docs before writing `api/auth.py`.

## D17. Generated API client: openapi-typescript and openapi-fetch

*2026-10-28, Stage 0.2.*

The backend writes `frontend/openapi.json` (`desk api openapi`), `npm run gen:api` turns it into `src/lib/api-schema.ts`, and `src/lib/api.ts` wraps it with `openapi-fetch`. Both files are committed; CI fails if either is stale. The client looks `fetch` up on every call because `openapi-fetch` 0.17 otherwise captures `globalThis.fetch` at creation time, which breaks test stubs.

## D18. Docker image built from the repo root

*2026-10-28, Stage 0.2.*

`backend/Dockerfile` is built with `docker build -f backend/Dockerfile .` so `config/` and `prompts/` are in the image (`DESK_ROOT=/app`). It uses the official uv binary image pinned to the same uv version as dev (0.11.7), `uv sync --locked --no-dev`, a non-root user, and listens on `$PORT` (Cloud Run). CI builds it and calls `/api/health`.

## D19. Tooling defaults chosen in the scaffold

*2026-10-28, Stage 0.2.*

- ESLint (create-vite now defaults to Oxlint; the roadmap requires ESLint), with `eslint-config-prettier`. Prettier: no semicolons, single quotes, width 100.
- shadcn/ui 4.23 with the `radix` base and the default `nova` preset. The terminal look is designed in Stage 3.1.
- Ruff rules include `DTZ` so naive datetimes fail lint (UTC everywhere).
- One `.env` at the repo root for both apps; Vite reads it with `envDir: '..'` and only exposes `VITE_*` variables.
- The CLI gains an `api` group (`desk api serve`, `desk api openapi`) next to the Section 4 groups.
- `.gitattributes` forces LF line endings so Windows and Ubuntu agree.

## D20. Price history: Coinbase canonical, Coin Metrics for early BTC

*2026-10-28, Stage 0.3.*

Coinbase (`ccxt` id `coinbase`) stays canonical for daily OHLCV: BTC from 2015-07-20, ETH from 2016-05-18, SOL from 2021-06-17, no key, works from US cloud IPs. BTC before 2015-07-20 (needed for the 2013 cycle) comes from Coin Metrics `PriceUSD` (from 2010-07-18), stored with `source=coinmetrics` and close-only (no OHLC). Bitstamp (BTC from 2011-08-18) is the fallback exchange if Coinbase fails. See `docs/DATA_SOURCES.md`.

## D21. On-chain: realized cap is derived

*2026-10-28, Stage 0.3.*

`CapRealUSD` is not in the Coin Metrics community catalog. Realized cap is derived as `CapMrktCurUSD / CapMVRVCur`, realized price as realized cap / `SplyCur`, and NUPL as (market cap − realized cap) / market cap. Stored metrics: PriceUSD, CapMrktCurUSD, CapMVRVCur, SplyCur, AdrActCnt, HashRate (BTC; ETH hash rate ends at the Merge).

## D22. 4H candles: resampled from Coinbase 1h

*2026-10-28, Stage 0.3.*

Coinbase has no native 4h timeframe (it has 1h, 2h and 6h). 4H bars are resampled from closed Coinbase 1h candles on 00/04/08/12/16/20 UTC boundaries, keeping one canonical source. Only recent history (for example the last 180 days) is kept for 4H. Bitstamp's native 4h is the fallback.

## D23. BTC dominance: daily snapshot from now on

*2026-10-28, Stage 0.3.*

CoinGecko Demo has current dominance (`/global`) but no history: `/global/market_cap_chart` is Pro-only (401, error 10005) and coin history is capped at 365 days (error 10012). The daily job stores a `dominance:btc` (and `dominance:eth`) snapshot from Stage 1.2 onward, and the UI says when the series starts.

## D24. Server models: Haiku 5.5 replaces Haiku 4.5 (supersedes part of D10)

*2026-10-28, Stage 0.3, approved by Rob.*

Claude Haiku 5.5 (`claude-haiku-5-5`, $0.10/$0.50 per MTok for prompts up to 100K tokens) replaces Haiku 4.5 ($1/$5) for agents, chat and desk nodes; both passed the structured-output probe. Sonnet 5.5 (`claude-sonnet-5-5`, $2/$10) stays the brief writer. Decision 9 degradation: chat drops to Haiku 5.5 with effort `low`; the brief writer drops to Haiku 5.5. Friends' defaults: OpenRouter `anthropic/claude-haiku-5.5`, Anthropic `claude-haiku-5-5`; the OpenAI default is chosen in Stage 5.1 against OpenAI's own model docs. Haiku 5.5 counts about 25% more tokens for the same text (new tokenizer) and does not accept `budget_tokens`, prefill or non-default sampling parameters.

## D25. Video summaries: Gemini 3.5 Flash-Lite on the free tier

*2026-10-28, Stage 0.3.*

`gemini-3.5-flash-lite` read a 14-minute MCO video by YouTube URL in 10 s (about 84K input tokens) and returned schema-valid JSON. `gemini-3.8-flash` and `gemini-3.6-flash` returned 503 "high demand" at first; a later 3.8 Flash retry succeeded after 299 s. Stage 6.1 uses a chain: `gemini-3.5-flash-lite` → `gemini-3.8-flash`, each with backoff retries, then the title-and-description fallback marked "low detail". The probe's BTC bias ("bullish") contradicted its own downside C-wave targets, so `summarize.py` adds a deterministic consistency check (bias vs target direction relative to price) that marks the extraction `low` confidence, and wave labels stay behind Rob's approval (Decision 7). YouTube URL input is a free preview feature, and free-tier data may be used by Google (acceptable: only public videos and our prompt).

## D26. MCO discovery: RSS with a YouTube Data API fallback

*2026-10-28, Stage 0.3.*

MCO's channel id is `UCngIhBkikUe6e7tZTjpKK7Q`. Its RSS feed works from Rob's PC but failed on all three GitHub runner attempts (404, 500, 500). `mco/discover.py` tries the RSS feed first, then YouTube Data API v3 `playlistItems.list` on the uploads playlist (1 quota unit per call, 10,000 units/day by default). Stage 6.1 adds a [Rob] step: enable the YouTube Data API v3 in the `crypto-desk-gemini` project and add `YOUTUBE_API_KEY`.

## D27. Structured output uses `json_schema`

*2026-10-28, Stage 0.3.*

Forced `tool_choice` returns 400 on Claude Sonnet 5.5 (and Opus 5.5 / Fable 5.1). All structured-output calls use `with_structured_output(Schema, method="json_schema")`, which worked on Haiku 4.5, Haiku 5.5, Sonnet 5.5 and OpenRouter. Code never sets `tool_choice` to `any` or a named tool.

## D28. Agent constructor: `langchain.agents.create_agent` or an explicit graph

*2026-10-28, Stage 0.3.*

`langgraph.prebuilt.create_react_agent` is deprecated since LangGraph 1.0 in favor of `create_agent` in the `langchain` package (not yet a dependency; PyPI latest 1.4.7). Stage 5.1 adds `langchain` and uses `create_agent`, or builds the tool loop as an explicit `StateGraph`, after checking the installed source. Streaming uses `astream` with `stream_mode=["messages", "updates"]` (or `astream_events`) mapped to SSE `token`, `tool_start` and `tool_end` events. The `langchain-mcp-adapters` stdio round trip works (`MultiServerMCPClient` → `get_tools()`).

## D29. Clerk: Invite-only works on the free plan

*2026-10-28, Stage 0.3.*

Clerk renamed the sign-up mode setting to **Access mode** (User & authentication → Access mode); "Invite-only" is the dashboard label for `restricted`. Rob selected it on the free Hobby plan with no upgrade prompt. Hobby allows 50,000 monthly retained users; the "Secured by Clerk" branding stays (removing it is paid). Waitlist mode is the fallback.

## D30. Fallback per service

*2026-10-28, Stage 0.3.*

| Service | Fallback if the free tier changes or fails |
|---|---|
| Coinbase (prices) | Bitstamp via ccxt; Coin Metrics `PriceUSD` (close only) |
| Coin Metrics community | Derive what we can from price data; hide the affected on-chain panels |
| CoinGecko Demo (dominance) | Skip the day; keep the series gap-tolerant |
| FRED, Fear & Greed, RSS | Skip and mark stale in the Data tab freshness view |
| Gemini free tier | Paid Flash-Lite (about $0.30/month at 4 videos a day) under the D9 cap, else title and description only |
| YouTube RSS | YouTube Data API v3 (D26) |
| Cloud Run | Render or Fly.io free web service |
| Neon | Supabase free Postgres |
| Clerk | Supabase Auth, or Clerk Waitlist mode |
| Cloudflare Pages | GitHub Pages or Netlify free |
| LangSmith | Tracing off (it is optional) |
| Anthropic server key | Haiku 5.5 via OpenRouter on a capped key |

## D31. Market data storage rules

*2026-10-28, Stage 1.1.*

- **Closed candles only:** a daily bar is stored once `open time + 1 day <= now (UTC)`. Coinbase also returns the day in progress, which is dropped.
- **Incremental updates** refetch from (last stored Coinbase day − 3 days) and upsert on (coin, date), so re-runs are idempotent and late corrections are picked up. A coin with no rows pages forward from 2010-01-01 in 300-day windows (empty windows before listing are skipped).
- **BTC backfill (D20)** runs once: Coin Metrics `PriceUSD` for days before the first Coinbase day, stored close-only (`open`, `high`, `low`, `volume` null, `source=coinmetrics`). Coin Metrics never overwrites Coinbase days.
- **Weekly bars** are computed on the fly from daily (weeks start Monday 00:00 UTC and are labeled by that Monday; open first, high max, low min, close last, volume sum). Close-only days count their close as open, high and low. Weeks not fully covered by data (the current week, or a first partial week) are dropped unless asked for.
- **Validation** reports gaps, duplicate days, OHLC inconsistencies (`low <= open, close <= high`, prices > 0) and close-to-close moves over 40%. Flags are reported by `desk data status`, not stored or auto-corrected; Rob decides. Known real flags: Coinbase ETH has no candles for 2016-05-21 and 2016-05-22; big moves on BTC 2010-11-06, 2011-05-10, 2013-04-11, ETH 2020-03-12, SOL 2022-11-09.
- **`candles_4h` table** added now for D22 (not in the original Section 5) so Stage 3.2 only fills it.
- **Schema:** every Section 5 table is in migration `0001`; constraint names follow a naming convention in `models.Base.metadata`. Postgres-only types (JSONB, ARRAY, `ON CONFLICT`) are used freely: there is no SQLite path.
- **Tests:** Postgres tests use `TEST_DATABASE_URL` and create and drop their own throwaway database, never `DATABASE_URL` (which is Neon in `.env`). They run in a separate Ubuntu CI job with a Postgres service container (GitHub's Windows runners cannot run Linux service containers), which also checks that migrations round-trip and match the models (`alembic check`). On the Windows leg they are skipped.

