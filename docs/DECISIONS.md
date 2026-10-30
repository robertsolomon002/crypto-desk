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


## D32. Context data storage and as-of rules

*2026-10-29, Stage 1.2.*

- **Storage:** every numeric context source goes into `series` (unique on key and date, idempotent upserts): `fng` (alternative.me), `cm:<BTC|ETH>:<metric>` for `CapMrktCurUSD`, `CapMVRVCur`, `SplyCur`, `AdrActCnt`, `HashRate` (Coin Metrics; realized cap, realized price and NUPL are derived later from these, D21), `fred:<id>` (FRED, from 2010-01-01) and `dominance:<btc|eth>` (CoinGecko, percent). Headlines go into `news`, the macro calendar into `calendar_events`.
- **As-of rule:** a row dated D is known once D has ended in UTC, like a closed candle. Coin Metrics stores only days before today. Fear & Greed for D is published at 00:00 UTC on D. A dominance snapshot is dated by the UTC day of CoinGecko's `updated_at`, and a later run that day overwrites it.
- **FRED release lags:** FRED dates observations by period, not by publication, so as-of reads include a FRED row only once `date + release_lag_days <= as_of` (lags in `config/fred_series.yaml`). The lags are the measured maximum first-release delays for 2025-01 to 2026-10 (`output_type=4`): DTWEXBGS 8, DGS10 6, DFF 6, M2SL 60 (measured 51–58). Exact per-row release dates were rejected: ALFRED caps a request at 2,000 vintage dates (DGS10 and DFF have more than 5,000), and DTWEXBGS has no vintages before 2019. Values are the latest vintage, so small revisions are not point-in-time; acceptable for context panels. Readers called without `as_of` return everything stored, all of which has been published.
- **Incremental updates:** Fear & Greed asks for (days since last + 3); Coin Metrics refetches from (the coin's latest stored day − 3) for stored metrics, so ETH `HashRate`, which stops at the Merge (2022-09-14), does not pull the start back; metrics never stored are fetched from 2009. FRED refetches the last 365 days each run to pick up revisions (M2SL).
- **Headlines (untrusted):** titles are parsed with `html.parser` and reduced to plain text (script and style bodies dropped, entities decoded, control characters removed, 300-character cap); only http(s) links are kept, without fragments or `utm_*`/`mc_*`/`fbclid`/`gclid`/`ref`/`taid` parameters. Coins are tagged by whole-word, case-insensitive matches of the symbol and `coins.aliases` in the title and summary (summaries are not stored). Duplicates are dropped by canonical URL and by case-folded title, also against stored rows. Future publish times are clamped to the fetch time.
- **Calendar:** `config/calendar.yaml` is the source of truth; `sync` inserts, updates and deletes rows to match it. The as-of reader returns events in a window around `as_of`, since the schedules are public in advance.
- **CLI:** `desk data update` with no flags refreshes every source; each runs independently, failures are reported and the exit code is 1 if any failed. Missing FRED or CoinGecko keys skip that source with a warning. FRED errors are re-raised without the request URL because the API key is in the query string.

## D33. Analytics conventions

*2026-10-29, Stage 1.3.*

- **Pure functions** in `desk.analytics` take the frames the data layer returns (`market.load_daily`, `coinmetrics.load_onchain`) and never touch the database. `analytics.registry` adapts them to `(inputs, coin, as_of, **params) -> JSON`, and the CLI, the cache, the look-ahead test, the API and desk-mcp all go through it.
- **`as_of` (a UTC date or None):** every function first truncates its inputs to dates `<= as_of`, so the candle for `as_of` is included (it closed at the end of that day). All computations are causal: trailing windows only, no backward fill, no statistics over the full sample. Weekly views use complete Monday-to-Monday weeks only (`resample_weekly`), so a week in progress never leaks.
- **Close-only rows** (the Coin Metrics backfill, D31) use the close as high and low wherever those are needed.
- **Look-ahead test** (`tests/test_lookahead.py`): for every registry function, every coin and 50 seeded random `as_of` values, `f(full, as_of)` must equal `f(full truncated at as_of, as_of)`. For time-series outputs, `f(full, None)` cut at `as_of` must also equal `f(full, as_of)`, which catches centered windows, backfill and full-sample normalization.

## D34. Regime rules (frozen)

*2026-10-29, Stage 1.3. Written before the code and never tuned on outcomes. Changing them needs a new decision and, once signals exist, a new signal version.*

The label is evaluated daily on closes. Rules are checked in this order, and the first match wins:

1. `insufficient_data`: fewer than 365 daily closes up to that day.
2. `high-vol`: 30-day realized volatility (std of daily log returns × √365) is above the 90th percentile of its own values over the trailing 365 days (including that day).
3. `uptrend`: close > SMA200 **and** SMA50 > SMA200 **and** SMA50 > SMA50 of 20 days earlier.
4. `downtrend`: close < SMA200 **and** SMA50 < SMA200 **and** SMA50 < SMA50 of 20 days earlier.
5. `range`: everything else.

The function returns the label series, the current label, and the values that produced it (close, SMA50, SMA200, SMA50 20 days earlier, volatility, volatility threshold), so the UI and the agent can show why.

## D35. Cycle anchors, zigzag defaults and the analytics cache

*2026-10-29, Stage 1.3.*

- **`config/cycles.yaml` restructured:** each cycle now runs bottom → halving → top and is named after the year of its top (`2013`, `2017`, `2021`, `2025`). The old file paired each top with the bear-market bottom that *followed* it, which breaks bottom alignment. Rob confirmed the current BTC top on 2026-10-29 (window 2025-09-01 to 2025-12-31). ETH uses BTC's halving dates; its 2017 cycle has no bottom because Coinbase ETH data starts 2016-05-18.
- **Anchors** are the lowest (highest) daily close inside each window. An anchor exists only once its window has ended by `as_of`, so hindsight windows never leak into earlier views. Found in Stage 1.3:

| Coin | Cycle | Bottom | Halving (first close on or after) | Top |
|---|---|---|---|---|
| BTC | 2013 | 2011-11-18 $2.11 | 2012-11-28 $12.33 | 2013-12-04 $1,134.93 |
| BTC | 2017 | 2015-01-14 $175.64 | 2016-07-09 $657.61 | 2017-12-16 $19,650.01 |
| BTC | 2021 | 2018-12-15 $3,183.00 | 2020-05-11 $8,572.40 | 2021-11-08 $67,554.84 |
| BTC | 2025 | 2022-11-21 $15,760.14 | 2024-04-20 $64,968.87 | 2025-10-06 $124,720.09 |
| ETH | 2017 | – | 2016-07-09 | 2018-01-13 $1,386.02 |
| ETH | 2021 | 2018-12-14 $83.00 | 2020-05-11 | 2021-11-08 $4,811.90 |
| ETH | 2025 | 2022-06-18 $993.64 | 2024-04-20 | 2025-08-22 $4,831.24 |

- **Independent check** (`desk analytics verify-anchors`, run 2026-10-29): anchors from Coinbase are compared with Coin Metrics `PriceUSD`, and those from the Coin Metrics backfill with Bitstamp. An anchor passes if the independent extreme in the same window is within 5% of our price and within 2 days of our date, or is a *near-tie* (the independent close on our date is within 1% of its own extreme). **12 of 13 pass.**
  - Same day, within 0.5%: 2013 top, 2017 bottom (Bitstamp, +2.5%), 2017 top, 2021 bottom and top, 2025 top, and every ETH anchor (the ETH 2021 bottom is 1 day apart).
  - **2025 bottom, a near-tie:** Coin Metrics' lowest close is 2022-11-09 ($15,758.29), against ours on 2022-11-21 ($15,760.14). It is a double bottom (the FTX crash and its retest) $2 apart, and Coin Metrics' close on 2022-11-21 is $15,778.02.
  - **2013 bottom fails against Bitstamp:** Bitstamp's lowest close in Oct–Dec 2011 is 2011-10-20 ($2.24), and its close on 2011-11-18 is $2.50, against Coin Metrics' $2.11. Bitstamp had just launched and was thin in 2011, and there is no other free daily source for that period. We keep the Coin Metrics anchor; Rob spot-checks it on a public long-history chart.
- **Zigzag defaults:** the reversal threshold is `clip(k·σ, floor, cap)`, with σ the rolling std of log returns. Daily: k=4, σ over 30 days, floor 5%, cap 35%. Weekly: k=2, σ over 26 weeks, floor 10%, cap 50%. Before σ exists the cap is used. Pivots alternate high and low; the last is the open leg (`confirmed=false`), and each confirmed pivot records the bar that confirmed it. On real data this gives about 20 daily swings a year for BTC.
- **Key levels** use the intraday high for the ATH ($126,296 on 2025-10-06), while cycle anchors use closes.
- **`analytics_cache`:** keyed by (function, sha256 of name + coin + params, `as_of`), where `as_of` defaults to the coin's last candle date. Each row stores a fingerprint, `max(date):count:sum(close)` of the input candles (plus the same over `cm:<coin>:*` series for on-chain), and a mismatch recomputes and overwrites the row, so new days and late corrections invalidate it. `desk analytics refresh-cache` precomputes the heavy functions (cycles in all three modes, ROI, YoY, seasonality, distribution, drawdown episodes) for the active coins and prunes rows not recomputed for 30 days: 32 entries in about 8 s on Neon.
- **A bug found by the hand-computed tests:** building a frame from a Series with a shifted index *aligns* the values instead of moving them, so the 20-week band had been applied to the week it summarizes. That is a leak the look-ahead test cannot see, because the full and truncated runs are equally wrong. It is fixed with plain arrays. A mutation check confirmed that the look-ahead test does catch centered windows and anchors resolved from full data.

## D36. Daily job and alerts

*2026-10-29, Stage 1.4.*

- **Daily job** (`desk jobs daily`, `.github/workflows/daily.yml`, cron `20 0 * * *` plus manual dispatch): it refreshes every source through `desk.data.update.update_all` (the same code as `desk data update`), checks freshness, refreshes `analytics_cache`, and writes a `job_runs` row (`running`, then `success` or `failed` with the problems listed in `error`). The concurrency group `daily` queues overlapping runs instead of cancelling them, so a run is never killed mid-write. The pooled `DATABASE_URL` secret is used; migrations are not part of the job (they need the direct host, D31).
- **What fails the run:** any source failing (including an RSS feed returning nothing), any active coin without yesterday's candle, or an unexpected error. Lagging context series are only notes: Fear & Greed more than 1 day old, Coin Metrics more than 2 days old (community data for yesterday may not be published by 00:20 UTC; the 3-day overlap catches up the next day), and ETH `HashRate` never, because it ended at the Merge. A failure exits 1, and the workflow's `if: failure()` step sends `ops_failure` with the summary (passed through a file) and the run link (passed through an env var), never through `${{ }}` inside `run:`. Successful runs send nothing.
- **Alerts** (`desk.notify`): `send(Alert(event, title, body, url))` routes by `config/settings.yaml` `alerts`. Routing is validated: unknown events or channels are errors, and admin-only events (`ops_failure`, `mco_review_pending`) can never be routed to the public Discord channel. A channel with a missing secret is skipped with a warning; a failed channel never stops the others, and `send` does not raise for delivery problems.
  - **Telegram:** plain text (no `parse_mode`, so untrusted text cannot become markup), web page previews off, 4096 characters.
  - **Discord:** Markdown escaped (no injected masked links, formatting or quotes) and `allowed_mentions: {"parse": []}` (no @everyone or role pings), 2000 characters; the link is appended unescaped.
  - Both count length in UTF-16 code units and truncate with "…". Both retry 429 after the server's `retry_after` / `Retry-After` (capped at 30 s), and retry 5xx and network errors with backoff, 3 attempts in total. Errors name the channel and HTTP status only, never the token or webhook URL.
- **Checks:** `desk notify test` sends one test message per channel; the workflow's `notify_test` input runs it from GitHub to prove the repository secrets. Live tests on 2026-10-29: Telegram and both Discord webhooks delivered from Rob's PC, and `desk jobs daily` against Neon succeeded in 10 s.

## D37. Read API, auth and roles

*2026-10-29, Stage 2.1.*

- **Clerk tokens** (checked against Clerk's docs on 2026-10-29, details in `DATA_SOURCES.md`): the frontend sends the session token as `Authorization: Bearer`. `api/auth.py` verifies it with PyJWT (D16): RS256 only, keys from `<issuer>/.well-known/jwks.json` through a cached `PyJWKClient`, `exp`/`iat`/`iss`/`sub` required, 5 s leeway, `azp` checked against `CORS_ORIGINS` when present, `sts == "pending"` rejected. Every failure is a generic 401 that never echoes the token. The issuer is `CLERK_ISSUER` or is decoded from `VITE_CLERK_PUBLISHABLE_KEY` (`pk_test_`/`pk_live_` plus unpadded base64 of `<frontend-api-host>$`, Clerk's documented format). Verified live: the issuer decoded from Rob's key serves a JWKS with one RS256 signing key.
- **Roles live in the `users` table**, not in Clerk metadata: public metadata is not a default session-token claim, and adding it means customizing the token. A user row is created as `member` on first sight. `ADMIN_CLERK_IDS` (JSON list) is promoted to `admin` on every login, so a DB reset never locks Rob out. Admins change roles through `PATCH /api/admin/users/{id}`; the last admin and `ADMIN_CLERK_IDS` users cannot be demoted. Users are cached in memory for 60 s, and a role change drops the cache entry. *Roadmap Section 3.6 updated.*
- **Every router except health** declares `require_role("member")` or `require_role("admin")` at router level. `tests/test_api_routes.py` lists a sample request for every operation in the OpenAPI schema and checks anonymous (401), member (403 on admin routes, success elsewhere) and admin (success) on each one; a new route fails the test until it is added.
- **Response envelope:** every data route returns `{as_of, sources, data}`. `as_of` is the last UTC date the data covers; `sources` names each source (`coinbase`, `coinmetrics`, `fred` with the series URL, `alternative.me`, `rss`, `desk.analytics` with the function). Routes take `as_of` (future dates are 422) and pass it to the same readers and registry functions as the CLI, so look-ahead rules (D33) and FRED release lags (D32) apply unchanged. Analytics results are `data.result` exactly as `registry.run_json` returns them; per-tab types come in Stage 3. Heavy functions go through `analytics_cache`.
- **Selectable indicators:** `GET /api/indicators/{coin}?sma=20,50&ema=200&bb=20:2&rsi=14&macd=12:26:9&vol=30&band=true` uses `indicators.custom`, built from the same causal primitives; columns are named by their parameters. Bounds: windows 2 to 400, at most 6 per type, `fast < slow`. It has its own look-ahead test and a test that it equals the fixed `indicators` function at the default settings.
- **Data tab:** only tables in `api/tables.py` can be browsed. Members see market, context, news, calendar, signals and briefs; conversations, messages and agent snapshots are own-rows-only (a filter cannot widen this); users, job runs, LLM spend, the analytics cache and all MCO tables are admin-only (Decision 6), and MCO tables disappear when `MCO_ENABLED=false`. Filters are `column:op:value` (`eq ne gt gte lt lte contains`) on allowlisted columns, with values cast to the column type and sent as bound parameters; `contains` escapes `%` and `_`. Pages hold at most 500 rows. CSV export streams at most 200,000 rows and prefixes text cells starting with `= + - @`, tab or CR with `'` (CSV injection; headlines are untrusted).
- **User LLM keys:** an outermost ASGI middleware removes `X-LLM-Key` from the request headers before CORS, logging or any route sees it, and keeps it only as a `SecretStr` in `request.state.llm_key`. A log record factory also replaces that request's key with `[redacted]` in any log message (for example an f-string). The canary test sends a key to normal, 401, 403, 404, 422, 500 and preflight requests, plus probe routes that log headers and the raw key, and asserts the key is absent from every log record, response body, header and database table.
- **Rate limit:** 120 requests per minute per user (`config/settings.yaml` `api.rate_limit_per_minute`), sliding window, 429 with `Retry-After`. It runs after authentication, so it is keyed by user. It is in memory and per instance: with Cloud Run max 2 instances a user can get up to 240 per minute. Good enough for a few friends; a shared store would be needed if it opens up.
- **Caching:** GZip for responses of 1 KB and up. GET 200 JSON responses get a weak ETag (sha256 of the uncompressed body), `Cache-Control: private, no-cache`, and 304 on `If-None-Match`. The heavy computation is already saved by `analytics_cache`; ETags save bandwidth on repeat views.
- **Admin routes:** the watchlist (max 10 from `coins.yaml`, upper-case symbols, market `<SYMBOL>/USD`; removing a coin sets `active=false` so its history stays, and the next daily job backfills a new coin). The database is now the source of truth for the watchlist. Invites are proxied to Clerk's Backend API (`GET /v1/invitations`, `POST /v1/invitations` with `email_address`, `notify`, `redirect_url`, `POST /v1/invitations/{id}/revoke`) with `CLERK_SECRET_KEY`. The list accepts a plain array or `{data, total_count}`, and `created_at` is read as milliseconds; both will be confirmed on the first live call (3.4). Clerk errors are passed through with their message, and unreachable is 502.
- **Frontend client:** `src/lib/api.ts` gets `setTokenGetter`, which the Stage 3.1 shell connects to Clerk's `getToken`. `VITE_API_BASE_URL` now falls back to the page origin when it is empty, not only when it is missing (the local `.env` has it empty, which broke the health test locally).

## D38. Deploy: Cloud Run, Cloudflare Pages, CORS and CSP

*2026-10-30, Stage 2.2. How to operate it is in `docs/OPS.md`; the free-tier facts behind these choices are in `DATA_SOURCES.md`.*

- **Backend on Cloud Run** (`desk-api`, `us-central1`, project `crypto-desk-513023`): 1 vCPU, 512 MiB, request-based billing (`--cpu-throttling`), startup CPU boost on (billed as normal CPU time, inside the free tier), min 0 / max 2 instances, concurrency 40, request timeout 900 s (room for the agent's SSE streams in 5.1). It runs as `desk-api@` (runtime service account), which can read only the two secrets it uses.
- **Deploy pipeline** (`deploy-backend.yml`): runs after CI passes on a push to `main` (`workflow_run`, checked out at CI's `head_sha`) or by hand, never for pull requests. Steps: skip if the API is unchanged since the live revision → build and push `…/desk/api:<sha>` → `desk db upgrade` → `gcloud run deploy --no-traffic --tag candidate` → smoke test on the candidate's tag URL → `update-traffic --to-latest`. A revision that fails the smoke test never serves users. Failures alert the admin channels (`ops_failure`).
- **Workload Identity Federation, no JSON keys:** pool `github`, provider `crypto-desk`, attribute condition `repository_id == 1437208542 && ref == refs/heads/main` (the numeric id survives a rename and rules out a look-alike repo). Only that principal set may impersonate `desk-deployer@`, which has `run.developer` (project), `artifactregistry.writer` (repo `desk` only) and `iam.serviceAccountUser` on `desk-api@` only.
- **Public access without run.admin in CI:** disabling the invoker IAM check needs `run.services.setIamPolicy` (in `run.admin`, not `run.developer`). So the service is created once by hand with `--no-invoker-iam-check` (OPS.md), and CI deploys with `run.developer`, which keeps that setting. Auth is the app's job (a Clerk JWT on every route but health).
- **Secrets:** Secret Manager holds only what the service reads: `database-url` (the Neon pooled URL) and `clerk-secret-key`, mounted as env vars from `:latest` at instance start. That is 2 of the 6 free active versions; the Anthropic and LangSmith keys join in 5.1. The jobs keep running in GitHub Actions with GitHub secrets, so their secrets are not mirrored. *Roadmap 2.2 said "mirror the backend secrets"; mirroring all of them would go past the 6 free versions. Roadmap updated.*
- **Non-secret service config** is a `--env-vars-file` written by `desk deploy env-file`, which validates it (https origins only, anchored regex, a `pk_` key, `user_` ids) so a typo fails the deploy instead of locking users out. `ADMIN_CLERK_IDS` comes from the repo variable of that name (empty until Stage 3.1).
- **Migrations** run in their own step over Neon's direct host (`desk db upgrade` strips `-pooler` from the pooled host, D31), before the new revision gets traffic, never on app start. The old revision keeps serving during that window, so **migrations must be backward compatible with the running code** (add columns and tables; drop or rename only in a later deploy).
- **Smoke test** (`desk deploy smoke`): health (retried through a cold start), 401 without a token, CORS preflight allowed for the Pages origin and refused for `https://evil.example`, then one authenticated call. That call uses a dedicated Clerk test user (`external_id` `desk-smoke`, `desk-smoke+clerk_test@example.com`, no password) created on first use: a session from `POST /v1/sessions` and a 120 s token from `POST /v1/sessions/{id}/tokens`, then `GET /api/me` (must be `member`) and `GET /api/coins` (must include BTC); the session is then revoked. Clerk's spec says create-session "is intended only for use in testing, and is not available for production instances", so with an `sk_live_` key that part is skipped with a warning. The smoke user is an ordinary member row in `users`.
- **Frontend on Cloudflare Pages** (project `crypto-desk`, production branch `main`): direct upload with a pinned wrangler, no Git integration, so builds stay in GitHub Actions. The bare `crypto-desk.pages.dev` was taken, so the site is **`crypto-desk-a9f.pages.dev`**. Production deploys run after CI passes on `main`; every same-repo pull request gets a preview at `<branch>.crypto-desk-a9f.pages.dev`. Both call the production API. A smoke step checks `/` and a deep link (SPA fallback) for the root div and the CSP header.
- **Pages vs Workers:** wrangler 4.153 redirects `pages project create` to Workers static assets when it detects an AI agent and the project is new ("the latest version of Cloudflare Pages, now part of Cloudflare Workers"). That redirect failed for an empty project. Rob chose classic Pages, as in the roadmap, so the project was created once with `--force`. CI is not an agent and the project now exists, so deploys go straight to Pages. Workers static assets stays the fallback if Pages is ever retired.
- **CORS:** `CORS_ORIGINS=["https://crypto-desk-a9f.pages.dev"]` plus the new `CORS_ORIGIN_REGEX=^https://[a-z0-9-]+\.crypto-desk-a9f\.pages\.dev$` for previews. The Clerk `azp` check accepts the same list and regex, both with `fullmatch`, so CORS and auth never disagree. Tests cover look-alike hosts (`…pages.dev.evil.example`), plain http and other projects.
- **CSP and security headers** (`frontend/src/lib/security-headers.ts`, from Clerk's CSP guide, checked 2026-10-30):
  - `default-src 'self'`;
  - `script-src 'self'` plus the Clerk Frontend API host (decoded from the publishable key), `https://challenges.cloudflare.com` and `https://*.protect.clerk.com`;
  - `connect-src 'self'` plus the API origin, Clerk and `https://*.protect.clerk.com:*`;
  - `img-src 'self' data: https://img.clerk.com`;
  - `style-src 'self' 'unsafe-inline'` (Clerk's runtime CSS-in-JS; Lightweight Charts injects a `<style>` and inline SVG, nothing external);
  - `worker-src 'self' blob:`; `frame-src` challenges and protect;
  - `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`.

  No `'unsafe-inline'` or `'unsafe-eval'` for scripts. Also `nosniff`, `strict-origin-when-cross-origin`, a restrictive `Permissions-Policy` and HSTS. `vite build` writes these headers to `dist/_headers`, and `vite preview` sends the same ones, so the Playwright smoke tests run under the production CSP and fail on any violation.
- **Free-tier guard rails:** max 2 instances; 2 secret versions of 6. **Artifact Registry:** the first image measured 415 MB, so keeping 3 (the first plan) would be about 1.2 GiB against 0.5 GiB free. The repo now keeps only the newest image and deletes replaced ones once they are an hour old (the cleanup job runs about daily). Pushes that change nothing under `backend/`, `config/` or `prompts/` since the live revision's commit build no image at all (manual runs always deploy). Consequence: a traffic rollback to an older revision works only until its image is cleaned up; after that, roll back by reverting the commit (OPS.md). Shrinking the image (ccxt, pandas and the LangChain stack dominate) is a later option. The GCP budget alert at $1 (Section 7) is a [Rob] step, because `gcloud` here cannot read the billing account.

## D39. App shell, Overview API and test-only sign-in

*2026-10-30, Stage 3.1.*

- **`GET /api/overview`** (Rob's choice over composing per-coin calls in the browser): one call returns the coin cards and the freshness strip, so a cold start costs one request instead of 10 or more. The card values come from a new registry function `summary` (`analytics/summary.py`: last close; 1d/7d/30d change against the last close on or before N calendar days earlier; ATH from highs with the close fallback, D31; distance from ATH; the D34 regime label), so the look-ahead test covers it. Measured on Neon data: 0.3 s warm, 1.4 s first call. Signal and MCO bias are `null` until v1.3 and v1.2. Freshness: last date of prices, Fear & Greed, dominance, FRED and headlines, each with a max age (2 days; FRED 62 days because of monthly series and release lags, D32); stale is judged against `as_of` or today. The daily job's status and times are shown to members, but its error text stays in `job_runs` (admin-only). With `as_of`, `daily_job` is null.
- **Feature flags for tabs:** `/api/me` now returns `features` (`onchain_macro`, `mco`, `agent`, `signals`) from `config/settings.yaml`. A new `mco_tab: false` flag separates showing the MCO tab (v1.2) from `mco`, which governs MCO data (Decision 6); the reported `mco` is `mco_tab && mco && MCO_ENABLED`. Unbuilt v1 tabs (Charts, Cycles, Stats, Data, Settings) show a "Coming in Stage x" page; the Data placeholder already accepts the `?table=&coin=` deep links that every "View data" link uses.
- **Test-only sign-in for Playwright** (Rob's choice over Clerk testing tokens, which need the secret key and network in CI): `VITE_E2E_FAKE_AUTH=1` swaps Clerk for a fixed signed-in user. Guards: Vite inlines the flag, so normal builds drop the fake module (no chunk is emitted); `vite.config.ts` refuses the flag when `VITE_API_BASE_URL` is anything but `http://localhost[:port]`, and deploys always set the Cloud Run URL; a unit test checks that `deploy-frontend.yml` and `ci.yml` never set it and that only `playwright.config.ts` does. Even if it shipped, the backend rejects its token. Playwright builds call the API on the preview origin, where `page.route` answers.
- **Shell:** the selected coin lives in the URL (`?coin=`), and tab links carry only that parameter. Phones (<768 px) get a bottom bar with the first 4 tabs plus a "More" menu. The cold-start banner shows when nothing has loaded yet and requests have run for 1.5 s. Errors: one app-level boundary, one per route (reset on navigation), and a Retry per card; 4xx responses are not retried, 5xx once.
- **Theme:** one token set in `index.css`, dark by default (a saved choice, then the system preference), applied in `main.tsx` before the first render because the CSP forbids inline scripts. Positive and negative are blue-green and orange-red, and changes always carry a sign and an arrow. Series colors are Okabe-Ito. Every text pair passes WCAG AA (computed from the OKLCH values: lowest is warning on background at 4.74:1 in light).
- **Fear & Greed gauge** is a small SVG, not ECharts, to keep the Overview light; ECharts arrives with the Cycles and Stats tabs.

