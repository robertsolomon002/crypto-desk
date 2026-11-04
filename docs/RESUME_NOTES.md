# Resume notes

Material for Rob's CV and interviews. Every figure here was measured or recorded in the repo (`docs/LOG.md`, `docs/DECISIONS.md`) as of 2026-11-04. Update the numbers before using them later: users, weeks of signals and spend will have moved.

## Three resume bullets

- **Built and deployed a multi-user crypto research terminal** (React/TypeScript, FastAPI, Postgres) with 10 tabs: charts, cycle comparisons, seasonality, on-chain and macro data, an AI agent, weekly signals and a data browser. It runs on 6 free data sources and $0 of hosting (Cloud Run, Neon, Cloudflare Pages, Clerk, GitHub Actions). Every number on screen can be inspected and exported, and a look-ahead test guards every analytics function against using future data.
- **Designed an MCP server (19 read-only tools in 5 access groups)** used both by an in-app LangGraph agent and by the Claude desktop app. Built a multi-agent desk on top of it: parallel analysts limited to their own tool groups, a cited bull/bear debate, a head and a deterministic validator. Every tool call is saved, so users can open the exact data behind any answer.
- **Engineered for cost and safety:** a hard $8-a-month LLM cap enforced in code with three degradation steps (about $0.20 spent in the first week; a desk run costs under a cent, and the weekly job for 3 coins about $0.10). Also built:
  - bring-your-own-key auth, where keys never touch the server's storage or logs (a canary test checks);
  - append-only, hash-chained signal records;
  - CI on Windows and Ubuntu with about 575 backend tests and 300 frontend tests;
  - monitoring with encrypted backups;
  - a load check that caught and fixed a rate-limit race.

Shorter variants: "Built a crypto research terminal with an MCP-powered AI agent and multi-agent signal desk; $0 hosting, $8/month hard LLM cap, full data provenance." / "Designed a 19-tool MCP server reused by an in-app LangGraph agent and Claude desktop."

## 60-second summary (spoken)

> I trade large-cap crypto over days to weeks. The good research terminals are paywalled, so I built my own for me and a few friends, entirely on free data and free hosting.
>
> It's a React and FastAPI app with ten tabs: charts and indicators, BTC's cycles lined up against past ones, seasonality, on-chain and macro data, and a data tab where every number can be inspected and exported.
>
> The interesting part is the AI. I wrote an MCP server, 19 read-only tools over the same analytics code the app uses. An in-app LangGraph agent uses it, and so does Claude on my desktop. Every tool call is saved, so you can click "view data" and see exactly what the model looked at.
>
> On top of that is a multi-agent desk: two analysts in parallel, a bull and a bear who debate, a head who makes the call, and a deterministic validator. It writes a weekly signal per coin, and a scorecard compares it against a coin flip and a simple trend rule.
>
> Friends bring their own LLM key, which never touches my storage. My own spend has a hard $8 cap in code. So far it's cost about twenty cents.

## Interview cheat sheet

### MCP tool design and group-based access

- **One definition, two clients:**
  - `desk-mcp` (the official `mcp` SDK, FastMCP) wraps the same read functions the API routes call, so a number in the app and a number the agent used come from the same code;
  - the in-app agent connects over the SDK's in-memory transport (no subprocess per chat, D45);
  - Claude desktop connects over stdio.
- **19 tools in 5 groups:** market, cycles, stats, context and views. `--groups` limits which tools a client sees. The desk uses this as access control: the technical analyst gets market, cycles and stats; the context analyst gets context and views (D47). An analyst can't wander into the other's data, which keeps the reports independent and the prompts small.
- **Tool design:**
  - every tool is read-only and takes `as_of`;
  - results are compact JSON with `as_of` and `sources`, so the model can cite them;
  - errors come back as tool results rather than exceptions, so one bad call never ends an answer.
- **Trade-off:** fewer, broader tools keep the model's choice simple. The limits were 10 tool calls and 90 seconds per answer.

### Agent provenance ("view the data it used")

- Every tool call's arguments and result are saved as an `agent_snapshot` row before the answer continues, and the stream sends `tool_start` and `tool_end` events with the snapshot id.
- The UI shows each call as a card; "View data" opens that exact snapshot in the Data tab as a table and a chart. The desk's whole graph state (reports, debate, signal) is one snapshot too.
- Why it matters: LLM answers about markets are only as good as the numbers behind them, and this makes a wrong answer easy to catch.

### The multi-agent graph

- A LangGraph `StateGraph` per coin:
  1. a technical and a context analyst run in parallel, each returning a structured report with finding ids;
  2. bull and bear give openings, then rebuttals, in parallel. They have no tools, and every claim must cite a finding id;
  3. the head returns the Decision 8 signal (`lean_long` or `flat`, confidence 0.5 to 0.95, entry zone, invalidation, target);
  4. a deterministic validator checks the schema, the ranges and `invalidation < entry < target`, and routes back to the head once.
- **Time limits:** 180 seconds per run, 60 per analyst, 30 per turn. A late analyst is marked unavailable and the debate continues without it. A signal that is invalid twice is reported, never replaced.
- **Measured:** a SOL run took 16.7 s, 11 model calls and 9 tool calls, for $0.0072 (Haiku 5.5). The weekly job for 3 coins plus a Sonnet-written brief cost about $0.09 to $0.11.
- **Scoring:** signals are append-only and hash-chained (a database trigger refuses UPDATE and DELETE). Outcomes are scored on hit rate, Brier score, target before invalidation, and paper P&L after costs, against a coin flip and a 20-week-SMA trend rule. An "early days" badge stays on until 12 weeks of history.

### Bring-your-own-key security

- Friends' keys (one OpenRouter key is the recommended path) stay in `localStorage` and are sent only in an `X-LLM-Key` header to the agent routes.
- The outermost middleware strips the header before anything else sees the request, and holds the key as a `SecretStr`. A log-record factory redacts it from any log line.
- A canary-key test checks logs, the database, error messages and LangSmith traces. Only server-key runs are traced at all, through a scrubbing client.
- There is a strict CSP with no third-party scripts beyond Clerk and the chart libraries, and model output is rendered as sanitized text.
- **Next step for a public launch:** envelope-encrypted server-side storage (`docs/PUBLIC_READINESS.md`).

### Free-tier architecture

- **The pieces:**
  - Cloudflare Pages for the frontend;
  - Cloud Run with min 0 and max 2 instances, deployed through Workload Identity Federation with smoke-tested no-traffic revisions;
  - Neon Postgres (pooled host for the app, direct host for migrations and dumps);
  - Clerk for invite-only auth;
  - GitHub Actions cron for the daily, weekly, level-watch, MCO and ops jobs.
- **Writes happen in jobs; the API mostly reads.** That keeps the API cheap and cold starts harmless.
- **Guard rails:**
  - only the newest container image is kept (free registry storage is 0.5 GiB);
  - secrets are counted against the free versions;
  - a $1 budget alert;
  - per-user limits counted in the database (row-locked after the load check showed concurrent requests could slip past).
- **Ops:** an admin Health page (jobs, freshness, spend, errors, usage), a weekly Telegram summary, and encrypted weekly `pg_dump`s to a bucket the job can only add to. Neon Free keeps only 6 hours of history.

### Analytics correctness and the look-ahead test

- **Pure functions with `as_of`:** indicators, regime, key levels, zigzag pivots, cycle alignment, seasonality, distributions, drawdowns, correlations.
- **The look-ahead test:** for random `as_of` dates, results on the full data must equal results on data truncated at `as_of`. This is what makes the agent's snapshots and the weekly signals honest.
- **Cycle anchors:**
  - the lowest and highest closes in each window, available only once the window has ended;
  - checked against an independent source;
  - BTC before 2015 comes from Coin Metrics.
- **Other checks:** browser-side indicators match a backend-generated fixture, weekly bars are resampled Monday to Monday in UTC, and FRED series get release lags so an as-of read never sees data that wasn't published yet.

### What Rob would build next

- Let the signals scorecard run for 12+ weeks, then compare the desk with the baselines honestly (and change the signal definition only as a new version).
- An eval set for the desk: recorded weeks replayed with different prompts and models, scored before anything changes in production.
- Per-friend watchlists and alerts, and Telegram bot commands (`/price SOL`, `/cycle`) answered from the same API.
- Encrypted server-side keys and the rest of the public-readiness list, if it ever opens up.
- More outside analysts through the same private, attributed pipeline as MCO, if they agree.

## Facts to have ready

- **Built:** 2026-10-28 to 2026-11-04 with Claude Code. 24 substages, each one committed, tested and logged, with 54 decision records.
- **Data:**
  - 11,739 daily candles (BTC from 2010-07-18);
  - 17 daily series (about 68,000 points);
  - 4 news feeds;
  - an FOMC/CPI calendar.
- **Tests:** about 575 backend tests (including Postgres tests in CI), about 210 frontend unit tests and about 90 Playwright tests at 1440 and 390 px.
- **Users so far:** Rob, plus a test member. Friend onboarding (invites, the key wizard, the setup guide) is ready but no friends had been invited by 2026-11-04. Don't claim more users than that.
- **LLM spend in the first week:** about $0.20 on the server key.
