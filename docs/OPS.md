# Operations

First version: Stage 2.2 (2026-10-30). Why it is set up this way: D38 in `DECISIONS.md`.

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

**Backend** (Cloud Run keeps every revision; Artifact Registry keeps the 3 newest images, so you can go back up to 3 deploys):

```powershell
gcloud run revisions list --service desk-api --region us-central1 --project crypto-desk-513023
gcloud run services update-traffic desk-api --region us-central1 --project crypto-desk-513023 --to-revisions desk-api-00005-abc=100
```

The next successful deploy moves traffic to the newest revision again. To stop that, revert the bad commit on `main`.

**Frontend:** Cloudflare dashboard → Workers & Pages → `crypto-desk` → Deployments → ⋯ on an older production deployment → "Rollback to this deployment". It takes effect instantly. Preview deployments can't be rollback targets.

**Database:** for a bad migration, `uv run alembic downgrade -1` from `backend/` (it needs the direct host: set `DATABASE_URL` to the URL without `-pooler`). For bad data, Neon can restore to any point in the last 6 hours (free plan history window) from the console (Branches → Restore).

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
| `ADMIN_CLERK_IDS` | GitHub repo **variable** (not a secret), JSON list; empty until Stage 3.1 |
| CORS origins, Pages URL, Cloud Run sizing | `env:` blocks and flags in the two deploy workflows |
| CSP | `frontend/src/lib/security-headers.ts` |

**Set the admin ids (Stage 3.1):** `gh variable set ADMIN_CLERK_IDS --body '["user_..."]'`, then run "Deploy backend" by hand.

**Rotate a service secret** (for example after a Neon password reset):

1. Put the new value in `.env`.
2. Add a new version from `.env` (trim spaces and comments the same way as for `gh secret set`, see the next line).
3. Run `gcloud secrets versions add database-url --project crypto-desk-513023 --data-file=-`, with the value piped in.
4. Destroy the old version, since only 6 active versions are free: `gcloud secrets versions destroy 1 --secret database-url --project crypto-desk-513023`.
5. Update the GitHub secret too.
6. Redeploy ("Deploy backend" by hand), because instances read secrets when they start.

## Free-tier guard rails (Section 7)

- Cloud Run: max 2 instances, 1 vCPU / 512 MiB, request-based billing (CPU only while serving), min 0 instances.
- Artifact Registry: keeps the 3 newest images and deletes older ones after a day (0.5 GiB free).
- Secret Manager: 2 active versions (6 free). Destroy old versions when rotating.
- Cloudflare Pages: direct uploads; production plus a preview per PR.
- **[Rob] GCP budget alert at $1:** Billing → Budgets & alerts → Create budget, project `crypto-desk-513023`, amount $1, alerts at 50%, 90% and 100%. It only emails; it does not cap spending.

## One-time setup (done 2026-10-30, for reference)

Everything is in project `crypto-desk-513023`, region `us-central1`. Repeat these only to rebuild from scratch.

```bash
P=crypto-desk-513023; N=850576035365; R=us-central1
gcloud services enable iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com --project $P

# Image registry, keeping the 3 newest images (policy file in D38's wording: delete any version older
# than 1d, keep mostRecentVersions 3)
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
