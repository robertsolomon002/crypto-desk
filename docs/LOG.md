# Build log

One line per substage: date, stage, what was done.

- 2026-10-28 · Stage 0.1 (git part) · Repo `robertsolomon002/crypto-desk` created (public), initial commit of ROADMAP.md, CLAUDE.md, .env.example and .gitignore pushed. Account setup and `.env` values still pending with Rob.
- 2026-10-28 · Stage 0.2 · Monorepo scaffolded: uv backend (`desk` CLI, `desk-mcp`, `/api/health`, alembic, Dockerfile), Vite/React/TS frontend (Tailwind 4, shadcn/ui, TanStack Query, React Router, generated API client, health page), config YAMLs, docs, CI (backend on Ubuntu and Windows, frontend checks, Playwright smoke, Docker smoke). Pinned TypeScript 6.0 and switched to `@clerk/react` (D14, D15).
- 2026-10-28 · Stage 0.1 (accounts) · Accounts and keys done: Neon, Clerk (Access mode set via Dashboard; free-plan Invite-only vs Waitlist to confirm in 0.3), Anthropic, Gemini (key in unbilled project `crypto-desk-gemini`), OpenRouter, FRED, CoinGecko Demo, LangSmith (service key), GCP project `crypto-desk-513023` on trial billing with Run/Artifact Registry/Secret Manager APIs on and Rob's Gmail as Owner. GitHub secrets uploaded (non-empty values only). Telegram, Discord and Cloudflare deferred (needed by 1.4 and 2.2).
