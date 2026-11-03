# Crypto Desk: getting started

Crypto Desk is Rob's private crypto terminal: charts, cycle comparisons, seasonality and stats for
BTC, ETH, SOL and a small watchlist, built on free data. Every number can be checked in the Data
tab. **It is not financial advice:** no trading, no exchange keys, no orders.

## 1. Log in

1. Rob sends you an invitation email from Clerk (our sign-in service). Open the link in it.
2. Sign up with Google or with your email (the same address the invitation went to).
3. You land on the Overview. Next time, go to **https://crypto-desk-a9f.pages.dev** and sign in.

The first page load after a quiet spell can take a few seconds while the server wakes up. A
banner tells you when that's happening.

## 2. What the tabs do

| Tab | What you get |
|---|---|
| **Overview** | Price and 1/7/30-day change per coin, trend regime, distance from the all-time high, Fear & Greed, this week's FOMC and CPI dates, and headlines. |
| **Charts** | Candles (1D, 1W, 4H) with moving averages, the 20-week "bull market support band", Bollinger Bands, RSI, MACD, key levels and swing pivots. A ratio mode charts ETH/BTC, SOL/BTC and others. |
| **Cycles** | This BTC (or ETH) cycle against past ones, aligned by halving, cycle bottom or cycle top, plus a year-over-year view and returns since each bottom. |
| **Stats** | Monthly returns heatmap, week-of-year and day-of-week patterns, where this week's return sits in history, drawdowns, volatility and correlation between coins. |
| **On-chain & Macro** | MVRV, realized price, NUPL, active addresses and hash rate for BTC and ETH, Fear & Greed history, dominance, and four macro series you can overlay on BTC. |
| **Agent** | Ask questions in plain English ("Where is BTC in its cycle vs 2017?"). The agent looks the numbers up with the desk's own tools, shows each lookup as a card, and **View data** opens exactly what it saw. Up to 30 questions an hour. Answers can be wrong: check the data. |
| **Data** | Every table behind the app: filter, sort, chart a column, export CSV. Each chart's "View data" link opens its exact numbers here. |
| **Settings** | Theme, and your own AI key for the Agent tab (below). |

The coin selector at the top applies to every tab. View settings live in the page address, so
you can bookmark or share a view.

More tabs (MCO summaries, weekly Signals) arrive in later versions.

## 3. Your own AI key (for the Agent)

The Agent answers questions using the desk's data. It runs on **your own key**, so you pay the AI
provider directly, usually cents a month, and you set the limit. You can set it up now in
**Settings → Your AI key**.

We recommend **OpenRouter**: one key covers Claude, GPT, Gemini and more.

1. Sign up at **https://openrouter.ai/** (Google or email).
2. Add a little credit at **https://openrouter.ai/settings/credits**. $5 lasts most people months on
   the default model.
3. Create a key at **https://openrouter.ai/keys** and give it a **credit limit** (for example $5).
   Once the key has used its limit, OpenRouter refuses requests with it until you raise the
   limit, so it can never spend more than you allow.
4. Copy the key (it starts with `sk-or-`), paste it into Settings, press **Test key** (a single tiny
   request, a fraction of a cent), then **Save in this browser**.

Anthropic (Claude Console) and OpenAI keys work too. The wizard links to their key and spending
limit pages.

**Where your key goes:** it is saved only in this browser (so you set it up once per browser) and
is sent to the desk's server only with requests that need it. The server passes it to your
provider and never stores or logs it. **Forget key** in Settings removes it from the browser. If
you think a key leaked, delete it on the provider's site and create a new one.

## 4. Feedback

Tell Rob what's confusing, broken or missing: a short list is perfect. Screenshots help.
