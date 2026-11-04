# Public readiness

What must change before Crypto Desk opens beyond Rob's invited friends. Written in Stage 8.2 (2026-11-04); the reasoning is in `DECISIONS.md` (D54).

Today the app is invite-only (Clerk restricted mode, D29), runs on free tiers at $0, and has one admin and one test member. This page assumes "public" means **anyone can sign up for free**, and notes where charging money would change things.

This is an engineering checklist, not legal advice. The license and terms items need a lawyer's read before launch.

## 1. Must do before opening (blockers)

| # | Item | Why | Work |
|---|---|---|---|
| 1 | **MCO off** (Decision 6) unless More Crypto Online gives written permission | His summaries are his content; we only have them for private use | Set `features.mco: false` and `features.mco_tab: false` in `config/settings.yaml`, and `MCO_ENABLED=false` on Cloud Run and in the `mco.yml` and `weekly.yml` jobs. Already wired: every `/api/mco` route answers 404; `/api/views`, the scorecard, the Overview cards, the agent's `get_external_views` and the Data tab drop MCO rows. Briefs and desk debates of weeks with MCO input are held back (D52). Also: stop the `mco.yml` schedule, and decide whether to delete the private `mco_*` rows or keep them for Rob only |
| 2 | **Data licenses** (section 4) | Coin Metrics community data is CC BY-NC, and CoinGecko's Demo plan has no commercial license | Free and non-commercial: keep the attributions (done in Stage 8.2) and get a written OK from Coin Metrics or Talos for a public site. Charging: buy CoinGecko Basic ($35 a month) and a Coin Metrics license (price on request), or replace both sources |
| 3 | **Terms of use, privacy policy and disclaimer** | FRED's terms require a published privacy policy when an app collects user information. Users need the not-advice terms in writing | Write Terms (not financial advice, no warranty, acceptable use, account closure) and a Privacy Policy listing what is stored: Clerk account and email, conversations, agent snapshots, the role, and that LLM keys stay in the browser. Link both from the footer and the sign-up page |
| 4 | **Open sign-up with abuse limits** | Invite-only is the only gate today | Section 2 |
| 5 | **Data retention** | Agent snapshots grow by roughly 0.3 MB per active user a month (section 3) and Neon Free has 1 GB | Delete snapshots and conversations after 90 days (or keep them on request), and add a per-user "delete my data" control (deleting conversations exists already) |
| 6 | **Account deletion** | Privacy laws (and the privacy policy) promise it | Delete the user's rows when Clerk sends a `user.deleted` webhook, or from an admin action. Signals and briefs stay, since they aren't personal |
| 7 | **Cost alarms that can stop spend** | The $1 GCP budget alert only emails | Keep Cloud Run max instances as the hard ceiling; raise it only together with a budget. Add a Neon spending limit on a paid plan. The $8 server-key cap already refuses calls in code |

## 2. Open sign-up and abuse limits

- **Clerk:** switch from restricted (invite-only) mode to public sign-up, with email verification. Clerk's Hobby plan covers 50,000 monthly retained users per app (https://clerk.com/pricing, 2026-11-04), so cost doesn't change.
- **Rate limits that exist:**
  - 120 API requests a minute per user (in memory per instance, D37);
  - 30 agent questions an hour per user, counted in the database (row-locked since Stage 8.1, D53);
  - 5 desk runs an hour.
  For public use, also add:
  - a daily cap per user;
  - a limit per IP on unauthenticated routes (`/api/health`);
  - a sign-up limit per IP (Clerk or Cloudflare).
- **Server key:** only admins use it today. A public free tier on the server key (section 3) would need its own per-user monthly allowance, recorded in `llm_spend` per user, on top of the global $8 cap.
- **Exports:** CSV export streams whole tables. Cap rows per export for members, and count exports per hour.
- **Prompt injection and abuse through the agent:** tools are read-only, headlines and transcripts are wrapped as untrusted data, and output is rendered as sanitized text (Section 3.6). Public users bring more adversarial input, so add a few injection cases to the agent tests and log tool-call counts per user.
- **Cloud Run:** keep `max-instances` low (it bounds cost, and a flood gets 429s or queues), and consider Cloudflare in front of the API for bot filtering.
- **Admin surface:** keep `ADMIN_CLERK_IDS` to Rob. Every admin route is already tested for 403 on members (Section 9).

## 3. Costs at 100 and 1,000 users

The data jobs cost the same whatever the user count: prices, series and news are fetched once a day into the database, and users read from there. What grows is API traffic, database compute and storage, and any LLM use on Rob's key.

**What we measured (2026-11-04):**
- Cloud Run served 433 requests in 7 days for 1,281 billable instance-seconds (about 3 s per request, inflated by cold starts and streamed agent answers);
- the database is 28.5 MB;
- 47 agent snapshots take 208 kB (about 4.4 kB each);
- one agent answer with 2 tool calls cost $0.0029 on Haiku 5.5;
- a desk run cost $0.0072 (D47);
- the weekly job cost about $0.09 to $0.11 (D51, D53).

**Assumptions per active user a month:** 20 visits of about 40 API requests (800 requests), 30 agent questions on their own key, and the measured 3 instance-seconds per request with no overlap between users. That last part is an upper bound: requests from different users share an instance, up to 80 at a time.

**Prices** (checked 2026-11-04):
- **Cloud Run, request-based billing, us-central1** (Cloud Billing Catalog API): $0.000024 per vCPU-second, $0.0000025 per GiB-second, and $0.40 per million requests after 2 million free. The free tier covers 180,000 vCPU-seconds and 360,000 GiB-seconds a month.
- **Neon Launch** (https://neon.com/pricing): $0.106 per CU-hour and $0.35 per GB-month, with no minimum. Free is 100 CU-hours and 1 GB.
- **Clerk:** free to 50,000 monthly retained users.
- **CoinGecko Basic:** $35 a month for a commercial license.

| Item | 100 users | 1,000 users |
|---|---|---|
| Cloud Run (1 vCPU, 512 MiB) | 240,000 instance-s → about **$1.44** of CPU; memory and requests stay free | at most 2.4M instance-s → up to **about $55** (CPU $53.28, memory $2.10). Likely far less, since users overlap. Needs `max-instances` raised above 2 |
| Neon | Awake most of the day: about 120 CU-hours at 0.25 CU is over Free's 100, so Launch at **about $13** | Always on at 0.5 to 1 CU, 365 to 730 CU-hours, and 2 to 5 GB: **about $40 to $80** |
| Clerk, Cloudflare Pages, GitHub Actions, backups bucket | **$0** | **$0** |
| Data APIs | $0 if non-commercial (section 4) | $0 if non-commercial; **$35+** a month and a Coin Metrics license if commercial |
| Rob's server key (weekly desk and brief, his own chat) | about **$0.50 to $2** a month whatever the user count, capped at $8 | the same |
| Optional free agent allowance on Rob's key (10 questions per user a month at about $0.003) | about **$3** | about **$30**; the $8 cap would have to rise |
| **Total** | **about $15 a month** (plus about $3 with a free allowance) | **about $45 to $135 a month**, more with commercial data licenses and a free allowance |

Friends' and users' own-key LLM spend is not in the table: they pay their provider directly.

## 4. Data sources' terms (checked 2026-11-04)

| Source | Terms | What it means for a public app |
|---|---|---|
| **Coinbase** (prices through ccxt) | Public market data endpoints; we store daily closes | Read Coinbase's API terms for redistribution of derived data before launch (not yet checked) |
| **Coin Metrics community** (on-chain, BTC before 2015) | "Available to the community under the Creative Commons license", linked to CC BY-NC 4.0 (https://docs.coinmetrics.io/packages/coin-metrics-community-data) | Attribution required (shown on the On-chain section and in the footer). **Non-commercial only:** a paid tier needs a license from Coin Metrics (now part of Talos; datasupport@talostrading.com). Even a free public site should get a written OK |
| **CoinGecko** (dominance) | Demo plan: 10,000 calls a month, 100 a minute, attribution required, no commercial license; Basic is $35 a month with a commercial license (https://www.coingecko.com/en/api/pricing). The attribution guide asks for a linked credit such as "Data provided by CoinGecko" next to the data (https://brand.coingecko.com/resources/attribution-guide) | The linked credit was added under the dominance chart in Stage 8.2. Upgrade to Basic before charging |
| **FRED** (macro) | Apps must show "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis", link the Terms of Use and say users are bound by them, publish a privacy policy if collecting user information, not use FRED in the hostname, and not replicate FRED's experience. Series marked "Copyright" need their owner's permission beyond personal use (https://fred.stlouisfed.org/docs/api/terms_of_use.html) | The notice and link were added to the Macro section and footer in Stage 8.2. None of our four series (DTWEXBGS, DGS10, DFF, M2SL) has a copyright note (checked through the FRED API). Privacy policy: item 3 |
| **alternative.me** (Fear & Greed) | "Commercial use is allowed as long as the attribution is given right next to the display of the data"; no impersonation (https://alternative.me/crypto/fear-and-greed-index/) | Credit shown next to the Overview gauge and in the On-chain explainer. Fine as is |
| **RSS feeds** (CoinDesk, Cointelegraph, Decrypt, The Block) | We store and show titles and links only | Keep it that way. Check each publisher's feed terms before any commercial use |
| **YouTube and Gemini** (MCO) | Private use of free public videos | Off when public (item 1) |
| **TradingView Lightweight Charts** | Apache 2.0, with the NOTICE text and a link kept in the app | Done |

## 5. Users' LLM keys on the server (encrypted)

Today a user's key lives in their browser's `localStorage` and travels in `X-LLM-Key` on agent requests only (Decision 2). That's the simplest safe design, but the key has to be entered again on each device, and a script injected into the page (XSS) could read it. The CSP and text-only rendering make that unlikely.

If users want their key on the server:
- Store it encrypted per user: AES-GCM with a data key wrapped by a key-management service (envelope encryption). Google Cloud KMS is paid per key and operation, so check its pricing first. Never store a plain key, and never put one in a GitHub or Cloud Run variable.
- Decrypt only inside the agent request, keep it in memory as a `SecretStr`, and reuse the redaction middleware and the canary test. The test must also prove the key never reaches the database in plain form or the logs.
- Let users replace and delete it at any time. Show the last 4 characters only.
- Keep the browser-only option as the default.

## 6. A paid tier, if ever wanted

Charging changes the obligations more than the code:
- **Data first:** commercial licenses for CoinGecko (Basic, $35 a month) and Coin Metrics, or replacements. FRED, alternative.me (with attribution) and TradingView's chart library allow it.
- **Payments** through a provider such as Stripe (per-transaction fees), with plan limits enforced in the API next to the rate limits. Clerk can hold the plan on the user.
- **What a plan could add:** a server-key agent allowance (so users don't need their own key), more watchlist coins, per-user watchlists, and alerts to the user's own Telegram.
- **Taxes, refunds and a support channel**, which the current setup doesn't have.
- **No trading, no exchange keys, not financial advice:** these stay whatever the plan. Selling signals as advice would bring financial-regulation questions; the scorecard and brief are presented as research.

## 7. Already in place

- Invite-only auth with roles stored in the database; tests cover every role on every route.
- A strict CSP, keys stripped and redacted before anything logs, and a canary test for keys.
- Sanitized text rendering for headlines, summaries and model output.
- Parameterized SQL, and untrusted text kept out of workflow `run:` lines.
- Append-only, hash-chained signals.
- Health page, weekly ops summary, structured logs with error counts, encrypted weekly backups and runbooks (Stage 8.1).
- The $8 server-key cap with degradation steps, Cloud Run max 2 instances, and per-user limits.
