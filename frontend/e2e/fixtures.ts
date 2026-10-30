import type { Page } from '@playwright/test'

// Canned API responses for the smoke tests (shapes from the OpenAPI schema).

const src = [{ name: 'test', detail: null, url: null, last_date: '2026-10-29' }]

export const ME = {
  clerk_id: 'user_e2e',
  role: 'member',
  features: { onchain_macro: false, mco: false, agent: false, signals: false },
}

const coin = (symbol: string, name: string, close: number, is_watchlist = false) => ({
  symbol,
  name,
  is_watchlist,
  date: '2026-10-29',
  close,
  change_1d: 0.0123,
  change_7d: -0.045,
  change_30d: 0.1,
  ath: close * 1.4,
  ath_date: '2025-10-06',
  ath_distance: 1 / 1.4 - 1,
  regime: 'uptrend',
  signal: null,
  mco_bias: null,
})

export const OVERVIEW = {
  as_of: '2026-10-29',
  sources: src,
  data: {
    coins: [
      coin('BTC', 'Bitcoin', 90123.45),
      coin('ETH', 'Ethereum', 3210.5),
      coin('SOL', 'Solana', 181.2),
      coin('LINK', 'Chainlink', 14.3, true),
    ],
    freshness: [
      {
        source: 'Prices',
        table: 'candles_daily',
        last_date: '2026-10-29',
        max_age_days: 2,
        stale: false,
      },
      {
        source: 'Fear & Greed',
        table: 'series',
        last_date: '2026-10-29',
        max_age_days: 2,
        stale: false,
      },
      {
        source: 'Dominance',
        table: 'series',
        last_date: '2026-10-20',
        max_age_days: 2,
        stale: true,
      },
      {
        source: 'FRED macro',
        table: 'series',
        last_date: '2026-10-01',
        max_age_days: 62,
        stale: false,
      },
      {
        source: 'Headlines',
        table: 'news',
        last_date: '2026-10-29',
        max_age_days: 2,
        stale: false,
      },
    ],
    daily_job: {
      status: 'success',
      started_at: '2026-10-30T00:20:00Z',
      ended_at: '2026-10-30T00:20:11Z',
    },
  },
}

const COINS = {
  as_of: '2026-10-29',
  sources: src,
  data: OVERVIEW.data.coins.map((c) => ({
    symbol: c.symbol,
    name: c.name,
    is_watchlist: c.is_watchlist,
    first_date: '2015-07-20',
    last_date: c.date,
    last_close: c.close,
  })),
}

const FNG = {
  as_of: '2026-10-29',
  sources: src,
  data: Array.from({ length: 30 }, (_, i) => ({
    date: `2026-10-${String(i + 1).padStart(2, '0')}`,
    value: 40 + (i % 10),
  })).concat([{ date: '2026-10-31', value: 72 }]),
}

const CALENDAR = {
  as_of: '2026-10-30',
  sources: src,
  data: [
    {
      date: '2026-11-04',
      time_utc: '19:00:00',
      kind: 'fomc',
      title: 'FOMC decision',
      source_url: 'https://www.federalreserve.gov/',
    },
  ],
}

export const NEWS = {
  as_of: '2026-10-29',
  sources: src,
  data: [
    {
      source: 'CoinDesk',
      title: 'Bitcoin holds above $90K <img src=x onerror=alert(1)>',
      url: 'https://example.com/a',
      published_at: '2026-10-29T12:00:00Z',
      coins: ['BTC'],
    },
    {
      source: 'Decrypt',
      title: 'Ether upgrade lands',
      url: 'javascript:alert(1)',
      published_at: '2026-10-29T09:00:00Z',
      coins: ['ETH'],
    },
  ],
}

/** Answer every API call from the fixtures above; anything else is a 404. */
export async function mockApi(page: Page, overrides: Record<string, unknown> = {}) {
  const routes: Record<string, unknown> = {
    '/api/me': ME,
    '/api/coins': COINS,
    '/api/overview': OVERVIEW,
    '/api/macro/fng': FNG,
    '/api/calendar': CALENDAR,
    '/api/news': NEWS,
    '/api/health': { status: 'ok', version: '0.1.0', time_utc: '2026-10-28T00:00:00Z' },
    ...overrides,
  }
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    const body = routes[path]
    return body === undefined
      ? route.fulfill({ status: 404, json: { detail: 'not mocked' } })
      : route.fulfill({ json: body })
  })
}
