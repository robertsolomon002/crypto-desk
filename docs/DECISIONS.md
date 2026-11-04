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


## D40. Charts tab: indicators in the browser, ratio as a line

*2026-10-30, Stage 3.2.*

- **Indicators are computed in the browser** (`frontend/src/lib/indicators.ts`, a port of `analytics/indicators.py`): `/api/indicators` is daily-only, but the chart needs the same math on 1W, 4H and ratio bars, and computing locally means one OHLCV request per view and instant toggling. `/api/indicators` stays the source for the agent and the Data tab. **Parity:** `backend/tests/test_indicator_parity.py` writes `frontend/src/lib/__fixtures__/indicators_parity.json` (a synthetic random walk, no real data, through `indicators.custom`) and fails if the committed file is stale; `indicators.test.ts` checks the TypeScript output against it to 1e-9 relative, warm-up NaNs included. Regenerate with `uv run python tests/test_indicator_parity.py`.
- **20W band:** on 1D and 4H it comes from complete weekly closes and applies from the next Monday (same rule as the backend, D33); on 1W it is the 20-week SMA and 21-week EMA of the bars.
- **Ratio mode** (e.g. ETH/BTC) divides closes on the bars both coins have and plots a line: A/B highs and lows do not divide into a true OHLC. Volume, key levels and pivots are off in ratio mode.
- **Close-only backfill** (BTC before 2015-07-20, D31) is drawn as a thin line joined to the first candle; the readout says "close only (Coin Metrics)".
- **Pivots** use `/api/pivots` on 1D and 1W; on 4H the toggle is disabled, since pivots are computed on daily or weekly bars. **Levels** are today's `/api/levels` values on every timeframe except ratio.
- **Settings** live in `localStorage` under `desk.charts.v1.<clerk_id>`; stored JSON is validated field by field, so a corrupt or old value falls back to the defaults.
- **Lightweight Charts 5.2.1, checked in the installed typings and source:** sub-panes are native (`addSeries(def, options, paneIndex)`) and share the time scale and crosshair; a new pane copies pane 0's price scale options, so the RSI and MACD panes are set back to linear explicitly (otherwise MACD turned logarithmic in log mode). Colors must be sRGB strings, so the OKLCH theme tokens are resolved to `rgb()`/`rgba()` through a 1x1 canvas and re-read when the theme changes. Default price precision is 2 decimals, which flattens ratios and MACD, so each series gets a precision from its data (about 4 significant digits below 1). `attributionLogo` stays on (the license's link requirement), and the footer carries the NOTICE text and a link to tradingview.com.
- **Performance:** the full BTC history (about 5,950 daily bars, around 10 series) renders in well under a second in Playwright. The chart is created once per mount, series are synced by id, and data is re-sent only when it changes. The Charts tab is a lazy chunk (65 kB gzip), so the Overview's first load does not pay for the chart library.

## D41. Cycles and Stats tabs: ECharts, analytics deep links

*2026-11-01, Stage 3.3.*

- **Data comes straight from the existing `/api/cycles` and `/api/stats` routes** (one request per chart, no new endpoints). Cycles cover BTC and ETH only: for other coins the routes return 404 ("not available") and the tab says so instead of showing errors. ETH's first cycle has no bottom, so it is missing from bottom-aligned views and the ROI table.
- **Fix in `to_jsonable`:** a frame reindexed to `range(...)` keeps a `RangeIndex`, so its name (`month`, `weekday`) was dropped and the monthly and day-of-week summaries came out with no period key. A named `RangeIndex` is now kept as a column. These results are cached, but the cache fingerprint changes with each new candle, so old rows clear within a day; until then the frontend falls back to the row position (`periodOf`).
- **ECharts 6.1.0, checked in the installed source and typings:** modular imports (`echarts/core`, `charts`, `components`, `renderers`) with only Line, Bar, Heatmap and Scatter plus Grid, Tooltip, Legend, VisualMap, MarkLine and Aria registered. `EChart.tsx` creates one instance per mount, resizes with a `ResizeObserver` and replaces the option with `notMerge`. Findings: (1) a date string with no zone is parsed as **local** time (`parseDate` in `util/number.js`), so time-axis data goes in as UTC-midnight timestamps with `useUTC: true`; (2) labels inside a cell pick dark (`#333`) or light text from the fill's luminance (zrender `Path.getInsideTextFill`), so the heatmap's diverging colors are opaque blends (`mix`) rather than alpha, and its labels stay readable in both themes; (3) ECharts draws on several stacked canvases. Tooltips are HTML, so every non-numeric value in them goes through `format.encodeHTML`. The CSP already allows inline styles (D38), and the smoke tests check for violations.
- **Colors:** the Okabe-Ito series tokens and the blue-green / orange-red positive and negative tokens (D39), resolved to sRGB like the Charts tab (D40). Past cycles use the series colors at reduced opacity and the current cycle uses the foreground color, thicker, with a "Today · day N" line. In the YoY view older years fade toward the background. Heatmap colors saturate at ±40% (`HEATMAP_CLIP`), so a few early +200% months don't wash every other cell out to neutral; the cells show the exact value. Correlation cells use blue and orange (correlation is not a gain or a loss).
- **"View data" for derived results** links to `/data?table=analytics&fn=<registry name>&coin=..&<params>` (for example `fn=cycles_paths&mode=bottom`). Stage 3.4's Data tab must accept `table=analytics` and show that result (through the matching API route) as a table plus a CSV export. These results are computed, not stored rows, so they can't use the table allowlist.
- **View settings live in the URL** (`anchor`, `y`, `view` on Cycles; `horizon`, `stat`, `range`, `window` on Stats; defaults left out, `replace` history), like the coin, so a link reproduces the view. Range (All/4Y/1Y) trims drawdown, volatility and correlation in the browser; the API still returns the full history (about 6,000 daily rows for BTC).
- **"Current week"** in the distribution is the latest complete Monday week (`period_returns`, labeled by its Monday), and the text says so. The 30-day horizon uses overlapping windows, and the text says that too.
- **Bundle:** ECharts sits in a lazy chunk shared by the two tabs (about 197 kB gzip; Rollup names it after `url-state`, which is cosmetic). The tab chunks themselves are 4 and 5 kB gzip, and the Overview's first load is unchanged.

## D42. Data and Settings tabs, the key test, watchlist eligibility

*2026-11-01, Stage 3.4.*

- **Data tab:** a catalog of the allowlisted tables (description, rows, freshness, from `/api/data/tables`) and of the computed analytics results, a table view and an analytics view. Deep links: `table`, `coin`, `from`, `to` (inclusive; on timestamp columns it becomes "before the next UTC day"), plus any parameter that names a column (for example `key=fng`), all turned into the API's bound `column:op:value` filters. The coin filter uses `coin`, or `coins` (contains) on headlines, and never the `coins` table's `symbol`, because tab links always carry the selected coin (D39). "All coins" sets `allcoins=1`. Sorting, paging (50/100/500) and the chart column live in the URL too. The chart preview plots one numeric column against the table's main date column over the newest 500 rows that match the filters. CSV export calls the existing streamed endpoint with the session token and saves a blob, since a plain link would carry no token. Cells are text only (headline titles included).
- **Analytics results** (`table=analytics&fn=...`, D41) go through the same API route as their chart (a fixed `fn` to route map in `queries.ts`), so there is no new backend surface. `resultView` turns any result into tables: a list of records is one table, an object gives a table per list of records (`matrix`, `summary`, `table`), `bins`/`counts` become a histogram table, and nested objects become dotted columns (`bottom.date`). Single values show beside the tables. Paging, sorting and CSV happen in the browser, and the CSV neutralizes formulas like the backend's export, leaving numbers as numbers.
- **Key storage:** `lib/keys.ts` keeps `{provider, key, model}` under `desk.llm.v1` in localStorage, validated on read: unknown provider, wrong prefix or bad length means no key. The `X-LLM-Key` header is added only by the calls that need it (the key test now, the agent in 5.1), never by the shared API client. Prefix checks catch a key pasted under the wrong provider (`sk-or-`, `sk-ant-`, `sk-`). Unit tests cover round-trip, corrupt values, storage that throws and the header.
- **`POST /api/agent/test-key`** (member): one minimal call with the header key, through `agents/keycheck.py` with plain httpx, redirects off. OpenRouter and Anthropic make a 1-output-token completion on the chosen model (default from `byo_defaults`). OpenAI lists models (`GET /v1/models`) because no OpenAI model is chosen until 5.1 and listing is free. The response carries only our own message, chosen by HTTP status, because OpenAI's 401 text echoes part of the key. The canary test now sends its key through this route, with a fake provider whose error body echoes the request headers, and checks that the key went out to the provider but appears in no response, log or table. `GET /api/agent/models` returns the providers with defaults and the new `byo_choices` from `config/models.yaml`. The default model is saved with the key in the browser. Members can type any model id their key allows (validated against `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$`).
- **Watchlist eligibility:** `GET /api/admin/watchlist/check/{symbol}` and the add route both require an active Coinbase `{SYMBOL}/USD` spot market and candles in a window that starts 366 days back (the live check is in DATA_SOURCES). A failure explains itself, and Coinbase's `base_name` prefills the name. Tests use a fake exchange by default (the `api` fixture), so no test reaches Coinbase.
- **`GET /api/admin/usage`:** this month's server-key spend (UTC month) from `llm_spend` against the Decision 9 cap, by job and by model, agent messages per user (written from 5.1), and the 10 latest job runs with errors cut to 500 characters. Friends' own-key use has no recorded cost.
- **Settings:** a theme switch (the theme hook now follows the `<html>` class, so the top bar toggle and Settings stay in step), the key wizard (provider cards with OpenRouter recommended; three linked steps per provider, checked against each provider's docs; paste with show/hide; test; save in this browser; a saved key is shown masked as `sk-or-v1-…cdef` with Test, Change and Forget), and admin sections for watchlist, Clerk invites (redirect to the app's origin), users and roles, and usage.
- **Bundles:** the Data and Settings pages are lazy chunks. The Data preview reuses the shared ECharts chunk.

## D43. On-chain & Macro tab: existing routes, browser-side correlation readout

*2026-11-01, Stage 4.1.*

- **No new API.** The tab reads `/api/onchain/{coin}` (the `onchain` registry function, D21), `/api/ohlcv/{coin}` (Coinbase closes for price lines), `/api/macro` (FRED with release lags, D32), `/api/macro/fng` and `/api/macro/dominance`. `onchain_macro` is now on in `config/settings.yaml`. On-chain covers BTC and ETH; for any other selected coin the panels show BTC and say so. The Data tab gains `table=analytics&fn=onchain`; raw series link to `table=series&key=cm:<COIN>:<metric>`, `fred:<id>`, `fng` and `dominance:<btc|eth>`.
- **Hidden panels (roadmap: hide what 0.3 found unavailable, and say so):** ETH hash rate (Coin Metrics' free series stops 2022-09-14 at the Merge) is replaced by a "not available" note. Dominance has no free history (D23), so its panel draws the daily snapshots since 2026-10-29 and says so. Realized price and NUPL are derived (D21), and the text says how.
- **Bands are conventions, stated as such.** MVRV: below 1 (market value under realized value) and above 3.5. Checked on our Coin Metrics data: BTC yearly MVRV maxima 2011 7.74, 2013 5.88, 2017 4.72, 2021 3.96, 2024 2.78; minima near bottoms 2011 0.39, 2015 0.56, 2018 0.69, 2020 0.88, 2022 0.75. ETH peaks never reached 3.5 after 2017. NUPL zones (capitulation < 0, hope/fear, optimism/anxiety, belief/denial, euphoria/greed > 0.75) are the common Bitcoin-cycle convention. Fear & Greed bands are alternative.me's own classes (D32 findings). The MVRV readout gives the latest value's percentile within the coin's own history up to that day (trailing).
- **Correlation readout, computed in the browser** (`lib/onchain-data.ts`, like the indicators in D40): Pearson r between BTC's log returns and each FRED series' change (log change for the dollar index and M2, plain difference for the two rates) per UTC Monday week (monthly for M2, matched by calendar month to the M2 date on the 1st), over the latest 52 and 208 weeks (36 and 120 months for M2). BTC's latest period may be in progress, so it is dropped; changes are taken between consecutive periods both series have. A flat series (fed funds between moves) gives "—" instead of a fake number. It is a trailing readout for display, not an analytics function, so it is outside the look-ahead test; the agent's `get_macro` tool (4.2) can add a registry version if needed.
- **Charts:** one ECharts option builder (`lib/onchain-options.ts`) with an optional right-hand log axis for the "Overlay on BTC" price line, shaded bands (`MarkArea`, now registered; an edge left out runs to the axis edge) and dashed reference lines. Log axes are fitted to the data (`dataMin`/`dataMax`): otherwise BTC hash rate, which spans 11 powers of ten since 2010, ran to 1e10 EH/s. Values below 0.01 show in scientific notation and prices below $1 with 4 significant digits. BTC hash rate is shown in EH/s (Coin Metrics stores TH/s). Overlays (`overlay=DGS10,M2SL`), the range (`range`) and the M2 view (`m2=level`, YoY by default) live in the URL.
- **Size:** the BTC on-chain response is about 1.6 MB of JSON before gzip (5,950 days × 9 fields) and takes about 1 s on the full local data; acceptable next to the 0.7 MB OHLCV already loaded by Charts. Trimming precision or using `start` is a later option. The tab chunk is 8 kB gzip and reuses the shared ECharts chunk.

## D44. desk-mcp: tools call the API's read functions, compact JSON, groups

*2026-11-01, Stage 4.2.*

- **Defined once:** each tool in `mcp_server/tools.py` calls the same function as its API route (`desk.api.routes.*`, plain Python functions taking a session), so as-of rules, FRED release lags, provenance, the analytics registry and the cache are shared, not re-implemented. Route `HTTPException`s become the tool's error message ("unknown coin 'X'", "cycles_day_n is not available for SOL"). A separate service layer was not worth it for 19 thin wrappers; if the routes ever grow request-only logic, it moves into such a layer then.
- **`/api/coins` now takes `as_of`** (D37 said every response does; this one did not), so every tool, `list_coins` included, takes `as_of`. OpenAPI and the TS client regenerated.
- **Compact output:** `{"as_of", "sources", "data"}` as compact JSON text (`structured_output=False`, so no duplicate structured copy); floats to 6 significant digits; long series as `columns` + `rows` with `total_rows`, cut to the newest `limit` rows (max 500); summaries instead of full histories where an LLM needs the gist (regime: the last 10 label changes; YoY: per year the multiple at today's day of year, year end, max and min; correlations: latest plus 12 month-ends; distribution: quantiles and the latest percentile, histogram on request; macro: latest, 3 months and 1 year ago, 1-year change in points for rates and as a fraction otherwise). Real-data answers are 150 B to 4 KB, 0.04 to 0.9 s each.
- **Descriptions are written for an LLM:** what it returns, units, an example, and caveats (close-only early BTC, unconfirmed last pivot, headlines untrusted). All tools carry `readOnlyHint`. `get_external_views` is a stub until Stage 6.
- **`--groups`** (`market`, `cycles`, `stats`, `context`, `views`; comma-separated, unknown names exit with an error) registers only those tools; a call to another group's tool is "Unknown tool". The desk's analysts (5.3) get their own subsets this way.
- **Database:** the server reads `DATABASE_URL` like every other entry point (env, then the repo's `.env`), so the Claude desktop config needs no secrets. From Rob's PC that is Neon's pooled URL; heavy analytics may write `analytics_cache` rows there, as the API does.
- **Tests** (`tests/test_mcp_server.py`): tool lists per group, every schema has an optional `as_of` and a "Returns" description, every tool on the seeded database with `as_of` returns nothing dated later, the M2 release lag, errors, and stdio round trips with the SDK's `stdio_client` + `ClientSession` against a subprocess (`python -m desk.mcp_server.server --groups ...`, `DATABASE_URL` set to the test database).

## D45. Agent backend: in-process desk-mcp, our own graph, the server-key cap

*2026-11-03, Stage 5.1.*

- **Tools in-process:** the agent loads desk-mcp's tools with `langchain_mcp_adapters.tools.load_mcp_tools` over the MCP SDK's in-memory transport (`mcp.shared.memory.create_connected_server_and_client_session`) on the same FastMCP server Claude desktop runs, so tools are still defined once and still go through MCP. A stdio subprocess per chat (1.9 s to initialize from Rob's PC, plus memory on a 512 MiB instance) wasn't worth it. FastMCP runs sync tools on the event loop, so `build_server(threaded=True)` wraps each tool in `anyio.to_thread.run_sync` (same signature and schema); stdio is unchanged. A context variable (`tools.session_override`) hands the tools the API's session factory, so they share its pool (and the test database).
- **Our own LangGraph graph** (`agent` ⇄ `tools`, `stream_mode="custom"` events), not `create_react_agent` (deprecated in langgraph 1.2) and not `langchain.agents.create_agent` (another package). It owns the tool-call limit and the snapshot writes. After `agent.max_tool_calls` (10) calls the model gets one last turn with `tool_choice` none (Anthropic `{"type": "none"}`, OpenAI-style `"none"`: Anthropic needs the tools defined while the history holds tool calls) and a note to answer from what it has; parallel calls past the limit get a "not run" tool result. Tools run one after another, so events arrive in order.
- **Routes** (member and up): `POST /api/agent/chat` streams SSE with FastAPI 0.162's own `EventSourceResponse` (works on POST; keepalive comments; gzip already skips `text/event-stream`). Validation, the budget, the hourly limit and saving the question happen in a dependency, so refusals are plain HTTP errors (400 no key or bad model, 402 server budget used up, 404, 429 with `Retry-After`) before the stream starts. Events: `conversation`, `token`, `tool_start`, `tool_end` (snapshot id, 300-character preview), `done` (tokens, server cost, tool calls, `limited`, `truncated`) or `error` (`timeout`, `provider`, `internal`, always our own text). Payload models are added to the OpenAPI components with an `x-sse-events` map on the route, so the client has their types. Plus `GET/DELETE /api/agent/conversations[/{id}]` (owner only, 404 otherwise) and `GET /api/agent/snapshots/{id}` (owner, or any admin). Conversation detail attaches each snapshot to the first answer saved after it.
- **Run loop:** the graph runs in its own task feeding a queue, inside `asyncio.timeout(90)`, so a slow client never holds the deadline. The answer saved is all streamed text, also after a timeout or error. Memory is the last 20 user and assistant messages; tool results aren't replayed (they're in the snapshots). The MCP session's task group wraps failures in exception groups, so errors are unwrapped before choosing a message.
- **Models** (`agents/llm.py`): OpenRouter through `ChatOpenAI` with OpenRouter's base URL, `stream_usage=True` and `use_responses_api=False`; Anthropic through `ChatAnthropic`; OpenAI through `ChatOpenAI`. Keys are passed as `SecretStr` and an empty key is refused, so a request never falls back to a key in the server's environment. One client retry, 60 s per call. Max output tokens 4,000: the first live run hit 2,000 because Haiku 5.5's adaptive thinking counts toward it, and `done.truncated` now reports a cut-off. OpenAI default `gpt-6-luna` (cheapest current model with tool calling) at `reasoning_effort` none, with `gpt-5.6-luna` and `gpt-5-mini` as choices.
- **Cost** (`agents/cost.py`): prices from `models.yaml` (Haiku 5.5's long-prompt rate above 100K input tokens included); `check_budget` before a server-key run; `record` writes one `llm_spend` row per model call from `usage_metadata`. At 80% of the $8 cap (`budget.degrade_at_fraction`) chat moves to `chat_degraded` at effort low with 1,500 output tokens; at the cap, 402. A run that starts under the cap may finish slightly over it. User-key answers store tokens with a null cost.
- **Hourly limit:** 30 questions per user per rolling hour, counted from `messages` in the database, so it holds across both Cloud Run instances (unlike the per-minute limiter, D37).
- **LangSmith:** only server-key runs are traced; every run sits in an explicit `tracing_context(enabled=...)`, so `LANGSMITH_TRACING` in the environment can't trace a friend's run. `ScrubbingClient` scrubs every field of every run it posts (secret values become `[redacted]`, key-like fields are dropped); the canary test checks it with a model that leaks the key into its invocation params, and fails if the scrub is switched off. Rob's key is an organization-scoped service key (`lsv2_sk_`), which gets 403 on runs and projects without the workspace id, so `LANGSMITH_WORKSPACE_ID` is now a setting (a repo variable for Cloud Run).
- **Deploy:** the service mounts `anthropic-api-key` and `langsmith-api-key` from Secret Manager only once they exist (the deployer needs `roles/secretmanager.viewer` on them to check), so deploys stay green until Rob creates them. That makes 4 of the 6 free active versions.
- **Tests:** the `api` fixture now gives every test a scripted fake model, so no test can reach a provider or the server key in `.env`; `real_llm` restores the factory for the canary test, which drives a real `ChatOpenAI` against a mocked OpenRouter stream.

## D46. Agent tab: streamed answers, tool cards, snapshots in the Data tab

*2026-11-03, Stage 5.2.*

- **Stream client** (`lib/agent.ts`): `openapi-fetch` with `parseAs: "stream"` (so the Clerk token middleware still applies), the body read through `TextDecoderStream` and a small SSE parser that keeps unfinished events between chunks, skips keepalive comments and drops unknown or malformed events. A refusal (400, 402, 404, 429) shows the API's own `detail`. The key goes only into this request's `X-LLM-Key` header; the body carries `provider` and `model` (none for the admin's server key). Stop aborts the fetch.
- **Chat view:** the conversation being streamed lives in local state; any other comes from `GET /api/agent/conversations/{id}`, whose snapshots are shown as tool cards with "View data" (no arguments or preview are stored for history, so those cards show the tool and link only). The open conversation is `?c=<id>` in the URL. Tool cards say the tool in plain words plus its arguments ("BTC · mode halving · latest data") and a short preview; after each answer a "Data used" line lists the tools with the as-of date read from the preview, each linking to its snapshot. Notes for `limited` and `truncated`, and model, tokens and (server key) cost under each answer.
- **Markdown:** `react-markdown` 10.1 + `remark-gfm` 4.0 (tables), with `skipHtml` and no `rehype-raw`, so raw HTML in model output is dropped; links only if http(s), opened with `noopener noreferrer nofollow`; images never load (alt text only), which also keeps the CSP unchanged. Tested with script, iframe, `onerror` and `javascript:` inputs. The tab is a lazy chunk (53 kB gzip, mostly the Markdown parser).
- **Who can chat:** with a saved key, anyone, on the model picker's choice (the key's provider only: saved model, provider default, then `byo_choices`); the admin without a key, on the capped server key (a badge says so); a member without a key gets a card linking to Settings. Starter questions from the roadmap.
- **Data tab:** `?snapshot=<id>` opens `GET /api/agent/snapshots/{id}`: tool, arguments, as-of date, sources, then the result as tables (desk-mcp's compact `columns`/`rows` tables expanded at any depth, a bare record as one row, single values beside), a column chart when there is a `date` or `time` column, CSV, and a link back to the conversation. A 404 explains that the snapshot isn't the user's or was deleted with its conversation.
- **Flag:** `features.agent` is on. The key wizard's "Test key" was already live since Stage 3.4 (D42); the roadmap's step 3 needed no change.

## D47. The multi-agent desk and "Ask the desk"

*2026-11-03, Stage 5.3.*

- **Graph** (`agents/desk_graph.py`) is the Section 3.3 diagram, using LangGraph fan-out and fan-in edges:
  - `START` → `technical` and `context` in parallel;
  - `["technical", "context"]` → `bull_open` and `bear_open` in parallel;
  - `["bull_open", "bear_open"]` → `bull_rebut` and `bear_rebut`;
  - then `head` → `validator`, which routes back to `head` once if the signal is invalid.
  - Parallel branches write only their own keys (a dict-merge reducer), and progress streams as `stream_mode="custom"` events.
- **Analyst tools:** each analyst opens its own in-memory desk-mcp session with `build_server(groups)`, the same code path as `desk-mcp --groups`, so a call to another group's tool gets "Unknown tool". Rob chose a wider group for the technical analyst than Section 3.3's "market tools":
  - technical: `market,cycles,stats`;
  - context: `context,views`.
- **Analyst flow:**
  - A tool loop of at most 6 calls, ending when the model replies without a tool call (the prompt asks for "done").
  - Then one fresh structured call, with the tool results passed as a data block, writes the report.
  - Why a fresh call: it is a single structured call that works the same on every provider, and it never has tool calls in its history (Anthropic requires the tools to be bound while the history holds tool calls).
  - Finding ids (T1.., C1..) are assigned by the code, not the model. Debaters cite them; citations to ids no report contains are kept and flagged (`unknown_cites`), never hidden.
- **Structured output:** `with_structured_output(schema, method="function_calling", include_raw=True)`, checked in the installed source.
  - `ChatAnthropic` 1.7.7 binds a forced tool. Haiku 5.5 accepts forced `tool_choice`; Fable 5.1, Opus 5.5 and Sonnet 5.5 don't, and the library falls back for them.
  - `ChatOpenAI` 1.7.3 defaults to `json_schema` but accepts `function_calling`, which is what OpenRouter models support most widely.
  - `include_raw` keeps the usage for cost, and a parsing error becomes a validator error instead of a crash.
- **Schemas:** the model schemas are loose; `validate()` does the strict checks:
  - confidence within `signals.confidence_min`/`max`;
  - for `lean_long`, all four levels present and `invalidation < entry_low ≤ entry_high < target`;
  - every level positive and within ±50% of the reference close.
  - The reference close is the last daily close up to `as_of`, read from `candles_daily` when the run is prepared, not parsed from tool output.
  - A signal invalid twice is reported as `invalid` with its errors. No signal is ever made up (Stage 7.1 decides its own fallback).
- **Limits** (`desk:` in `config/settings.yaml`):
  - 180 s for a run, 60 s per analyst, 30 s per debate turn and head attempt;
  - an analyst that fails or times out is marked unavailable, and the run goes on; the head is told and the UI says so;
  - both analysts failing, or any later node failing, ends the run with an `error` event (our own text) after saving the partial state;
  - 5 runs per user per rolling hour (user messages starting "Ask the desk:"), on top of the chat's 30 questions, which count the run's question too.
- **Persistence:**
  - a run is a conversation titled "Ask the desk: SOL" with one question and one answer, a short Markdown summary of the signal;
  - every analyst tool call is an `agent_snapshots` row, as in chat;
  - the full state (`DeskRunState`: reports, debate, signal, validation, per-node usage) is one `desk_run` snapshot, which the Agent tab re-renders when a run is reopened.
  - `DeskRunState` is published in the OpenAPI components, and the desk's SSE payloads are mapped under `x-sse-events` like chat's.
- **API and CLI:**
  - `POST /api/agent/desk` (SSE; refusals 400/402/404/422/429 before the stream);
  - `GET /api/agent/desk/estimate` (tokens per node from `desk.estimate_tokens`; USD only when the model has a price in `models.yaml`, so most OpenRouter ids get "depends on your provider");
  - `desk agent desk-run --coin SOL [--as-of]` runs it on the server key as the first admin and prints the projected cost and the per-node costs.
  - `as_of`, when given, is forced into every tool call.
- **Cost:** server-key calls are recorded with source `desk`. The run counts against the $8 cap and moves to the degraded model settings at 80%, like chat.
- **Live run, 2026-11-03** (SOL, server key, Haiku 5.5, Neon): 16.7 s, 11 model calls, 9 tool calls, 48,982 input and 4,567 output tokens, **$0.0072**. Every debate citation resolved, and the head returned a valid `flat` at 0.55 on the first try. Per node:

| Node | Calls | Tools | In | Out | USD |
|---|---|---|---|---|---|
| technical | 3 | 4 | 17,675 | 1,118 | 0.00233 |
| context | 3 | 5 | 13,616 | 1,317 | 0.00202 |
| bull_open | 1 | 0 | 2,730 | 394 | 0.00047 |
| bear_open | 1 | 0 | 2,774 | 429 | 0.00049 |
| bull_rebut | 1 | 0 | 3,527 | 457 | 0.00058 |
| bear_rebut | 1 | 0 | 3,571 | 436 | 0.00057 |
| head | 1 | 0 | 5,089 | 416 | 0.00072 |

- **Agent tab:** a Chat / Ask the desk switch.
  - The desk mode shows a coin picker, the estimate and Run; Stop aborts the run.
  - Cards appear in graph order: the analysts with their tool cards, the four debate turns with citation chips (unknown ones struck through), and the signal with the validator's verdict, plus a "retried" badge when the head ran twice.
  - All model text is plain text. The shared SSE reader moved to `readEvents`/`parseEvents` in `lib/agent.ts`, and the tool card to `components/agent/ToolCard.tsx`.

## D48. MCO ingest pipeline

*2026-11-03, Stage 6.1.*

- **Discovery** (`mco/discover.py`): RSS first, then the YouTube Data API uploads playlist (`channels.list` for the uploads id, then `playlistItems.list`). One `videos.list` call adds duration and `snippet.liveBroadcastContent` for unseen videos. Each call costs 1 quota unit (checked in the quota docs), so a run uses about 3 of the 10,000 daily units.
  - A live check on 2026-11-03 found the uploads full of Shorts (42 to 73 s). YouTube Shorts can run up to 3 minutes, so videos under `mco.min_duration_seconds: 180` are stored as `skip`.
  - Keywords match whole words (`sol` matches "SOL", not "solid").
  - Live and upcoming broadcasts are not stored, so they come back as uploads.
  - Unseen videos older than `mco.backfill_days: 3` are stored as `skip`, so the first run does not work through the backlog.
  - At most 4 videos a day, newest first. Videos already processed that UTC day count toward the cap. A failed video is retried on later runs, up to 3 attempts.
  - Decision 9 step 2: from 80% of the cap, only 2 a day, and only videos that name BTC, ETH or SOL.
- **Summaries** (`mco/summarize.py`, prompts `mco_extract_v1`, `mco_repair_v1`, `mco_fallback_v1`):
  - Chain: `gemini-3.5-flash-lite`, then `gemini-3.8-flash`. Invalid JSON gets one text-only repair call per model; after that, a title-and-description fallback marked low detail (all coins `low`, no pivot labels).
  - google-genai 2.33 retries only when `HttpOptions.retry_options` is set (the default is a single attempt), and `HttpOptions.timeout` is in milliseconds (installed source). We use 3 attempts on 408/429/5xx with backoff from 5 s, and a 300 s timeout.
  - The schema adds `pivot_kind` (high or low) to each pivot label so snapping knows which pivot type to look for. Coins are mapped to our symbols through the `coins` aliases, and duplicates are dropped. Summaries longer than 120 words are trimmed, not rejected.
  - D25 check: a bullish bias with every target below the last close, or with the invalidation above it (and the bearish mirror image), sets that coin to `low` and adds a note to the payload's `checks`.
- **Cost:** each Gemini call is one `llm_spend` row (source `mco`) with its real tokens at **$0** while `models.yaml` `gemini_tier` is `free` (Rob's choice). Setting it to `paid` applies the paid prices that are already in `prices`. The earlier "≈$0.30/month if paid" estimate was about 10× too low: 84K input plus 1.1K output tokens is about $0.028 per video, so about $3.40/month at 4 a day on Flash-Lite.
- **Snapping** (`mco/snap.py`): pivots come from the same zigzag and timeframe defaults as `/api/pivots`, as of the day before publication (the last closed bar), with the open week included on 1W.
  - A label matches the pivot of the same kind with the lowest bars/tol + |pct|/tol inside ±5 bars and ±3% (1D) or ±2 bars and ±6% (1W) (`mco.snap`).
  - 4h and 1h labels snap on 1D; monthly ones on 1W.
  - Labels on coins we don't track stay only in the extract payload.
  - Every row is `pending`. An unmatched row keeps a `match_note`.
- **Privacy (Decision 6):**
  - The job summary (public Actions log, ops alerts) holds ids, counts, model ids and error codes only. Unexpected errors are logged as type and code location, never as a message.
  - `mco_videos.error` holds a short code.
  - `desk mco show` prints extracts and refuses to run in CI.
  - Members' `/api/mco/videos` never returns the raw `pivot_labels`, only `approved`/`edited` label rows.
  - `/api/admin/mco/review` is admin-only, and every MCO route answers 404 when MCO is off.
  - Tests cover a canary in the title and summary, writes under the repo, and the role matrix.
- **Alerts:** `new_mco_summary` per video (title, per-coin bias, link, "AI-extracted" note) to Telegram and Discord. `mco_review_pending` (counts only) goes to Telegram.

## D49. MCO wave counts dropped; extract v2 with scenarios

*2026-11-03, after Stage 6.1. Rob's decision; it updates Decision 7 and removes Stage 6.3.*

- **Evidence:**
  - Rob checked the v1 extract of a SOL video against the video. Bias, wave position, targets, levels, the alternative scenario and the missing invalidation were all right. The wave labels mixed past swings with projected ones and with both of his scenarios, which he draws in different colours that change from video to video.
  - The same video, 3 runs on `gemini-3.5-flash-lite`, gave three entirely different label sets: different labels, dates and prices, with some impossible (dated after the video) and some mistaken for a resistance level. Levels, targets and scenarios were the same in every run.
  - `media_resolution` LOW, MEDIUM and HIGH all used exactly 33,636 input tokens on that video, so the setting appears to have no effect for YouTube URLs on Flash-Lite.
  - `gemini-3.8-flash` failed with 503 "high demand" on all 3 runs (4 attempts each, about 15 minutes), as in Stage 0.3.
- **Decision:** Rob does not want to place labels by hand, so chart wave counts are dropped.
  - The app shows MCO's levels, targets, invalidation and triggers per scenario.
  - `mco_wave_labels` and `mco/snap.py` stay in the code, unused, in case a stronger model makes labels reliable later.
  - The 8 labels stored by v1 were set to `rejected`, not deleted.
  - `GET /api/admin/mco/review` and the job's `mco_review_pending` alert are removed. The event name stays in the alert routing for now.
- **Extract v2** (`prompts/mco_extract_v2.md`, `mco_fallback_v2.md`; `mco_repair_v1.md` is unchanged):
  - Per coin: bias (the primary's), wave position in words, timeframe, shared `key_levels`, and `scenarios`. Each scenario has `name` (primary or alternative), `color` (only when clearly visible), `bias`, `description`, `levels`, `targets`, `invalidation` and `trigger`.
  - The D25 check runs per scenario.
  - The prompt says that "what would change his view" is the alternative scenario with that condition as its trigger, and asks for every level he names. The first v2 draft put the alternative into the primary's trigger and dropped levels; the tightened prompt gave the same primary, alternative and shared levels on 3 of 3 runs. Colours were inconsistent ("orange" once, "yellow" twice, the alternative's never given), so they are shown as a hint only.
  - **Earlier views as context:** the latest extract per coin from the previous 14 days (at most 10 extracts, 8 coins) goes into the prompt as compact text inside `<earlier_views>`, marked untrusted. This is for "as mentioned yesterday" references.
  - v1 payloads are read as v2 (`schemas.load_payload`): the primary takes v1's targets and invalidation, the alternative's bias is unknown (neutral), and labels are dropped.
- **API:** `/api/mco/videos[/{id}]` return scenarios and never any label, from rows or from stored payloads.
- Today's 3 videos were re-extracted with v2 (Neon, alerts off).

## D50. MCO tab, chart overlays and outside views

*2026-11-03, Stage 6.2.*

- **Outside views** (`api/routes/views.py`, `list_views`):
  - MCO's views are read live from `mco_extracts` (newest extract per video, v1 read as v2), not copied into `external_views`, so they never go stale when a video is re-extracted. `external_views` holds only Rob's manual views (`extract_id` stays null).
  - `as_of`: MCO views count from the video's publication time, manual ones from their creation, both up to the end of that UTC day.
  - MCO views are left out when MCO is switched off. Manual views stay.
  - The same function backs `GET /api/views` (member), desk-mcp's `get_external_views` (the `views` group the desk's context analyst already has; the tool says the text is untrusted and AI-extracted) and the Overview's `mco_bias`.
  - `POST /api/admin/views` and `DELETE /api/admin/views/{id}` (admin) take source, coin, bias, levels (price and label, at most 20), invalidation and an http(s) link.
- **MCO tab** (`features.mco_tab` on):
  - The AI-extracted notice with the channel link.
  - A coin filter in the URL (`mco_coin`).
  - A bias timeline: one marker per video, coloured by bias, on the daily close of the chosen coin (log axis).
  - Video cards: thumbnail, title linking to YouTube, date, per-coin bias chips, a low-detail badge, the summary, failed D25 checks, and per coin the primary and alternative scenarios with targets, invalidation, trigger and levels, plus shared levels.
  - Everything is plain text; links go through `safeHttpUrl`.
  - **Rob's choice:** his own chart colours are not shown, because the model reads them unreliably (D49).
  - Thumbnails come from `i.ytimg.com`, which is added to the CSP `img-src` only, and load without a referrer.
  - The timeline's "View data" link (`mco_extracts`) is shown to the admin only, since MCO tables are admin-only in the Data tab (Decision 6).
- **Charts tab:**
  - The "MCO waves" placeholder is gone.
  - "Primary scenario" and "Alternative scenario" toggles draw the newest video's lines for the coin: levels dashed, targets solid, invalidation dotted. The primary is in `series-1` and the alternative in `series-4`; the shared levels (muted) go with the primary.
  - The chart title says the lines are AI-extracted from the video of that date.
  - The toggles appear only when the MCO feature is on. They are saved with the other chart settings and are on by default.
- **Overview:** each coin card shows MCO's latest bias with a link to the MCO tab filtered on that coin, or nothing when there is none.
- **Settings:** an admin "Outside views" panel adds and deletes manual views. Levels are one per line, price then label.

## D51. Weekly signals job, brief writer and level watch

*2026-11-04, Stage 7.1.*

- **Week and as_of:** the signal week is the Monday of the run's UTC week. Every input is as of the Sunday before (the desk's tools get it forced, the baselines truncate at it), and a coin without that Sunday's candle gets no signals that week (reported as stale).
- **Signal version:** `config/settings.yaml` says `v1`; the `signals.version` column is an integer, so `v1` is stored as 1 (`chain.version_number`).
- **Confidence means "the stance is right"**, 0.5 to 0.95 (the table's check constraint). The chance of a higher close is `confidence` for `lean_long` and `1 - confidence` for `flat`. So the trend rule's "flat with 0.4" in Section 3.5 is stored as flat at 0.6 (a 0.4 chance of a higher close).
- **Desk:** run on the server key with the per-user hourly limits off (`prepare(rate_limited=False)`), one coin at a time, as Ask the desk conversations of the first admin. Only a valid signal becomes a `desk` row; `transcript_ref` is `snapshot:<id>` (the `desk_run` snapshot). An error, a refusal (for example the cap) or a signal invalid twice writes no desk row, and the run fails so the admins hear about it; the other sources are still written. At the cap itself there is no desk row, since the $8 cap is hard; "never skipped" (Decision 9) means degradation never drops signals, only the watchlist.
- **MCO as a source:** the newest view published by the end of the Sunday and at most 14 days old. `lean_long` if bullish, else `flat`. Confidence comes from the extraction's label (high 0.7, medium 0.6, low 0.55), or 0.6 without one. His primary invalidation and nearest target above the close become the row's levels only when they bracket the close. `transcript_ref` is `mco:<video id>`.
- **Chain:** SHA-256 over the row's canonical JSON (version, week, coin, source, stance, confidence, levels, rationale, transcript_ref) plus the previous row's hash. One global chain, written under a transaction-scoped advisory lock. Migration 0003 adds a trigger that refuses UPDATE and DELETE. TRUNCATE isn't blocked, because the tests reset with it. `desk signals verify` runs after each weekly job. Re-runs skip (coin, source) pairs the week already has.
- **Resolving (`signals/resolve.py`):** one `signal_outcomes` row per signal once all seven daily candles of its week have closed (new column `reference_close`, the Sunday close before the week).
  - "up" means the week's last close is above the reference;
  - `direction_hit`: lean_long and up, or flat and not up;
  - `brier`: (P(up) − up)²;
  - `first_hit` (only when a signal has both an invalidation and a target): from daily lows and highs, and a day touching both counts as invalidation;
  - `paper_pnl`: lean_long bought at the reference close and sold at the level hit first, else at the week's close, with 0.2% per side (flat weeks are 0). The entry zone isn't used for fills.
  - Stage 7.2 aggregates these rows.
- **Brief writer (`agents/brief_writer.py`, `prompts/brief_v1.md`):** one call, no tools, server key only. Sonnet 5.5, or Haiku 5.5 from 80% of the cap (Decision 9, step 3). Structured output uses `method="json_schema"`, because Sonnet 5.5 refuses forced tool choice. It gets per coin the compact desk state (reports, debate, signal, validation), every source's signal and the key levels, all as untrusted data. It returns a 5-line summary and per coin setup, bull case, bear case, what would change the view and levels to watch. That is rendered to Markdown in `briefs.content`, with the structure in the new `briefs.payload`. Spend source `brief`. Max output tokens 16,000, because adaptive thinking counts toward it.
- **Alerts:** `brief_ready` carries the 5 summary lines and each coin's desk signal, linking to the app (`app.url`). `level_cross` sends one message per level-watch run.
- **Level watch (`jobs/levelwatch.py`):** for yesterday's close D, a level L is crossed when close(D−1) < L ≤ close(D), or the reverse. The levels are this week's `desk` and `mco` rows (entry low and high, invalidation, target) plus the key levels as of D−1, so the crossing close doesn't move them. It is de-duplicated by a successful `levelwatch` run in `job_runs` for the same day. It runs at 01:00 UTC, after the daily job.
- **Privacy (Decision 6):** the Actions logs are public, so the weekly and level-watch summaries hide MCO-derived rows and the brief text, and errors print only the exception type (the full message goes to `job_runs`). `--show-private` shows them locally.
- **Dry run, 2026-11-04 (week of 2026-11-02, data to 2026-11-01, Neon, server key):** 90 s wall time and **$0.106** (target at most $0.50 a week):
  - three desk runs took 16 to 20 s each and about $0.02 in all; every signal was valid: BTC, ETH and SOL flat at 0.55, ETH with invalidation 2,170.03 and target 2,389.59, SOL with invalidation 92.14;
  - the trend rule leaned long on all three, and MCO had a view on BTC only (lean long 0.70; ETH and SOL had none within 14 days);
  - the brief on Sonnet 5.5 took 15,029 input and 5,626 output tokens ($0.086). A second brief from the same snapshots took 4,784 output tokens ($0.078), used only numbers from the data, and said where MCO had no view.
  - About $0.45 a month, in line with Section 7.


## D52. Scorecard, Signals API and Signals tab

*Stage 7.2, 2026-11-04.*

- **Scoring (`signals/score.py`)** aggregates the `signal_outcomes` rows that `signals/resolve.py` writes (D51); nothing is recomputed from candles. Per source and per (source, coin):
  - direction hit rate;
  - mean Brier score on P(up) (the coin flip always scores 0.25);
  - target-before-invalidation rate over the signals that have both levels, where a day touching both counts as invalidation;
  - paper P&L on `lean_long` weeks, with 0.2% per side already in `paper_pnl` and flat weeks at 0. Per (source, coin) the weeks are compounded; per source each week is the equal-weight mean over that source's coins, then compounded;
  - an "early days" flag under 12 distinct weeks.
  Cumulative values per week drive the charts. Hand-computed cases are in `tests/test_score.py`.
- **API (`/api/signals`, members):** `weeks`, `week` (default the latest, with the brief's structured payload), `history` (coin and source filters), `scorecard` and `{id}/debate`. The debate route serves the saved `desk_run` state directly, because that snapshot belongs to the admin user and the Data tab's `own` rule would hide it from members. All take a `version` that defaults to `signals.version`.
- **MCO (Decision 6):**
  - While MCO is on, members see MCO's signal rows on screen.
  - When MCO is off, the API leaves out `mco` rows and their scores. A week that had an MCO row also keeps back its brief and desk debates, since both were written with MCO's views as input.
  - Data tab (this fixes a gap from Stage 2.1's allowlist that 7.1 made real): `signals`, `signal_outcomes` and `briefs` now carry an `mco_rows` filter. It drops MCO signals, their outcomes, and the briefs of weeks with MCO rows from members' CSV exports, and from everything for everyone when MCO is off.
- **Overview:** each coin card's `signal` is the desk's latest signal of the current version (week W counts from W − 1 for `as_of`).
- **UI:** the Signals tab shows:
  - the brief (from the payload, or the sanitized Markdown when there is none);
  - a coin × source grid with levels and outcomes;
  - desk debates fetched when opened, reusing the Agent tab's `DeskRunView` without the snapshot link;
  - the scorecard with early-days badges;
  - a cumulative chart (paper P&L, hit rate or Brier);
  - history with source and coin filters;
  - the not-advice notice, and "View data" links to `briefs`, `signals` and `signal_outcomes`.
  `features.signals` is now on. Until the first weekly run (Monday 2026-11-09, 00:15 UTC) the tab says there are no signals yet.

## D53. Ops, monitoring and cost

*Stage 8.1, 2026-11-04.*

- **Health page:** `/health` keeps the public backend status, and for admins adds the ops view from `GET /api/admin/health` (`ops/health.py`):
  - **Jobs:** the last run of each scheduled job with its status, duration and error, the last success, runs and failures in the last 7 days, and an **overdue** flag when no success came within `ops.jobs.<job>` hours (daily, levelwatch and mco 26 h; weekly and backup 170 h).
  - **Freshness:** the newest date per source (prices per coin, on-chain per coin, Fear & Greed, dominance, FRED, headlines, MCO's newest summarized video, the newest desk signal week and brief).
  - **Spend:** month to date against the $8 cap, the month-end pace, and the three Decision 9 degradations shown as on or off (they share one flag at 80% of the cap).
  - **Errors:** counts (see the next point).
  - **Usage:** `pg_database_size` against Neon Free's 1 GB and the largest tables. Cloud Run and Neon compute have no API we can call without new credentials (Neon Free can't export metrics), so they are console links, with the free-tier numbers alongside.
  Settings → Usage links to the page. MCO appears there only as dates and counts.
- **Error tracking: structured logs plus counts, no Sentry.**
  - Sentry's free Developer plan (5k errors, 1 user, 30-day lookback, sentry.io/pricing, 2026-11-04) would be $0, but it would send exception data to a third party, and messages here can quote prompts, MCO text or a fragment of a provider's key. It would also need one more secret and a client in the API.
  - Instead, on Cloud Run (`K_SERVICE` set) the API logs JSON lines with `severity` and `message`. Cloud Run moves `severity` to the entry, and a traceback inside `message` stays one entry that Error Reporting picks up (docs.cloud.google.com/run/docs/logging). uvicorn's access log is turned down because Cloud Run writes its own request log.
  - The `ErrorCounter` middleware writes one `app_errors` row per unhandled exception: the route template (FastAPI 0.162 nests included routers, so the prefix is rebuilt from the request path), the exception type and 500, never a message.
  - Agent and desk streams that end in `error` add a row with their code (`agent.chat` / `agent.desk`, `provider`, `timeout`, `budget` or `internal`).
  - Rows older than 90 days are pruned by the weekly summary. Migration `0004`.
- **Weekly ops summary:** `desk ops summary`, from `ops.yml` on Monday at 07:00 UTC, after the weekly and MCO jobs. It sends a new admin-only event, `ops_summary`, to Telegram only. The summary lists problems, each job, how many sources are fresh, spend and pace, error counts and database size. It carries counts and dates only, so the workflow log is safe too. `desk ops health` prints the same text locally without sending.
- **Backups.** Neon Free keeps 6 hours of restore history, 1 manual snapshot and no scheduled backups (neon.com/docs/introduction/plans, 2026-11-04), so `desk ops backup` runs weekly in `ops.yml` before the summary:
  - `pg_dump --format=custom --data-only` of the 14 tables nothing can rebuild (`ops.backup.tables`: coins for the watchlist, users, conversations, messages, agent snapshots, the three MCO tables, external views, signals, outcomes, briefs, job runs, LLM spend), over the direct host.
  - Neon runs **Postgres 18.6** (`SHOW server_version`), and pg_dump must not be older, so the workflow installs `postgresql-client-18` from PGDG. `apt.postgresql.org.sh -y` skips its prompt (checked in its source).
  - `pg_restore --list` must show one TABLE DATA entry per table.
  - `gpg --symmetric --cipher-algo AES256`, with `BACKUP_PASSPHRASE` on stdin. The database password goes in `PGPASSWORD`, never argv (a test caught `URL.set(password=None)` meaning "unchanged" in SQLAlchemy).
  - Upload to the private bucket `crypto-desk-513023-backups` (us-central1, 5 GB-months free) through the JSON API with `ifGenerationMatch=0`. The deployer gets only `roles/storage.objectCreator` on that bucket, which "does not give permission to view, delete, or overwrite objects", so a leaked workflow token can't read or destroy old backups. It authenticates with Workload Identity (`token_format: access_token`).
  - Objects are deleted after 180 days (`config/gcs-backup-lifecycle.json`).
  - Never a CI artifact (Decision 6; a public repo's artifacts are downloadable). The plain dump is deleted in all cases.
  - `alembic_version` is left out. The schema revision goes in the file name (`desk-YYYY-MM-DD-r0004.dump.gpg`): restore into a database migrated to that revision, then upgrade.
  - **Round trip checked locally (2026-11-04):** two scratch databases migrated to 0004 and FK-linked rows in every table. The Postgres 18 client produced 14 TABLE DATA entries. gpg encrypt and decrypt matched byte for byte. `pg_restore --data-only --single-transaction --exit-on-error` into the fresh database succeeded, with pg_dump ordering the tables by their foreign keys and sequences restored (the next user id continued). Restore steps are in `docs/OPS.md`.
- **Load check (3 concurrent users, `tests/test_agent_load.py`):** three chats (the admin's server key and two members' keys) against one API process, as one Cloud Run instance would serve them. The model is a fake with a 0.6 s wait before each of its two turns; the desk-mcp tools are real, on the seeded test database. Measured on Rob's machine:
  - one chat took 1.39 s and three at once took 1.76 s, so they overlap: model waits are awaited, and the tools and database writes run in worker threads;
  - peak Python allocations during the three were 3.3 MiB, small against the instance's 512 MiB;
  - each chat ended with `done` and its own snapshot.
  The test keeps a bound of 1.6× one chat.
- **A bug the load check found:** the hourly message limit counted, then inserted, with no lock, so three questions sent at once by a member with one question left all got through. `chat.check_rate` now locks the user's row (`SELECT … FOR UPDATE`) until the question is committed, which also covers the desk's per-run limit checked in the same transaction. The test now asserts `[200, 429, 429]`.
- **Real-model latency** (time to first token, provider rate limits) is outside this check. Friends use their own providers, and Cloud Run's metrics page (linked on the Health page) shows instance count and memory under real use.

## D54. Public readiness, README and resume notes

*Stage 8.2, 2026-11-04.*

- **`docs/PUBLIC_READINESS.md`** lists the blockers for opening beyond friends:
  1. MCO off (Decision 6);
  2. data licenses;
  3. terms, a privacy policy and a disclaimer;
  4. open sign-up with abuse limits;
  5. data retention;
  6. account deletion;
  7. cost alarms that can stop spend.
  It also has costs at 100 and 1,000 users, every source's terms, a design for encrypted server-side keys, and a paid-tier sketch.
- **Prices for the cost table, checked 2026-11-04:**
  - Cloud Run's request-based rates came from the Cloud Billing Catalog API, since the pricing page doesn't render for the fetch tool: "Services CPU (Request-based billing)" $0.000024/s, "Services Memory (Request-based billing)" $0.0000025/GiB-s, "Requests" $0.40 per million after 2 million;
  - Neon Launch: $0.106/CU-hour and $0.35/GB-month, no minimum;
  - Clerk Hobby: 50,000 MRUs, Pro $25 a month;
  - CoinGecko Basic: $35 a month with a commercial license.
- **The estimate rests on the measured week:** 433 requests and 1,281 billable instance-seconds (Cloud Monitoring), 4.4 kB per agent snapshot, and $0.0029 for a 2-tool answer. Assumptions: 800 requests and 30 agent questions per active user a month, with no overlap between users (an upper bound for Cloud Run). Result: about $15 a month at 100 users and $45 to $135 at 1,000, mostly Neon compute once the database stops idling.
- **Source terms found** (recorded in `DATA_SOURCES.md`):
  - Coin Metrics community data is CC BY-NC 4.0, so a commercial tier needs a license;
  - CoinGecko's Demo plan requires a linked attribution and has no commercial license;
  - FRED requires a specific notice, a link to its terms and a privacy policy, and none of our four series carries a third-party copyright note (checked through the FRED API);
  - alternative.me allows commercial use with attribution next to the data.
- **Fixed in the app now** (it already has users other than Rob in mind):
  - the FRED notice with a link to its terms, under the Macro section and in the footer;
  - "Data provided by CoinGecko", linked, under the dominance chart.
  - The Settings key card dropped two lines left over from before the agent shipped ("used once the agent is switched on", "the model list comes with the agent in v1.1"). The first now shows only while the agent flag is off.
- **README screenshots** (`docs/screenshots/`, 1.6 MB, 11 images at 1440 px plus a 390 px phone view):
  - taken from the local docker database, refreshed with the daily job, with `MCO_ENABLED=false`, so no MCO content appears;
  - the Signals week and the Agent answer are real runs on that local copy: the weekly job (about $0.13 on Rob's Anthropic key, recorded in the local `llm_spend`, not Neon's) and one $0.003 question;
  - production wasn't touched;
  - a throwaway script in the session scratchpad served the API with a fixed local user. It refused any non-local database, and it was never committed, because an auth bypass doesn't belong in the repo.
  To retake them, do the same against a local database, or after the first production weekly run.
- **`docs/RESUME_NOTES.md`:** three bullets, a 60-second summary, and the interview cheat sheet the roadmap asks for. It uses only recorded figures and says plainly that no friends had been invited yet.
