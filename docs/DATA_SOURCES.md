# Data sources, free tiers and models

Verified in Stage 0.3 on **2026-10-28**. "Local" means Rob's PC in Ontario; "CI" means a GitHub-hosted `ubuntu-latest` runner (US cloud IP), via `.github/workflows/probe.yml`. Re-run the probes with:

```
cd backend
uv run python scripts/probe_sources.py [--only ccxt,coinmetrics,fred,fng,coingecko,rss,mco,hyperliquid]
uv run python scripts/probe_llm.py [--only anthropic,openrouter,gemini,mcp,notify]   # local only, $0.25 cap
gh workflow run probe.yml [-f only=mco]
```

Decisions that follow from these findings are D20 to D29 in `DECISIONS.md`.

## Market data

### ccxt (4.5.90): Coinbase and Bitstamp

| Exchange id | BTC/USD daily from | ETH/USD from | SOL/USD from | Timeframes | `rateLimit` | Local | CI |
|---|---|---|---|---|---|---|---|
| `coinbase` (Advanced Trade, public) | 2015-07-20 | 2016-05-18 | 2021-06-17 | 1m 5m 15m 30m 1h 2h 6h 1d (**no 4h**) | 34 ms | ✅ | ✅ |
| `coinbaseexchange` | 2015-07-20 | 2016-05-18 | 2021-06-17 | 1m 5m 15m 1h 6h 1d (**no 4h**) | 100 ms | ✅ | ✅ |
| `bitstamp` | **2011-08-18** | 2017-08-16 | 2022-08-18 | 1m 3m 5m 15m 30m 1h 2h **4h** 6h 12h 1d 1w | 75 ms | ✅ | ✅ |

- No keys needed for public OHLCV. Not geo-blocked from the US runner.
- History depth was found by paging 300-day windows from 2010 (`fetch_ohlcv(since=..., limit=300)`).
- `coinbase.fetch_ohlcv` (installed source) sends `start=since`, `end=since + limit × timeframe` and caps `limit` at 300; the response also includes the candle still in progress. `desk.data.market.fetch_daily` pages 300-day windows itself, dedupes the overlapping boundary candle and drops the open day (D31).
- Full daily refresh from scratch for BTC, ETH and SOL took about 11 s locally (Stage 1.1). Coinbase has no ETH candles for 2016-05-21 and 2016-05-22.
- Coinbase has no native 4H candles; 4H bars can be resampled from closed 1h candles (D22).

Watchlist eligibility (Stage 3.4, checked live 2026-11-01, ccxt 4.5.90): `load_markets()` has 1,029 Coinbase markets (405 active USD spot), each with `info.base_name` (for example "Chainlink"). `fetch_ohlcv(market, "1d", since=..., limit=5)` returns only the candles in that window, so a window that starts 366 days back is empty for a coin listed less than a year ago (OPN/USD) and full for older ones (LINK/USD, DOLO/USD).

### Coin Metrics community API

- Base `https://community-api.coinmetrics.io/v4`, no key. Rate limit from response headers: `x-ratelimit-limit: 6000, 6000;w=20` (6,000 requests per 20-second sliding window, plan `download`).
- Free catalog (`/catalog-v2/asset-metrics?assets=btc,eth`), 31 metrics per asset: AdrActCnt, AdrBalCnt, BlkCnt, CapMVRVCur, CapMrktCurUSD, CapMrktEstUSD, FeeTotNtv, FlowInEx*/FlowOutEx*, HashRate, IssTot*, PriceBTC, PriceUSD, ROI1yr, ROI30d, ReferenceRate*, SplyCur, SplyEx*, SplyExpFut10yr, TxCnt, TxTfrCnt, volume_reported_spot_usd_1d.
- **`CapRealUSD` is not free.** Realized cap is derived as `CapMrktCurUSD / CapMVRVCur` (D21).
- Use `paging_from=start` to read history from the beginning; the default pages from the newest end. Values are strings; the response carries `next_page_url` (with `next_page_token`) until the range is exhausted.

| Metric | BTC from | ETH from |
|---|---|---|
| PriceUSD | **2010-07-18** | 2015-08-08 |
| CapMrktCurUSD | 2010-07-18 | 2015-08-08 |
| CapMVRVCur | 2010-07-18 | 2015-08-08 |
| AdrActCnt | 2009-01-03 | 2015-07-30 |
| HashRate | 2009-01-09 | 2015-07-30 (pre-Merge only) |

Local ✅, CI ✅.

## Context data

| Source | Endpoint | Result | Local | CI |
|---|---|---|---|---|
| FRED (key) | `api.stlouisfed.org/fred/series` | DTWEXBGS daily 2006-01-02→; DGS10 daily 1962-01-02→; DFF daily 1954-07-01→; M2SL **monthly** 1959-01-01→ | ✅ | ✅ |
| Fear & Greed | `api.alternative.me/fng/?limit=0` | 3,188 days, 2018-02-01 → today | ✅ | ✅ |
| CoinGecko Demo (key, header `x-cg-demo-api-key`) | `/global` | Current dominance works (BTC 59.5%, ETH 10.5%). No rate-limit headers returned | ✅ | ✅ |
| | `/global/market_cap_chart` | **401, error 10005 "limited to PRO"**: no dominance history on Demo | ❌ | ❌ |
| | `/coins/bitcoin/market_chart` | 365 days ✅; `days=max` → **401, error 10012** (Demo history capped at 365 days) | | |
| Hyperliquid (optional) | `POST api.hyperliquid.xyz/info` `fundingHistory` | Hourly funding for BTC, ETH, SOL | ✅ | ✅ |

### Stage 4.1 findings (2026-11-01)

- **Coin Metrics units** (`/v4/reference-data/asset-metrics?metrics=...` and https://docs.coinmetrics.io/network-data/network-data-overview/mining/hash-rate): `HashRate` is "Varies" by protocol; for **BTC it is TH/s** (`(BlkCnt / 144) * DiffMean * ((2^32 / 10^12) / 600)`), and the latest BTC value (about 1.08e9 on 2026-10-31) is about 1.08 ZH/s. `AdrActCnt` counts unique active addresses (senders and recipients) per day. `CapMVRVCur` is dimensionless.
- **MVRV history in our data** (BTC from 2010-07-18, ETH from 2015-08-08): BTC yearly maxima 2011 7.74, 2013 5.88, 2017 4.72, 2021 3.96, 2024 2.78; ETH 2017 3.14, 2021 2.30. Used for the panel's bands and text (D43).

### Stage 1.2 findings (2026-10-29)

- **Coin Metrics:** several metrics per request work (`metrics=A,B,C`); a metric with no value that day comes back as `null` (ETH `HashRate` from 2022-09-15). Full BTC and ETH history of the five stored metrics is about 50,000 rows, loaded in a few seconds.
- **Fear & Greed:** `timestamp` is 00:00 UTC of the day; the newest row carries `time_until_update`. `metadata.error` is null on success. Full history: 3,189 days from 2018-02-01. **Classification bands** (we store only the value; measured 2026-10-30 from `value_classification` over all 3,190 days): ≤25 Extreme Fear, 26–46 Fear, 47–54 Neutral, 55–75 Greed, ≥76 Extreme Greed. The Overview gauge uses these (`fngLabel` in `frontend/src/lib/format.ts`).
- **FRED observations** (`/fred/series/observations`): missing values are `"."` (for example DGS10 on 2025-12-25). Measured first-release lag (observation date to `realtime_start` with `output_type=4`, 2025-01 to 2026-10): DTWEXBGS 3–8 days, DGS10 1–6, DFF 1–6, M2SL 51–58. ALFRED refuses ranges with more than 2,000 vintage dates (DGS10 and DFF have more than 5,000), and DTWEXBGS has no vintages before 2019. The API key is a query parameter, so errors must not echo the URL (D32).
- **FRED release calendar:** `/fred/release/dates?release_id=10&include_release_dates_with_no_data=true` lists upcoming CPI release dates, but only for the current year (through 2026-12-10 when checked).
- **CoinGecko `/global`:** `data.updated_at` (unix seconds) dates the snapshot; `market_cap_percentage` is in percent. It now also returns `fear_and_greed_index` (not used).
- **Official calendars:** the Fed FOMC page is fetchable by script (2027 meetings listed, "Last Update: October 28, 2026"). **BLS returns HTTP 403 to scripts** ("Access Denied", bot blocking), so the 2027 CPI dates were read from the BLS page in a browser-style fetch and the 2026 dates cross-checked with FRED's release calendar. `config/calendar.yaml` is maintained by hand; Rob double-checks it.

### RSS feeds (`config/feeds.yaml`)

All four configured URLs work locally and in CI: CoinDesk (25 items), Cointelegraph (30), Decrypt (34), The Block (20).

### MCO YouTube channel (private pipeline, Decision 6)

- Channel id **`UCngIhBkikUe6e7tZTjpKK7Q`** (resolved from `youtube.com/@MoreCryptoOnline`; the feed's author is "More Crypto Online").
- Feed `https://www.youtube.com/feeds/videos.xml?channel_id=UCngIhBkikUe6e7tZTjpKK7Q`: local ✅ (15 most recent videos); **CI ❌ on all three GitHub runner attempts (HTTP 404, 500, 500)**. YouTube's RSS is unreliable from cloud IPs.
- Fallback: YouTube Data API v3 `playlistItems.list` on the channel's uploads playlist costs **1 unit**; the default quota is **10,000 units/day** (https://developers.google.com/youtube/v3/determine_quota_cost). It needs an API key with the YouTube Data API enabled (a Rob step in Stage 6.1). See D26.
- Probe output for MCO is limited to the channel id and a video count; no titles, descriptions or summaries go into logs or this repo.
- Checked live in Stage 6.1 (2026-11-03, D48): `channels.list` gives the uploads playlist `UUngIhBkikUe6e7tZTjpKK7Q`; `playlistItems.list` returns `contentDetails.videoPublishedAt`; `videos.list` returns ISO 8601 durations and `snippet.liveBroadcastContent` (`none`, `live`, `upcoming`). Each method costs 1 unit. Many uploads are Shorts (42 to 73 s), so the pipeline skips videos under 180 s.
- google-genai 2.33: without `HttpOptions.retry_options`, a call is tried once; `HttpOptions.timeout` is in milliseconds.

## LLMs

### Anthropic (prices: https://platform.claude.com/docs/en/about-claude/pricing)

| Model id | Input / output per MTok | Probe (structured output, `json_schema`) |
|---|---|---|
| `claude-haiku-5-5` | **$0.10 / $0.50** (prompts ≤100K; $0.50 / $2.50 above) | ✅ 3.0 s, 472 in / 61 out, $0.00008 |
| `claude-haiku-4-5` (snapshot `claude-haiku-4-5-20251001`) | $1.00 / $5.00 | ✅ 2.7 s, 378 in / 34 out, $0.00055 |
| `claude-sonnet-5-5` | $2.00 / $10.00 | ✅ 2.2 s, 472 in / 59 out, $0.00153 |

- Haiku 5.5's newer tokenizer counted the same prompt as about 25% more input tokens than Haiku 4.5; it is still about 8× cheaper per call.
- 5.5 models: adaptive thinking only (no `budget_tokens`), `effort` low…max (Haiku 5.5 defaults to `medium`), no assistant prefill, and **forced `tool_choice` (`any`/`tool`) returns 400 on Sonnet 5.5**. `langchain-anthropic` 1.7.7 knows this (`_supports_forced_tool_choice`) and `with_structured_output(..., method="json_schema")` works on all three models.

### OpenRouter (friends' path)

- `ChatOpenAI(base_url="https://openrouter.ai/api/v1", model=...)` from `langchain-openai` 1.7.3 works. Structured output works with both `json_schema` and `function_calling` on `anthropic/claude-haiku-5.5` (✅ 2.6 s, $0.00008).
- Model ids and prices come from the public `GET https://openrouter.ai/api/v1/models`. Cheap candidates (per MTok, in/out): `anthropic/claude-haiku-5.5` $0.10/$0.50, `openai/gpt-5-nano` $0.05/$0.40, `openai/gpt-5-mini` $0.25/$2.00, `google/gemini-3.5-flash-lite` $0.30/$2.50.

### Key test for friends' own keys (Stage 3.4, checked live 2026-11-01, D42)

- OpenRouter `POST /api/v1/chat/completions` with `max_tokens: 1` on `anthropic/claude-haiku-5.5`: 200, 11 + 1 tokens, `usage.cost` $0.0000016. A bad key gets 401.
- Anthropic `POST /v1/messages` with `max_tokens: 1` and `anthropic-version: 2023-06-01`: 200, `stop_reason: max_tokens`. A bad key gets 401 `authentication_error`. (The current docs show a newer version date in their examples; 2023-06-01 still works.)
- OpenAI `GET /v1/models` with a bad key gets 401 `invalid_api_key`, and **the message echoes part of the key**, so provider error text is never passed on.
- Console links for the Settings wizard: OpenRouter keys `https://openrouter.ai/keys` (a credit limit can be set per key; once a key uses it up, requests with it are rejected until the limit is raised), credits `https://openrouter.ai/settings/credits`; Claude Console keys `https://platform.claude.com/settings/keys`, spend limits on Billing `https://platform.claude.com/settings/billing`; OpenAI keys `https://platform.openai.com/settings/organization/api-keys`, limits `https://platform.openai.com/settings/organization/limits`, spend-limit guide `https://developers.openai.com/api/docs/guides/spend-limits`.

### Gemini (video summaries)

- Models (https://ai.google.dev/gemini-api/docs/models): `gemini-3.8-flash` (stable, new), `gemini-3.6-flash` (stable), `gemini-3.5-flash-lite` (stable), `gemini-3.1-flash-lite` (stable). Google recommends 3.5 Flash-Lite or 3.8 Flash for new projects.
- Pricing (https://ai.google.dev/gemini-api/docs/pricing): **free tier, $0 input and output** for these models; free-tier data **is used to improve Google's products**, paid-tier data is not. Paid: 3.8 Flash $0.75/$3.75 per MTok until 2026-12-31 then $1.50/$7.50; 3.5 Flash-Lite $0.30/$2.50.
- Billing (https://ai.google.dev/gemini-api/docs/billing): Google Cloud trial credits **cannot** be used for the Gemini API; tier follows the linked billing account. Our key lives in the unbilled project `crypto-desk-gemini`.
- YouTube URLs (https://ai.google.dev/gemini-api/docs/video-understanding): **preview, no charge, public videos only**; free tier capped at **8 hours of YouTube video per day**; about 100 tokens per second of video at low media resolution. Free-tier RPM/RPD are shown only in AI Studio (https://aistudio.google.com/rate-limit), per project, resetting at midnight Pacific.
- SDK: `google-genai` 2.33 `models.generate_content` with `Part(file_data=FileData(file_uri=<youtube url>))`, `response_json_schema=<Pydantic schema>`, `media_resolution=MEDIA_RESOLUTION_LOW`.
- Probe on MCO's newest crypto video:
  - `gemini-3.5-flash-lite`: ✅ 10 s, 83,747 input / 1,130 output tokens, schema valid (paid-equivalent $0.028). Levels, invalidation and targets looked plausible, but **the BTC bias said "bullish" while the targets were a C-wave down**: the bias field needs a consistency check and Rob's review (D25).
  - `gemini-3.8-flash` and `gemini-3.6-flash`: **503 UNAVAILABLE "high demand"** on the first attempts; a later 3.8 Flash retry succeeded but took **299 s** (83,747 in / 2,804 out, schema valid, paid-equivalent $0.073). Its content was not compared with Flash-Lite. The pipeline needs retries, a model fallback chain and a long client timeout (or async jobs, not a request path).
- Cost if the free tier ever goes away: about 84K input + 1.1K output tokens per video, about $0.028 on Flash-Lite, so **about $3.40/month** at 4 videos a day (about $8/month on 3.8 Flash). *Corrected in Stage 6.1 (D48): the earlier "$0.30/month" was about 10× too low.*

## Agent libraries (installed versions)

- `langgraph` 1.2.18: `langgraph.prebuilt.create_react_agent` is **deprecated** (`LangGraphDeprecatedSinceV10`) "in favor of `create_agent` from the `langchain` package". `langchain` is not installed (PyPI latest 1.4.7). `StateGraph` compiled graphs expose `invoke/ainvoke/stream/astream/astream_events`; `stream_mode` is one of `values, updates, checkpoints, tasks, debug, messages, custom`.
- `langchain-core` 1.7.0: `with_structured_output(schema, include_raw=...)`.
- `langchain-mcp-adapters` 0.3.2: `MultiServerMCPClient({"name": {"command", "args", "transport": "stdio"}})` then `await client.get_tools()`. The stdio round trip to a one-tool FastMCP server works (2 + 3 → `5`).
- `mcp` 1.30.0 (`mcp.server.fastmcp.FastMCP`), `google-genai` 2.33.0, `anthropic` 2.3.0, `openai` 3.40.0.

### MCP SDK and Claude desktop (Stage 4.2, checked 2026-11-01)

- `mcp` 1.30.0 (installed source): `FastMCP.add_tool(fn, name, title, description, annotations, icons, meta, structured_output)`. A tool returning `str` becomes one `TextContent` as-is (other values go through `pydantic_core.to_json(..., indent=2)`); `structured_output=False` turns off the structured copy and the output schema. An exception in a tool becomes `isError` with "Error executing tool <name>: <message>"; an unregistered name gives "Unknown tool". Sync tool functions run directly on the event loop (fine for one stdio client). The SDK logs INFO lines to stderr.
- Claude desktop (https://modelcontextprotocol.io/docs/develop/connect-local-servers): Settings → Developer → Edit Config opens `%APPDATA%\Claude\claude_desktop_config.json`; `mcpServers.<name>` takes `command`, `args` and optional `env`; paths must be absolute; quit and restart the app to load changes; logs in `%APPDATA%\Claude\logs` (`mcp.log`, `mcp-server-<name>.log` with the server's stderr). The exact command in `docs/USING_WITH_CLAUDE.md` was run with the SDK client from Rob's PC against Neon: 1.9 s to initialize, 19 tools, `get_key_levels` answered.

### Agent runtime (Stage 5.1, checked 2026-11-03 in the installed source and live)

- `langchain-mcp-adapters` 0.3.2: `load_mcp_tools(session)` takes an open `ClientSession`; `mcp` 1.30.0 `mcp.shared.memory.create_connected_server_and_client_session(server)` runs a FastMCP server in-process over memory streams (inside an anyio task group, which wraps errors in exception groups). A tool error comes back as a `ToolMessage` with `status="error"`. FastMCP follows `functools.wraps` to the original signature, so a coroutine wrapper keeps each tool's schema.
- FastAPI 0.162 `fastapi.sse.EventSourceResponse` + `ServerSentEvent(event=..., data=...)`: works with POST, data is always JSON-encoded, the generator runs in a producer task with keepalive comments, and `Cache-Control: no-cache` and `X-Accel-Buffering: no` are set. Starlette's `GZipMiddleware` excludes `text/event-stream` by default.
- `langchain-anthropic` 1.7.7: `ChatAnthropic(effort="low")` sets `output_config.effort`; `bind_tools(tool_choice=...)` turns a string into a tool name, so "no tools" must be the dict `{"type": "none"}`; an API key not passed falls back to `ANTHROPIC_API_KEY`.
- `langchain-openai` 1.7.3: `bind_tools(tool_choice="none")` passes through; `stream_usage=True` adds `stream_options.include_usage`; `use_responses_api` defaults on for `gpt-6*` models with tools (so OpenRouter sets it off); `reasoning_effort` becomes `reasoning.effort` on the Responses API.
- OpenAI models (https://developers.openai.com/api/docs/pricing and the model pages): `gpt-6-luna` $0.10 / $0.50 per MTok, function calling and streaming, Chat Completions function calling "only with `reasoning_effort` set to `none`"; `gpt-5.6-luna` $0.20 / $1.20, no such restriction; `gpt-5-mini` $0.25 / $2.00; `gpt-5-nano` $0.05 / $0.40 but **deprecated** (OpenAI points to the Luna models).
- Live: "Where is BTC in its cycle vs 2017?" on the server key (Haiku 5.5) took 1 tool call (`get_cycle_comparison`), 10 to 12 s, about 17K input / 2K to 3K output tokens over two model calls, **$0.0027 to $0.0032**. Through OpenRouter (`anthropic/claude-haiku-5.5`) the same question took the same path in 12 s. Haiku 5.5's adaptive thinking counts toward `max_tokens`: at 2,000 the answer was cut off (`stop_reason: max_tokens`), hence 4,000.
- LangSmith (langsmith 0.14.14): `tracing_context(enabled=..., client=...)` overrides `LANGSMITH_TRACING`, and LangChain's tracer takes its client from that context. Rob's `lsv2_sk_` service key is organization-scoped: `GET /api/v1/workspaces` works, but runs and projects answer **403** until the workspace id is sent (`X-Tenant-Id`, which `Client(workspace_id=...)` or `LANGSMITH_WORKSPACE_ID` sets). With it, the traced run posted (9 runs: graph, nodes, ChatAnthropic, tool) and no server key appeared in the stored runs.

## Hosting and services (free tiers)

| Service | Free tier (official source) |
|---|---|
| **Cloud Run** | Per billing account per month: 2M requests, 180,000 vCPU-s, 360,000 GiB-s, 1 GB egress from North America (https://docs.cloud.google.com/free/docs/free-cloud-features). Streaming HTTP responses supported with no configuration; server must send `Transfer-Encoding: chunked` (https://docs.cloud.google.com/run/docs/triggering/https-request). Request timeout default 300 s, max 3600 s (https://docs.cloud.google.com/run/docs/configuring/request-timeout). Trial: 90 days / $300, no charges during trial; resources stop at trial end unless upgraded. |
| **Neon** | Pooler is PgBouncer in transaction mode; **schema migrations use the direct host** (the pooled host minus `-pooler`) because "tools may not support transaction pooling"; no SET/RESET, session advisory locks, SQL-level PREPARE or LISTEN/NOTIFY over the pooler, protocol-level prepared statements are fine (https://neon.com/docs/connect/connection-pooling, checked 2026-10-28). Migration `0001` and the market load ran this way in Stage 1.1. 1 GB storage per project (20 GB total), 100 CU-hours per project per month, scale to zero after 5 min (always on, can't be disabled), 10 branches, 5 GB egress, 6-hour history window (https://neon.com/pricing). |
| **Cloudflare Pages** | 500 builds/month, 1 concurrent build, 20,000 files per site, 25 MiB per file, 100 custom domains; no bandwidth limit listed (https://developers.cloudflare.com/pages/platform/limits/). |
| **Clerk** | Hobby: 50,000 monthly retained users per app; Waitlist mode included; "Secured by Clerk" branding can't be removed (https://clerk.com/pricing). **Invite-only** is set under User & authentication → Access mode (https://clerk.com/docs/guides/secure/restricting-access); Rob confirmed it is selectable on the free plan. Allowlist/blocklist need a paid plan for production. **Session tokens** (checked 2026-10-29): sent cross-origin as `Authorization: Bearer`, RS256, verify with the JWKS at `<Frontend API URL>/.well-known/jwks.json` (or `https://api.clerk.com/v1/jwks`); check `exp`, `nbf`, and `azp` against known origins; reject `sts=pending` (https://clerk.com/docs/guides/sessions/manual-jwt-verification). Default claims: `iss` (Frontend API URL), `sub` (user id), `sid`, `azp`, `exp`, `iat`, `nbf`, `v`, `fva`, `sts`, `pla`, `fea`, `o`, `jti`, `act`; public metadata is not included by default (https://clerk.com/docs/guides/sessions/session-tokens). Publishable key = `pk_test_`/`pk_live_` + base64 of `<frontend-api-host>$` (https://clerk.com/docs/guides/how-clerk-works/overview). **Invitations** (Backend API): `POST /v1/invitations` (`email_address`; optional `redirect_url`, `public_metadata`, `notify` default true, `ignore_existing`, `expires_in_days` default 30), `GET /v1/invitations` (`status`, `query`, `limit` 1 to 500, `offset`), `POST /v1/invitations/{id}/revoke`; statuses `pending`, `accepted`, `revoked`, `expired`; creating is limited to 100/hour per instance (https://clerk.com/docs/reference/backend/invitations/create-invitation, https://clerk.com/docs/guides/users/inviting). |
| **Secret Manager** | Free per billing account per month: 6 active secret versions (enabled *or disabled*; only destroyed versions are free), 10,000 access operations, 3 rotation notifications; then $0.06 per active version per month and $0.03 per 10,000 accesses. An automatic replication policy counts as one location (https://cloud.google.com/secret-manager/pricing, checked 2026-10-30). Cloud Run reads env-var secrets once per instance start. |
| **Artifact Registry** | 0.5 GiB storage free per billing account, then about $0.10/GiB-month (https://cloud.google.com/artifact-registry/pricing). Cleanup policies: keep rules beat delete rules; `mostRecentVersions.keepCount`; `olderThan` like `1d`; applied by a background job "within approximately one day"; `--no-dry-run` to actually delete (https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy). |
| **Cloud Run (deploy)** | The free tier is a spending-based discount at Tier 1 (us-central1) prices: request-based billing 180,000 vCPU-s, 360,000 GiB-s and 2M requests; instance-based 240,000 vCPU-s and 450,000 GiB-s (https://cloud.google.com/run/pricing). Startup CPU boost is billed as normal CPU during startup. Deploying needs `roles/run.developer` plus `roles/iam.serviceAccountUser` on the runtime service account. Disabling the invoker IAM check (`--no-invoker-iam-check`, the recommended way to make a service public) needs `run.services.setIamPolicy`, which is in `roles/run.admin` (https://docs.cloud.google.com/run/docs/authenticating/public). |
| **Cloudflare Pages (deploy)** | Commands: `wrangler pages project create <name> --production-branch` and `wrangler pages deploy <dir> --project-name --branch --commit-hash --commit-dirty`, authenticated by `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` (https://developers.cloudflare.com/workers/wrangler/commands/pages/). Without a top-level `404.html`, Pages runs in SPA mode and serves `/` for unknown paths (https://developers.cloudflare.com/pages/configuration/serving-pages/). Previews are `<hash>.<project>.pages.dev`, with branch aliases `<branch>.<project>.pages.dev` (lower-cased, non-alphanumerics to `-`) and `X-Robots-Tag: noindex` (https://developers.cloudflare.com/pages/configuration/preview-deployments/). `_headers` allows up to 100 rules and 2,000 characters per line (https://developers.cloudflare.com/pages/configuration/headers/). Rollback is in the dashboard: Deployments, "Rollback to this deployment" (production deployments only). **Found in the wrangler 4.153 source (`src/pages/delegate-to-workers.ts`):** when it detects an AI agent and the project does not exist, `pages project create` and `pages deploy` delegate to Workers static assets; `--force` opts out. It never happens in CI or for an existing project. If the name is taken on pages.dev, Cloudflare adds a suffix (ours: `crypto-desk-a9f`). |
| **Clerk (React SDK, Stage 3.1)** | `@clerk/react` 6.18.3 (checked in the installed types, 2026-10-30): `<Show when="signed-in" / "signed-out">` replaces the old `SignedIn`/`SignedOut`; `useAuth().getToken()` returns the session JWT; `<SignIn routing="hash" />` needs no sign-in route; `<UserButton />`; `ClerkProvider` takes `publishableKey` and `afterSignOutUrl`. **Invite-only (restricted) mode:** "The `<SignUp />` is accessible only to users who have been invited and have a valid invitation link"; users are added "through invitations, enterprise connections or manual user creation" (https://clerk.com/docs/guides/secure/restricting-access). So the first admin is created in the Dashboard (Users → Create user) or invited by email. |
| **Clerk (deploy)** | CSP needs: the Frontend API host in `script-src` and `connect-src`; `https://*.protect.clerk.com` (connect-src with `:*`) and `https://challenges.cloudflare.com` in `script-src` and `frame-src`; `https://img.clerk.com` in `img-src`; `worker-src 'self' blob:`; `style-src 'unsafe-inline'` (https://clerk.com/docs/guides/secure/best-practices/csp-headers, checked 2026-10-30). Backend API (spec `bapi/2026-08-20.yml` in github.com/clerk/openapi-specs): `POST /v1/sessions` `{user_id}` "is intended only for use in testing, and is not available for production instances"; `POST /v1/sessions/{id}/tokens` `{expires_in_seconds}` (min 30) returns `{object: "token", jwt}`; `POST /v1/sessions/{id}/revoke`; `GET /v1/users?external_id=`; `POST /v1/users` accepts `external_id`, `email_address[]` and `skip_password_requirement`. |
| **LangSmith** | Developer plan: 1 seat, 5,000 base traces/month, 14-day retention, then pay-as-you-go billed in arrears (https://www.langchain.com/pricing). Use a **service key**. |
| **Gemini API** | See above. |
| **Neon (backups and limits, Stage 8.1)** | Free plan (https://neon.com/docs/introduction/plans, checked 2026-11-04): 1 GB Postgres storage per project, 100 CU-hours a month per project, 10 branches, instant restore up to 6 hours (1 GB of change history), **1 manual snapshot and no scheduled backups**, console monitoring keeps 1 day and metrics export is not available. Our server is Postgres 18.6 (`SHOW server_version`); `pg_dump` must be the same major version or newer. Backup docs (https://neon.com/docs/manage/backups) list instant restore, manual `pg_dump`/`pg_restore`, and a nightly `pg_dump` from a GitHub Action. |
| **Cloud Storage (backups, Stage 8.1)** | Free tier (https://docs.cloud.google.com/free/docs/free-cloud-features, 2026-11-04): 5 GB-months of regional storage in us-east1, us-west1 and us-central1 combined, 5,000 Class A and 50,000 Class B operations a month, 100 GB egress from North America. `roles/storage.objectCreator` has `storage.objects.create` (and multipart upload) but not get, list or delete: it "does not give permission to view, delete, or overwrite objects" (https://docs.cloud.google.com/storage/docs/access-control/iam-roles). `gcloud storage buckets create` takes `--location`, `--default-storage-class`, `--uniform-bucket-level-access`, `--public-access-prevention` (both booleans with `--no-` forms) and `--lifecycle-file`; a lifecycle rule `{"action": {"type": "Delete"}, "condition": {"age": N}}` deletes objects N days old (https://docs.cloud.google.com/storage/docs/lifecycle-configurations). |
| **Cloud Run logging (Stage 8.1)** | A one-line JSON object on stdout/stderr goes to `jsonPayload`; `severity` becomes the entry's severity, `message` its text, and `logging.googleapis.com/trace` links it to the request log; exceptions in container logs reach Error Reporting (https://docs.cloud.google.com/run/docs/logging, 2026-11-04). Cloud Logging includes 50 GiB of logs per project per month. |
| **Sentry (not used, Stage 8.1)** | Developer plan: 1 user, 5k errors, 30-day lookback, no spend limits (https://sentry.io/pricing, 2026-11-04). Not used (D53): exception data would leave our hosting, and structured logs plus `app_errors` counts cover our needs. |
| **PGDG apt repository** | `sudo apt install -y postgresql-common` then `sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh`; the client-only package is `postgresql-client-18` (https://www.postgresql.org/download/linux/ubuntu/). The script waits for Enter unless given an option such as `-y` (checked in its source on salsa.debian.org, 2026-11-04). |

## Licenses and message limits

- **Coin Metrics community data** (Stage 8.2, 2026-11-04): "Available to the community under the Creative Commons license", linked to CC BY-NC 4.0 (https://docs.coinmetrics.io/packages/coin-metrics-community-data). Attribution required, non-commercial only; commercial use needs a license (Coin Metrics is now part of Talos, datasupport@talostrading.com). `coinmetrics.io/api/terms` now redirects to Talos's data page.
- **CoinGecko Demo** (Stage 8.2): 10,000 calls a month, 100 a minute, attribution required, no commercial license; Basic is $35 a month ($29 billed yearly) with 100,000 calls and a commercial license (https://www.coingecko.com/en/api/pricing). The attribution guide asks for a linked credit such as "Data provided by CoinGecko", close to the data (https://brand.coingecko.com/resources/attribution-guide). Shown under the dominance chart.
- **FRED API terms** (Stage 8.2, https://fred.stlouisfed.org/docs/api/terms_of_use.html): show "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis", link the Terms of Use and tell users they are bound by them; publish a privacy policy when collecting user information; no "FRED" in the hostname and no Fed logos; series whose notes say "Copyright" need their owner's permission beyond personal use. DTWEXBGS, DGS10, DFF and M2SL have no copyright note (FRED `series` API, 2026-11-04). The notice is in the footer and under the Macro section.
- **alternative.me Fear & Greed** (Stage 8.2): "Commercial use is allowed as long as the attribution is given right next to the display of the data"; no impersonation (https://alternative.me/crypto/fear-and-greed-index/).
- **Paid tiers for the public-readiness costs** (Stage 8.2, 2026-11-04): Cloud Run request-based billing in us-central1 is $0.000024 per vCPU-second, $0.0000025 per GiB-second and $0.40 per million requests after 2 million (Cloud Billing Catalog API, service `152E-C115-5142`); Neon Launch is $0.106 per CU-hour and $0.35 per GB-month, with no minimum (https://neon.com/pricing); Clerk Pro is $25 a month with 50,000 MRUs included, then $0.02 each (https://clerk.com/pricing).

- **Lightweight Charts** (Apache 2.0): add the NOTICE text "TradingView Lightweight Charts™ Copyright (с) 2025 TradingView, Inc." and a link to https://www.tradingview.com/ on a page users can reach; the `attributionLogo` chart option satisfies the link requirement (https://github.com/tradingview/lightweight-charts README and NOTICE).
- **Telegram Bot API**: `sendMessage` text 1–4096 characters after entities parsing (https://core.telegram.org/bots/api#sendmessage); about 1 message/second per chat, 20 messages/minute per group, about 30 messages/second overall (https://core.telegram.org/bots/faq).
- **Discord webhooks**: `content` up to 2000 characters, up to 10 embeds per message (https://docs.discord.com/developers/resources/webhook). Respect `429` / `Retry-After`.
- Telegram and Discord **live tests done 2026-10-29**: a bot message to Rob's chat and a message to each webhook (public and ops) delivered. Pasted webhook URLs can carry a leading space; `.env` values must start with `https://discord.com/api/webhooks/`. Re-test with `desk notify test` (locally, or from GitHub with the Daily workflow's `notify_test` input).
