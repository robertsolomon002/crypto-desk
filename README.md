# Crypto Desk

A private, invite-only crypto terminal for Rob and a few friends, built on free data: charts and indicators, cycle comparisons, seasonality and stats, on-chain and macro data, an AI agent that shows exactly which data it used, and a weekly signals brief. The plan is in [ROADMAP.md](ROADMAP.md).

> **Not financial advice.** This project is for information and education only. It does no trading, holds no exchange keys and places no orders.

## Layout

- `backend/`: Python 3.12 (uv), FastAPI, SQLAlchemy, Alembic, LangGraph, the `desk` CLI and the `desk-mcp` server
- `frontend/`: React, TypeScript, Vite, Tailwind, shadcn/ui, Lightweight Charts, ECharts
- `config/`: coins, cycle anchors, feeds, FRED series, models and app settings
- `docs/`: decisions, architecture and the build log

## Local development (Windows PowerShell)

```powershell
# One-time
Copy-Item .env.example .env            # then fill it in; never commit .env
$env:PYTHONUTF8 = "1"
cd backend; uv sync; cd ..
cd frontend; npm install; npx playwright install chromium; cd ..

# Local Postgres (needs Docker Desktop running); set DATABASE_URL=postgresql://desk:desk@localhost:5432/desk in .env
docker compose up -d db

# Backend API on http://127.0.0.1:8000 (docs at /docs)
cd backend; uv run desk api serve --reload

# Frontend on http://localhost:5173 (proxies /api to the backend)
cd frontend; npm run dev
```

Checks: `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest` in `backend/`; `npm run typecheck`, `npm run lint`, `npm test` and `npm run test:e2e` in `frontend/`.

After any API change: `uv run desk api openapi --out ../frontend/openapi.json` in `backend/`, then `npm run gen:api` in `frontend/`. CI fails if either is stale.

## Credits

Price charts use [TradingView Lightweight Charts](https://www.tradingview.com/lightweight-charts/) (the attribution is kept in the app). Data sources are listed in `docs/DATA_SOURCES.md`.

## License

MIT for the code. No data or third-party content is included in this repository.
