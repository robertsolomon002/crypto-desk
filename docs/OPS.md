# Operations

First version: Stage 2.2 (2026-10-30); monitoring, backups and runbooks added in Stage 8.1 (2026-11-04). Why it is set up this way: D38 and D53 in `DECISIONS.md`.

## URLs

| What | Where |
|---|---|
| App (production) | https://crypto-desk-a9f.pages.dev |
| App previews | `https://<branch>.crypto-desk-a9f.pages.dev` (one per pull request branch) and `https://<hash>.crypto-desk-a9f.pages.dev` (one per deployment) |
| API | https://desk-api-850576035365.us-central1.run.app (health: `/api/health`, docs: `/docs`) |
| Cloud Run console | https://console.cloud.google.com/run/detail/us-central1/desk-api?project=crypto-desk-513023 |
| Cloud Run logs | https://console.cloud.google.com/run/detail/us-central1/desk-api/logs?project=crypto-desk-513023 |
| Cloudflare Pages | Cloudflare dashboard → Workers & Pages → `crypto-desk` |
| Neon | Neon console → project → branch `main` |
| Workflows | https://github.com/robertsolomon002/crypto-desk/actions |

The API's first request after idle is a cold start of a few seconds (Decision 5).

## How deploys happen

Both deploy workflows start when **CI passes on a push to `main`**. Nothing deploys from a red commit or from a pull request's code with production rights.

- **Backend** (`.github/workflows/deploy-backend.yml`):
  0. skip everything if nothing under `backend/`, `config/` or `prompts/` changed since the live revision's commit (manual runs always deploy);
  1. build the image `us-central1-docker.pkg.dev/crypto-desk-513023/desk/api:<sha>` and push it;
  2. `desk db upgrade` (migrations over Neon's direct host);
  3. deploy a Cloud Run revision with **no traffic**, tagged `candidate`;
  4. `desk deploy smoke` against the candidate URL (health, 401 without a token, CORS, one authenticated call as the `desk-smoke` test user);
  5. move 100% of traffic to it.

  If any step fails, users keep the previous revision and an `ops_failure` alert goes to Telegram and the Discord ops channel.
- **Frontend** (`.github/workflows/deploy-frontend.yml`): `npm run build` (which writes `dist/_headers` with the CSP), `wrangler pages deploy` to branch `main`, then a smoke check of `/` and `/charts` on the deployment URL and the production URL.
- **Previews:** open a pull request that touches `frontend/`. The workflow deploys `https://<branch>.crypto-desk-a9f.pages.dev`, which talks to the production API. Clerk accepts it because CORS and the token `azp` check allow `*.crypto-desk-a9f.pages.dev`.
- **By hand:** Actions → "Deploy backend" or "Deploy frontend" → Run workflow (on `main`). This redeploys the current `main`.

### Migrations

They run before the new revision gets traffic, while the old one is still serving, so **every migration must work with the code that is already live**: add tables and nullable columns freely; drop or rename only in a later deploy, once no live code uses them. Never migrate on app start.

To run them by hand (for example after restoring a database):

```powershell
cd backend; $env:PYTHONUTF8 = "1"
uv run desk db upgrade   # uses DATABASE_URL from .env; switches the pooled host to the direct host
```

## Roll back

**Backend, usual way:** `git revert <bad commit>` and push. CI and the deploy run as normal (about 5 minutes), and the reverted code gets a fresh image.

**Backend, fast way (minutes after a bad deploy):** point traffic back at the previous revision. Cloud Run keeps every revision, but Artifact Registry keeps only the newest image (the image is 415 MB, free storage is 0.5 GiB, D38) and deletes replaced ones within about a day. So this works only shortly after the bad deploy:

```powershell
gcloud run revisions list --service desk-api --region us-central1 --project crypto-desk-513023
gcloud run services update-traffic desk-api --region us-central1 --project crypto-desk-513023 --to-revisions desk-api-00005-abc=100
```

The next successful deploy moves traffic to the newest revision again, so revert the bad commit too.

**Frontend:** Cloudflare dashboard → Workers & Pages → `crypto-desk` → Deployments → ⋯ on an older production deployment → "Rollback to this deployment". It takes effect instantly. Preview deployments can't be rollback targets.

**Database:** for a bad migration, `uv run alembic downgrade -1` from `backend/` (it needs the direct host: set `DATABASE_URL` to the URL without `-pooler`). For bad data, Neon can restore to any point in the last 6 hours (free plan history window) from the console (Branches → Restore). Anything older comes from the weekly backup ("Restore a backup" below).

## Read logs

```powershell
# API logs (newest first)
gcloud run services logs read desk-api --region us-central1 --project crypto-desk-513023 --limit 100

# Revisions and which one gets traffic
gcloud run services describe desk-api --region us-central1 --project crypto-desk-513023 --format "yaml(status.traffic)"
```

- Frontend deployments: Cloudflare dashboard → `crypto-desk` → Deployments, or `npx wrangler pages deployment list --project-name crypto-desk` (needs `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` in the environment).
- Deploy, daily-job and CI runs: GitHub → Actions.
- The `X-LLM-Key` header is stripped and redacted before anything logs (D37).

## Configuration

| Setting | Where it lives |
|---|---|
| `DATABASE_URL`, `CLERK_SECRET_KEY` (what the service reads) | Google Secret Manager: `database-url`, `clerk-secret-key` |
| The same values plus every job secret | GitHub Actions secrets (the deploy, daily and future jobs read these) |
| `ADMIN_CLERK_IDS` | GitHub repo **variable** (not a secret), JSON list, plus `.env` for local runs |
| `ANTHROPIC_API_KEY`, `LANGSMITH_API_KEY` (agent, Stage 5.1) | Secret Manager `anthropic-api-key`, `langsmith-api-key`; mounted only once they exist (D45) |
| `LANGSMITH_WORKSPACE_ID` | GitHub repo **variable** (a UUID, not a secret), plus `.env`; without it the service doesn't trace |
| CORS origins, Pages URL, Cloud Run sizing | `env:` blocks and flags in the two deploy workflows |
| CSP | `frontend/src/lib/security-headers.ts` |

**Set the admin ids (Stage 3.1):** in Invite-only mode, create the user in the Clerk Dashboard (Users → Create user) or invite the email first, sign in once, and copy the `user_…` id from the Dashboard. Then run `gh variable set ADMIN_CLERK_IDS --body '["user_..."]'`, add the same list to `.env`, and run "Deploy backend" by hand.

**Add the agent's secrets (Stage 5.1, [Rob]):** the admin's server-key chat needs the Anthropic key, and tracing needs the LangSmith key. Run each line from Claude Code with `!` (or Git Bash). The values come from `.env` and are never echoed; `tr` strips the newline that would otherwise be stored.

```
gcloud secrets create anthropic-api-key --project crypto-desk-513023 --replication-policy=automatic
gcloud secrets create langsmith-api-key --project crypto-desk-513023 --replication-policy=automatic
grep '^ANTHROPIC_API_KEY=' .env | cut -d= -f2- | sed 's/#.*//' | tr -d ' \t\r\n' | gcloud secrets versions add anthropic-api-key --project crypto-desk-513023 --data-file=-
grep '^LANGSMITH_API_KEY=' .env | cut -d= -f2- | sed 's/#.*//' | tr -d ' \t\r\n' | gcloud secrets versions add langsmith-api-key --project crypto-desk-513023 --data-file=-
for s in anthropic-api-key langsmith-api-key; do gcloud secrets add-iam-policy-binding $s --project crypto-desk-513023 --member=serviceAccount:desk-api@crypto-desk-513023.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor; gcloud secrets add-iam-policy-binding $s --project crypto-desk-513023 --member=serviceAccount:desk-deployer@crypto-desk-513023.iam.gserviceaccount.com --role=roles/secretmanager.viewer; done
gh variable set LANGSMITH_WORKSPACE_ID --body 84da3455-e2eb-4b0e-8a56-1870ec544c5e --repo robertsolomon002/crypto-desk
gh workflow run deploy-backend.yml --repo robertsolomon002/crypto-desk
```

The runtime account (`desk-api`) gets read access to the values. The deployer gets `secretmanager.viewer`, which shows only that a secret exists, so the deploy can decide what to mount. The deploy log lists any secret it skipped.

**Rotate a service secret** (for example after a Neon password reset):

1. Put the new value in `.env`.
2. Add a new version from `.env` (trim spaces and comments the same way as for `gh secret set`, see the next line).
3. Run `gcloud secrets versions add database-url --project crypto-desk-513023 --data-file=-`, with the value piped in.
4. Destroy the old version, since only 6 active versions are free: `gcloud secrets versions destroy 1 --secret database-url --project crypto-desk-513023`.
5. Update the GitHub secret too.
6. Redeploy ("Deploy backend" by hand), because instances read secrets when they start.

## MCO job (Stage 6.1, D48)

- **Schedule:** `.github/workflows/mco.yml`, daily at 06:30 UTC, or by hand: `gh workflow run mco.yml -f limit=1 -f alert=false`. Secrets: `DATABASE_URL`, `GOOGLE_API_KEY`, `YOUTUBE_API_KEY`, plus the alert secrets.
- **What it does:**
  - discovers new videos (RSS, falling back to the YouTube Data API);
  - summarizes up to 4 a day with Gemini (free tier, $0 in `llm_spend`);
  - sends `new_mco_summary` to Telegram and Discord.
- **No wave labels** (D49): extracts give a primary and an alternative scenario per coin. `mco/snap.py` is kept but unused.
- **Privacy:** the Actions log and the `ops_failure` alert carry only video ids, counts, model ids and error codes. Do not add steps that print extracts or upload artifacts.
- **Read results locally:** `uv run desk mco show --latest 2` prints the newest extracts (re-extracted videos show each version). It is local only and refuses to run in CI.
- **Re-run a video:** `uv run desk jobs mco --video <id> --no-alert`. A failed video is retried automatically on later runs, up to 3 attempts. `mco_videos.error` holds the last error code (for example `gemini-3.8-flash:fallback:503`).
- **Switch off:** `features.mco: false` in `config/settings.yaml`, or `MCO_ENABLED=false`. The job exits at once and every `/api/mco` route answers 404.

## Weekly signals and level watch (Stage 7.1, D51)

- **Weekly:** `.github/workflows/weekly.yml`, Monday 00:15 UTC, or by hand: `gh workflow run weekly.yml -f dry_run=true` (runs the desk and brief, costs about $0.10, writes nothing, no alerts). Secrets: `DATABASE_URL`, `FRED_API_KEY`, `COINGECKO_DEMO_KEY`, `ANTHROPIC_API_KEY`, plus the alert secrets.
- **What it does:** refreshes every source, resolves finished weeks into `signal_outcomes`, runs the desk per coin on the server key (core coins plus up to 3 watchlist coins; the watchlist is skipped from 80% of the $8 cap), adds the coin-flip, trend-rule and MCO rows, appends them hash-chained to `signals`, writes the brief (Sonnet 5.5; Haiku 5.5 from 80% of the cap) into `briefs`, and sends `brief_ready`. Then `desk signals verify` checks the chain.
- **Re-runs fill gaps only:** a coin and source that already have a row for the week keep it, and its desk run is not repeated; the brief is written once per week.
- **A failed run** (a source failed, a coin had no Sunday candle, a desk run errored or stayed invalid, the brief failed) exits 1 and sends `ops_failure`. Rows already written stay. Re-run it by hand.
- **Locally:** `uv run desk jobs weekly --dry-run --no-refresh --show-private` also prints the MCO rows and the brief (never in CI).
- **Level watch:** `.github/workflows/levelwatch.yml`, daily at 01:00 UTC, no LLM. One `level_cross` alert lists yesterday's crossings of this week's desk and MCO levels and of the key levels. A second run for the same day sends nothing (`-f force=true` to resend).
- **Privacy:** both logs hide MCO-derived rows and the brief text (Decision 6).
- **Never edit `signals`:** a trigger refuses UPDATE and DELETE. A change to the signal definition means a new `signals.version` in `config/settings.yaml`.

## Health page and the weekly summary (Stage 8.1, D53)

- **Health page:** https://crypto-desk-a9f.pages.dev/health (also linked from Settings → Usage and cost). Everyone sees the backend status. Admins also get:
  - a box at the top listing what needs a look;
  - **Jobs:** the last run, the last success, runs and failures over 7 days, and an **overdue** badge when no success came in time (daily, levelwatch and mco 26 h; weekly and backup 170 h; set in `ops.jobs` in `config/settings.yaml`);
  - **Data freshness** per source;
  - **Server-key LLM spend** against the $8 cap, with the month-end pace and which Decision 9 degradations are on;
  - **Errors** in the last 7 days;
  - **Free-tier usage:** database size against Neon's 1 GB, plus links to Cloud Run metrics, logs, Error Reporting, billing, Neon, the backups bucket and Actions.
  It refreshes every 5 minutes while open.
- **Weekly summary:** `.github/workflows/ops.yml`, Monday 07:00 UTC, sends the `ops_summary` alert to Telegram (Rob only). It has counts and dates only. Locally, `uv run desk ops health` prints the same text without sending it.
- **By hand:** `gh workflow run ops.yml` (backup, then summary); `gh workflow run ops.yml -f backup=false` (summary only).

## Backups (Stage 8.1, D53)

Neon Free keeps only 6 hours of restore history and one manual snapshot, so every Monday `ops.yml` dumps the tables nothing can rebuild, encrypts the dump and uploads it to a private bucket. Those tables are listed in `ops.backup.tables`: users, conversations, messages, agent snapshots, MCO videos and extracts, outside views, signals and outcomes, briefs, job runs, LLM spend and coins (the watchlist). Prices, series, news and the analytics cache are refetched by the daily job instead.

- File: `gs://crypto-desk-513023-backups/weekly/desk-YYYY-MM-DD-r<revision>.dump.gpg`. `<revision>` is the schema revision it was taken at.
- The workflow can only **create** objects. It can't read, overwrite or delete them, so old backups survive a bad run. Objects are deleted after 180 days.
- **The dump holds MCO-derived rows (Decision 6).** Never download it to a shared machine, attach it anywhere, or add a step that uploads it as an artifact.
- A failed backup sends `ops_failure` and shows on the Health page (the `backup` job).

### One-time setup [Rob]

Run these from Claude Code with `!` (Git Bash), from the repo root:

```bash
gcloud storage buckets create gs://crypto-desk-513023-backups --project crypto-desk-513023 --location us-central1 --default-storage-class STANDARD --uniform-bucket-level-access --public-access-prevention --lifecycle-file config/gcs-backup-lifecycle.json
gcloud storage buckets add-iam-policy-binding gs://crypto-desk-513023-backups --member=serviceAccount:desk-deployer@crypto-desk-513023.iam.gserviceaccount.com --role=roles/storage.objectCreator
echo "BACKUP_PASSPHRASE=$(openssl rand -base64 32)" >> .env
grep '^BACKUP_PASSPHRASE=' .env | cut -d= -f2- | tr -d ' \t\r\n' | gh secret set BACKUP_PASSPHRASE --repo robertsolomon002/crypto-desk
gh workflow run ops.yml --repo robertsolomon002/crypto-desk
```

Then **copy `BACKUP_PASSPHRASE` from `.env` into your password manager**. Without it the backups can't be opened: GitHub secrets can't be read back.

### Restore a backup

Restore into a **new Neon branch** (Neon console → Branches → Create branch, empty or from an old point), check it, then switch over. Never restore straight into `main`. You need `gpg` (Git Bash has it) and the Postgres 18 client (`pg_restore`). On Windows the simplest client is Docker's `postgres:18` image.

```bash
# 1. Download (needs your own gcloud login; the workflow can't read the bucket)
gcloud storage cp gs://crypto-desk-513023-backups/weekly/desk-2026-11-09-r0004.dump.gpg .
# 2. Decrypt (asks for BACKUP_PASSPHRASE)
gpg --output desk.dump --decrypt desk-2026-11-09-r0004.dump.gpg
# 3. Create the schema at the backup's revision on the new branch (direct host, no -pooler)
export DATABASE_URL='postgresql://...new-branch...'
(cd backend && uv run desk db upgrade 0004)
# 4. Load the data (pg_dump orders tables by their foreign keys; sequences come back too)
docker run --rm -v "$PWD:/w" postgres:18 pg_restore --data-only --no-owner --no-privileges --single-transaction --exit-on-error --dbname="$DATABASE_URL" /w/desk.dump
# 5. Bring the schema up to date, refill market data, then check the signals chain
(cd backend && uv run desk db upgrade && uv run desk jobs daily && uv run desk signals verify)
# 6. Delete the plain dump
rm desk.dump
```

To switch over, point `DATABASE_URL` at the new branch: in Secret Manager `database-url` (see "Rotate a service secret"), the GitHub secret and `.env`, then run "Deploy backend". This was tested end to end on local databases on 2026-11-04 (D53).

## Errors and logs (Stage 8.1, D53)

- On Cloud Run the API writes one JSON line per log record (`severity`, `message`, `logger`). Tracebacks stay inside `message`, so each error is one entry and shows up in **Error Reporting**: https://console.cloud.google.com/errors?project=crypto-desk-513023.
- Each unhandled API error also adds a row to `app_errors`, as does each agent or desk run that ends in an error. A row records where it happened and what kind of error, never the message. These rows are the counts on the Health page and in the weekly summary. Rows older than 90 days are pruned.
- To find the traceback for a count, open the Cloud Run logs at the time of `last_at`, filter by severity ERROR, and search for the route.
- No Sentry: see D53.

## Runbooks

### A job failed

You get `ops_failure` in Telegram and the Discord ops channel with the job's summary and the run link, and the job shows as failed (later overdue) on the Health page.

1. Open the run link (or Actions → the workflow → the failed run) and read the summary step. The `Problems:` lines say what failed.
2. If it's a source, see the next runbook.
3. If it was a one-off (a timeout, a 5xx), re-run it: `gh workflow run daily.yml` (or `mco.yml`, `weekly.yml`, `levelwatch.yml -f force=true`, `ops.yml`). Every job is safe to re-run. Daily re-fetches idempotently. Weekly fills gaps only and never duplicates a signal. MCO retries failed videos up to 3 times. The level watch sends nothing twice unless forced.
4. If it fails the same way twice, reproduce it locally: `cd backend; uv run desk jobs daily` (or `desk jobs weekly --dry-run --no-refresh`), which uses `.env`.
5. Weekly specifics: a missing Sunday candle means the daily job failed first, so fix that, then re-run weekly. "Invalid" desk runs were rejected twice by the validator. They are reported, never replaced, and the week's row for that coin stays missing.

### A source is broken

The daily summary says `<source> FAILED: …`, or Health → Data freshness shows it stale.

1. Check whether it's down or changed: run `uv run desk data update --<source>` locally (`--market`, `--onchain`, `--sentiment`, `--macro`, `--dominance`, `--news`). `uv run desk data status` shows the last date per coin and series.
2. If it is temporarily down (5xx, timeouts), do nothing: the next run catches up. Candles and series are filled for every missing day.
3. If the API changed (HTTP 4xx, a new field, a moved feed), check its docs, fix the client in `backend/src/desk/data/`, record what changed in `docs/DATA_SOURCES.md`, and add a test with a recorded fixture.
4. A key expired or was revoked (401/403): rotate it (next runbook).
5. Lags that are normal: Coin Metrics can be a day behind at 00:20 UTC (a note, not a failure); FRED publishes monthly with release lags (stale only after 62 days); ETH has no hash rate.
6. If Coinbase drops a coin, the coin goes stale. Deactivate it in Settings → Watchlist.

### Rotate a key

| Key | Where it lives | How |
|---|---|---|
| `DATABASE_URL` (Neon password reset) | Secret Manager `database-url`, GitHub secret, `.env` | "Rotate a service secret" above, then set the GitHub secret from `.env` |
| `CLERK_SECRET_KEY` | Secret Manager `clerk-secret-key`, GitHub secret, `.env` | Clerk Dashboard → API keys → create a new one, then the same steps; revoke the old key after the redeploy |
| `ANTHROPIC_API_KEY`, `LANGSMITH_API_KEY` | Secret Manager, GitHub secret (weekly job), `.env` | New key in the provider console, the same steps, then delete the old key in the console |
| `GOOGLE_API_KEY`, `YOUTUBE_API_KEY`, `FRED_API_KEY`, `COINGECKO_DEMO_KEY` | GitHub secrets, `.env` | New key in the provider console, then pipe it from `.env`: `grep '^NAME=' .env`, `cut -d= -f2-`, `tr -d ' \t\r\n'`, `gh secret set NAME` |
| `TELEGRAM_BOT_TOKEN` | GitHub secret, `.env` | @BotFather → `/revoke`, set the new token, then `gh workflow run daily.yml -f notify_test=true` |
| Discord webhooks | GitHub secrets, `.env` | Channel settings → Integrations → delete and recreate, set the new URL, then test as above |
| `BACKUP_PASSPHRASE` | GitHub secret, `.env`, password manager | Set a new one as in "One-time setup". **Keep the old one**: older backups still need it |
| Cloudflare token | GitHub secret `CLOUDFLARE_API_TOKEN` | Cloudflare → My Profile → API Tokens → roll, set the secret, then run "Deploy frontend" |

After any rotation, run the job that uses the key once by hand and check the Health page.

### A free-tier limit is hit

What to check first is on the Health page: Free-tier usage and the console links.

- **LLM cap ($8 server key):** from 80% the app degrades by itself (Decision 9). At 100% server-key chats and desk runs are refused (402) until the 1st of next month (UTC). The weekly signals job still runs: it is never skipped. To lower spend, look at Spend → by job. Raising the cap is Rob's call (`budget.server_llm_cap_usd_per_month`). Friends' own keys are unaffected.
- **Neon storage (1 GB):** see the largest tables on the Health page. `agent_snapshots` and `analytics_cache` grow fastest. The cache can be emptied (`TRUNCATE analytics_cache`; the daily job rebuilds it). Old snapshots go when their owners delete their conversations.
- **Neon compute (100 CU-hours a month):** the console shows usage. The database suspends after 5 idle minutes. Frequent jobs or a stuck client keep it awake, so check that no local process holds a connection open.
- **Cloud Run (2M requests, 180,000 vCPU-s, 360,000 GiB-s):** Cloud Run metrics. A spike means a loop in the frontend or abuse. Rate limits are 120 requests a minute per user and 30 agent messages an hour. Max instances is 2, so the cost is bounded.
- **GCP billing:** the $1 budget alert emails you. It does not cap spending, so check Billing → Reports for the service.
- **Gemini free tier:** the MCO job falls back to low detail and retries later; see the MCO job section.
- **GitHub Actions:** free on a public repo. If the repo ever goes private, scheduled jobs count against 2,000 minutes a month.

### Onboard a friend

1. Settings → Invite friends (admin): enter their email and send. Clerk emails an invitation link (the app is invite-only).
2. Send them `docs/FRIENDS_SETUP.md` (logging in, the tabs, and setting up an OpenRouter key with a spending limit).
3. After their first sign-in they appear in Settings → Users and roles as a `member`. Make someone admin only on purpose: admins use your server key.
4. They can use everything without a key except the Agent tab, which needs their own key (Settings → Your AI key and default model, with the "test key" button).
5. If they hit a problem, Health → Errors shows agent errors by code (`provider` usually means a key or credit problem on their side). Settings → Usage shows their message count.
6. To remove someone: revoke a pending invite in Settings, or delete the user in the Clerk Dashboard. Their conversations stay until deleted.

## Free-tier guard rails (Section 7)

- Cloud Run: max 2 instances, 1 vCPU / 512 MiB, request-based billing (CPU only while serving), min 0 instances.
- Artifact Registry: keeps only the newest image (415 MB; 0.5 GiB free). Replaced images are deleted once they are an hour old, by a cleanup job that runs about daily. Pushes that don't touch the API build no image.
- Secret Manager: 2 active versions (6 free). Destroy old versions when rotating.
- Cloudflare Pages: direct uploads; production plus a preview per PR.
- **[Rob] GCP budget alert at $1:** Billing → Budgets & alerts → Create budget, project `crypto-desk-513023`, amount $1, alerts at 50%, 90% and 100%. It only emails; it does not cap spending.

## One-time setup (done 2026-10-30, for reference)

Everything is in project `crypto-desk-513023`, region `us-central1`. Repeat these only to rebuild from scratch.

```bash
P=crypto-desk-513023; N=850576035365; R=us-central1
gcloud services enable iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com --project $P

# Image registry, keeping only the newest image (policy: Delete tagState any olderThan 1h;
# Keep mostRecentVersions keepCount 1)
gcloud artifacts repositories create desk --repository-format=docker --location=$R --project=$P
gcloud artifacts repositories set-cleanup-policies desk --project=$P --location=$R --policy=policy.json --no-dry-run

# Service accounts: runtime (desk-api) and deployer (desk-deployer, used by GitHub)
gcloud iam service-accounts create desk-api --project=$P
gcloud iam service-accounts create desk-deployer --project=$P
gcloud projects add-iam-policy-binding $P --member=serviceAccount:desk-deployer@$P.iam.gserviceaccount.com --role=roles/run.developer --condition=None
gcloud artifacts repositories add-iam-policy-binding desk --project=$P --location=$R --member=serviceAccount:desk-deployer@$P.iam.gserviceaccount.com --role=roles/artifactregistry.writer
gcloud iam service-accounts add-iam-policy-binding desk-api@$P.iam.gserviceaccount.com --project=$P --member=serviceAccount:desk-deployer@$P.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser

# Workload Identity Federation: only this repo (by numeric id) on main
gcloud iam workload-identity-pools create github --project=$P --location=global
gcloud iam workload-identity-pools providers create-oidc crypto-desk --project=$P --location=global --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository_id == '1437208542' && assertion.ref == 'refs/heads/main'"
gcloud iam service-accounts add-iam-policy-binding desk-deployer@$P.iam.gserviceaccount.com --project=$P --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$N/locations/global/workloadIdentityPools/github/attribute.repository_id/1437208542"

# Secrets the service reads (values piped from .env, never typed or pasted)
gcloud secrets create database-url --project=$P --replication-policy=automatic
gcloud secrets create clerk-secret-key --project=$P --replication-policy=automatic
gcloud secrets add-iam-policy-binding database-url --project=$P --member=serviceAccount:desk-api@$P.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding clerk-secret-key --project=$P --member=serviceAccount:desk-api@$P.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor

# The service itself, created once with a placeholder image and public access (needs run.admin,
# which CI does not have; CI deploys keep the setting)
gcloud run deploy desk-api --project=$P --region=$R --image=us-docker.pkg.dev/cloudrun/container/hello \
  --service-account=desk-api@$P.iam.gserviceaccount.com --no-invoker-iam-check --min-instances=0 --max-instances=2

# Cloudflare Pages project (--force: create classic Pages, see D38)
npx wrangler pages project create crypto-desk --production-branch main --force
```
