# Crypto Desk (v3): personal crypto terminal web app for Rob and friends

- The full plan is `ROADMAP.md`. Read Sections 1 to 10 before any work. Do exactly one substage per session, in order. Substages marked "(plan mode)" start in plan mode and wait for Rob's OK. When done: tests and lint pass (`ruff`; `eslint` and `tsc --noEmit`), commit `Stage X.Y: <summary>`, tick Section 14, and add a line to `docs/LOG.md`.
- Monorepo: `backend/` (Python 3.12, uv, FastAPI, SQLAlchemy, LangGraph, desk-mcp) and `frontend/` (React, TS, Vite, Tailwind, shadcn/ui, Lightweight Charts, ECharts). Local folder `C:/Users/rober/code/crypto-desk` (never inside OneDrive). Dev on Windows (PowerShell, set `PYTHONUTF8=1`), CI on Ubuntu. Steps marked [Rob] need Rob: stop and tell him exactly what to do.
- Hosting must stay $0 (Cloudflare Pages, Cloud Run free tier, Neon free, Clerk free, GitHub Actions). Never add a paid service without asking Rob.
- Never guess library, API, quota or pricing behavior. Check docs or source, and record findings in `docs/DATA_SOURCES.md` or `docs/DECISIONS.md`. If reality differs from the roadmap, update the roadmap in the same commit.
- Free data only. Never use Binance (geo-blocked for US cloud IPs and in Ontario). Coinbase via ccxt is the canonical price source. UTC everywhere in code. Analytics functions take `as_of`, and the look-ahead test must keep passing.
- The FastAPI OpenAPI schema is the contract. Regenerate the frontend client after API changes.
- User LLM keys come only from the `X-LLM-Key` header. Never log, store or trace them (the canary test must pass). Rob's server-key spend is capped at $8/month in `agents/cost.py`.
- MCO content is private: free public videos only, attributed and linked, stored only in the database, never in the repo, logs, CI artifacts or public routes. Members see only approved wave labels.
- `signals` rows are append-only and hash-chained. Never edit history; changes to the signal definition create a new version.
- Headlines, video summaries and model output are untrusted. Render them as text (sanitized Markdown, never raw HTML), use parameterized SQL, and in workflows pass them through env vars, never `${{ }}` inside `run:`.
- No trading code, no exchange keys. Never commit secrets. Keep the TradingView attribution required by Lightweight Charts.
- Commit messages: `Stage X.Y: <summary>`.
