import { expect, test, type Page } from '@playwright/test'

import { ME, mockApi } from './fixtures.ts'

// On-chain & Macro smoke tests at 1440 and 390 px, on synthetic series shaped like the API's
// (no real data in the repo).

const DAYS = Array.from({ length: 3000 }, (_, i) =>
  new Date(Date.UTC(2018, 7, 1) + i * 86_400_000).toISOString().slice(0, 10),
)
const env = (data: unknown) => ({ as_of: '2026-10-17', sources: [], data })

const onchain = (coin: string) =>
  env({
    name: 'onchain',
    coin,
    params: {},
    cached: false,
    result: DAYS.map((date, i) => {
      const mvrv = 1.6 + Math.sin(i / 300) * 0.9
      return {
        date,
        mvrv,
        market_cap: 1e12,
        realized_cap: 1e12 / mvrv,
        realized_price: 20_000 + i * 10,
        nupl: 1 - 1 / mvrv,
        supply: 2e7,
        active_addresses: 800_000 + Math.sin(i / 7) * 80_000,
        hash_rate: coin === 'BTC' ? (2e8 + i * 3e5) * (1 + Math.sin(i) * 0.05) : null,
      }
    }),
  })

const candles = DAYS.map((d, i) => ({
  time: `${d}T00:00:00Z`,
  open: null,
  high: null,
  low: null,
  close: (20_000 + i * 10) * (1.6 + Math.sin(i / 300) * 0.9),
  volume: null,
}))

const MACRO = env({
  series: [
    { id: 'DTWEXBGS', label: 'Broad U.S. dollar index', units: 'index', release_lag_days: 8 },
    { id: 'DGS10', label: '10-year Treasury yield', units: 'percent', release_lag_days: 6 },
    { id: 'DFF', label: 'Effective federal funds rate', units: 'percent', release_lag_days: 6 },
    { id: 'M2SL', label: 'M2 money supply', units: 'billions USD', release_lag_days: 60 },
  ],
  rows: DAYS.map((date, i) => ({
    date,
    DTWEXBGS: 115 + Math.sin(i / 90) * 6,
    DGS10: 3 + Math.cos(i / 200),
    DFF: i < 1500 ? 0.08 : 4.33,
    M2SL: date.endsWith('-01') ? 14_000 + i * 2.5 : null,
  })),
})

async function mock(page: Page) {
  await mockApi(page, {
    '/api/me': { ...ME, features: { ...ME.features, onchain_macro: true } },
    '/api/onchain/BTC': onchain('BTC'),
    '/api/onchain/ETH': onchain('ETH'),
    '/api/ohlcv/BTC': env(candles),
    '/api/ohlcv/ETH': env(candles),
    '/api/macro': MACRO,
    '/api/macro/fng': env(
      DAYS.map((date, i) => ({ date, value: 50 + Math.round(Math.sin(i / 40) * 40) })),
    ),
    '/api/macro/dominance': env({
      rows: [
        { date: '2026-10-29', btc: 59.5, eth: 10.5 },
        { date: '2026-10-30', btc: 59.7, eth: 10.4 },
        { date: '2026-10-31', btc: 59.6, eth: 10.6 },
      ],
    }),
  })
}

function watchCsp(page: Page) {
  const violations: string[] = []
  page.on('console', (message) => {
    if (/Content Security Policy/i.test(message.text())) violations.push(message.text())
  })
  return violations
}

const CHARTS = [
  'mvrv-chart',
  'realized-chart',
  'nupl-chart',
  'addresses-chart',
  'hash-chart',
  'fng-chart',
  'dominance-chart',
  'macro-DTWEXBGS',
  'macro-DGS10',
  'macro-DFF',
  'macro-M2SL',
]

test('the On-chain & Macro tab draws every panel', async ({ page }) => {
  const violations = watchCsp(page)
  await mock(page)
  const started = Date.now()
  await page.goto('/onchain?coin=BTC')
  for (const id of CHARTS)
    await expect(page.getByTestId(id).locator('canvas').first()).toBeVisible()
  expect(Date.now() - started).toBeLessThan(5_000)
  await expect(page.getByTestId('nupl-readout')).toContainText(
    /Optimism|Belief|Hope|Euphoria|Capitulation/,
  )
  await expect(page.getByTestId('corr-DGS10')).toContainText('1Y r =')
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
  expect(violations).toEqual([])
})

test('the tab opens from the navigation and keeps the coin', async ({ page, viewport }) => {
  await mock(page)
  await page.goto('/?coin=ETH')
  const tabs = page.getByRole('navigation', { name: 'Tabs' }).locator('visible=true')
  if ((viewport?.width ?? 1440) < 768) {
    await tabs.getByRole('button', { name: 'More tabs' }).click()
    await page.getByRole('menuitem', { name: 'On-chain' }).click()
  } else {
    await tabs.getByRole('link', { name: 'On-chain & Macro' }).click()
  }
  await expect(page).toHaveURL(/\/onchain\?coin=ETH$/)
  await expect(page.getByRole('heading', { name: /ETH MVRV/ })).toBeVisible()
})

test('ETH hides its hash rate panel and says why', async ({ page }) => {
  await mock(page)
  await page.goto('/onchain?coin=ETH')
  await expect(page.getByTestId('panel-unavailable')).toContainText('proof of stake')
  await expect(page.getByTestId('hash-chart')).toHaveCount(0)
})

test('overlay and range switches stay in the URL', async ({ page }) => {
  await mock(page)
  await page.goto('/onchain?coin=BTC')
  const overlay = page.getByRole('button', { name: 'Overlay on BTC' }).first()
  await overlay.click()
  await page.getByRole('button', { name: '4Y' }).click()
  await expect(page).toHaveURL(/overlay=DTWEXBGS/)
  await expect(page).toHaveURL(/range=4y/)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Overlay on BTC' }).first()).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(page.getByTestId('macro-DTWEXBGS')).toHaveAttribute(
    'aria-label',
    /representing BTC price/, // ECharts aria describes each series
  )
})
