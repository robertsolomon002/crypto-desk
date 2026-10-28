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
