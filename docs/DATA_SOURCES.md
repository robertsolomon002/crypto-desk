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

### RSS feeds (`config/feeds.yaml`)

All four configured URLs work locally and in CI: CoinDesk (25 items), Cointelegraph (30), Decrypt (34), The Block (20).

### MCO YouTube channel (private pipeline, Decision 6)

- Channel id **`UCngIhBkikUe6e7tZTjpKK7Q`** (resolved from `youtube.com/@MoreCryptoOnline`; the feed's author is "More Crypto Online").
- Feed `https://www.youtube.com/feeds/videos.xml?channel_id=UCngIhBkikUe6e7tZTjpKK7Q`: local ✅ (15 most recent videos); **CI ❌ on all three GitHub runner attempts (HTTP 404, 500, 500)**. YouTube's RSS is unreliable from cloud IPs.
- Fallback: YouTube Data API v3 `playlistItems.list` on the channel's uploads playlist costs **1 unit**; the default quota is **10,000 units/day** (https://developers.google.com/youtube/v3/determine_quota_cost). It needs an API key with the YouTube Data API enabled (a Rob step in Stage 6.1). See D26.
- Probe output for MCO is limited to the channel id and a video count; no titles, descriptions or summaries go into logs or this repo.

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

### Gemini (video summaries)

- Models (https://ai.google.dev/gemini-api/docs/models): `gemini-3.8-flash` (stable, new), `gemini-3.6-flash` (stable), `gemini-3.5-flash-lite` (stable), `gemini-3.1-flash-lite` (stable). Google recommends 3.5 Flash-Lite or 3.8 Flash for new projects.
- Pricing (https://ai.google.dev/gemini-api/docs/pricing): **free tier, $0 input and output** for these models; free-tier data **is used to improve Google's products**, paid-tier data is not. Paid: 3.8 Flash $0.75/$3.75 per MTok until 2026-12-31 then $1.50/$7.50; 3.5 Flash-Lite $0.30/$2.50.
- Billing (https://ai.google.dev/gemini-api/docs/billing): Google Cloud trial credits **cannot** be used for the Gemini API; tier follows the linked billing account. Our key lives in the unbilled project `crypto-desk-gemini`.
- YouTube URLs (https://ai.google.dev/gemini-api/docs/video-understanding): **preview, no charge, public videos only**; free tier capped at **8 hours of YouTube video per day**; about 100 tokens per second of video at low media resolution. Free-tier RPM/RPD are shown only in AI Studio (https://aistudio.google.com/rate-limit), per project, resetting at midnight Pacific.
- SDK: `google-genai` 2.33 `models.generate_content` with `Part(file_data=FileData(file_uri=<youtube url>))`, `response_json_schema=<Pydantic schema>`, `media_resolution=MEDIA_RESOLUTION_LOW`.
- Probe on MCO's newest crypto video:
  - `gemini-3.5-flash-lite`: ✅ 10 s, 83,747 input / 1,130 output tokens, schema valid (paid-equivalent $0.028). Levels, invalidation and targets looked plausible, but **the BTC bias said "bullish" while the targets were a C-wave down**: the bias field needs a consistency check and Rob's review (D25).
  - `gemini-3.8-flash` and `gemini-3.6-flash`: **503 UNAVAILABLE "high demand"** on the first attempts; a later 3.8 Flash retry succeeded but took **299 s** (83,747 in / 2,804 out, schema valid, paid-equivalent $0.073). Its content was not compared with Flash-Lite. The pipeline needs retries, a model fallback chain and a long client timeout (or async jobs, not a request path).
- Cost if the free tier ever goes away: about 84K tokens per video × 4 a day × 30 days ≈ $0.30/month input + output on Flash-Lite, about $1/month on 3.8 Flash.

## Agent libraries (installed versions)

- `langgraph` 1.2.18: `langgraph.prebuilt.create_react_agent` is **deprecated** (`LangGraphDeprecatedSinceV10`) "in favor of `create_agent` from the `langchain` package". `langchain` is not installed (PyPI latest 1.4.7). `StateGraph` compiled graphs expose `invoke/ainvoke/stream/astream/astream_events`; `stream_mode` is one of `values, updates, checkpoints, tasks, debug, messages, custom`.
- `langchain-core` 1.7.0: `with_structured_output(schema, include_raw=...)`.
- `langchain-mcp-adapters` 0.3.2: `MultiServerMCPClient({"name": {"command", "args", "transport": "stdio"}})` then `await client.get_tools()`. The stdio round trip to a one-tool FastMCP server works (2 + 3 → `5`).
- `mcp` 1.30.0 (`mcp.server.fastmcp.FastMCP`), `google-genai` 2.33.0, `anthropic` 2.3.0, `openai` 3.40.0.

## Hosting and services (free tiers)

| Service | Free tier (official source) |
|---|---|
| **Cloud Run** | Per billing account per month: 2M requests, 180,000 vCPU-s, 360,000 GiB-s, 1 GB egress from North America (https://docs.cloud.google.com/free/docs/free-cloud-features). Streaming HTTP responses supported with no configuration; server must send `Transfer-Encoding: chunked` (https://docs.cloud.google.com/run/docs/triggering/https-request). Request timeout default 300 s, max 3600 s (https://docs.cloud.google.com/run/docs/configuring/request-timeout). Trial: 90 days / $300, no charges during trial; resources stop at trial end unless upgraded. |
| **Neon** | 1 GB storage per project (20 GB total), 100 CU-hours per project per month, scale to zero after 5 min (always on, can't be disabled), 10 branches, 5 GB egress, 6-hour history window (https://neon.com/pricing). |
| **Cloudflare Pages** | 500 builds/month, 1 concurrent build, 20,000 files per site, 25 MiB per file, 100 custom domains; no bandwidth limit listed (https://developers.cloudflare.com/pages/platform/limits/). |
| **Clerk** | Hobby: 50,000 monthly retained users per app; Waitlist mode included; "Secured by Clerk" branding can't be removed (https://clerk.com/pricing). **Invite-only** is set under User & authentication → Access mode (https://clerk.com/docs/guides/secure/restricting-access); Rob confirmed it is selectable on the free plan. Allowlist/blocklist need a paid plan for production. |
| **LangSmith** | Developer plan: 1 seat, 5,000 base traces/month, 14-day retention, then pay-as-you-go billed in arrears (https://www.langchain.com/pricing). Use a **service key**. |
| **Gemini API** | See above. |

## Licenses and message limits

- **Lightweight Charts** (Apache 2.0): add the NOTICE text "TradingView Lightweight Charts™ Copyright (с) 2025 TradingView, Inc." and a link to https://www.tradingview.com/ on a page users can reach; the `attributionLogo` chart option satisfies the link requirement (https://github.com/tradingview/lightweight-charts README and NOTICE).
- **Telegram Bot API**: `sendMessage` text 1–4096 characters after entities parsing (https://core.telegram.org/bots/api#sendmessage); about 1 message/second per chat, 20 messages/minute per group, about 30 messages/second overall (https://core.telegram.org/bots/faq).
- **Discord webhooks**: `content` up to 2000 characters, up to 10 embeds per message (https://docs.discord.com/developers/resources/webhook). Respect `429` / `Retry-After`.
- Telegram and Discord **live tests pending**: the secrets are not set yet. Run `uv run python scripts/probe_llm.py --only notify` once they are, before Stage 1.4.
