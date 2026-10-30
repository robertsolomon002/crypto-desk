import { expect, test, type Page } from '@playwright/test'

import { mockApi } from './fixtures.ts'

// Charts tab smoke tests at 1440 and 390 px, on a synthetic full-length BTC history (close-only
// before 2015-07-20 like the Coin Metrics backfill) so rendering is exercised at real size.

const DAY = 86_400_000

function walk(seed: number, start: string, end: string, closeOnlyUntil?: string) {
  let s = seed
  const rand = () => (s = (s * 1_103_515_245 + 12_345) % 2_147_483_648) / 2_147_483_648
  const out = []
  let close = 0.06
  const stop = Date.parse(`${end}T00:00:00Z`)
  const full = closeOnlyUntil ? Date.parse(`${closeOnlyUntil}T00:00:00Z`) : 0
  for (let t = Date.parse(`${start}T00:00:00Z`); t <= stop; t += DAY) {
    const open = close
    close = Math.max(0.01, close * Math.exp((rand() - 0.49) * 0.07))
    const ohlc = t >= full
    out.push({
      time: new Date(t).toISOString().replace('.000Z', 'Z'),
      open: ohlc ? open : null,
      high: ohlc ? Math.max(open, close) * (1 + rand() * 0.02) : null,
      low: ohlc ? Math.min(open, close) * (1 - rand() * 0.02) : null,
      close,
      volume: ohlc ? 1000 + rand() * 500 : null,
    })
  }
  return out
}

function weekly(daily: ReturnType<typeof walk>) {
  const weeks = new Map<string, (typeof daily)[number]>()
  for (const d of daily) {
    const t = Date.parse(d.time)
    const monday = new Date(t - ((new Date(t).getUTCDay() + 6) % 7) * DAY).toISOString()
    const key = monday.replace('.000Z', 'Z')
    const w = weeks.get(key)
    if (!w) weeks.set(key, { ...d, time: key })
    else {
      w.close = d.close
      w.high = Math.max(w.high ?? d.close, d.high ?? d.close)
      w.low = Math.min(w.low ?? d.close, d.low ?? d.close)
      w.volume = (w.volume ?? 0) + (d.volume ?? 0)
    }
  }
  return [...weeks.values()]
}

const BTC = walk(7, '2010-07-18', '2026-10-29', '2015-07-20')
const ETH = walk(11, '2016-05-18', '2026-10-29')
const env = <T>(data: T) => ({ as_of: '2026-10-29', sources: [], data })
const analytics = (name: string, result: unknown) =>
  env({ name, coin: 'BTC', params: {}, cached: false, result })

const last = BTC[BTC.length - 1].close
const LEVELS = analytics('levels', [
  {
    name: 'ath',
    value: Math.max(...BTC.map((b) => b.high ?? b.close)),
    date: '2025-10-06',
    distance: -0.3,
  },
  { name: 'sma200d', value: last * 0.9, date: null, distance: -0.1 },
])
const PIVOTS = analytics('pivots', [
  { kind: 'low', date: '2026-08-01', price: 1, confirmed: true, confirmed_on: '2026-08-10' },
  { kind: 'high', date: '2026-09-15', price: 2, confirmed: false, confirmed_on: null },
])

async function mockCharts(page: Page) {
  await mockApi(page, { '/api/levels/BTC': LEVELS, '/api/pivots/BTC': PIVOTS })
  await page.route(/\/api\/ohlcv\/(BTC|ETH)/, (route) => {
    const url = new URL(route.request().url())
    const daily = url.pathname.endsWith('/BTC') ? BTC : ETH
    const tf = url.searchParams.get('tf') ?? '1d'
    const data = tf === '1w' ? weekly(daily) : tf === '4h' ? [] : daily
    return route.fulfill({ json: env(data) })
  })
}

async function chartReady(page: Page) {
  await expect(page.getByTestId('candle-chart').locator('canvas').first()).toBeVisible()
  await expect(page.getByTestId('chart-readout')).toContainText('2026-10-29 UTC')
}

test('the chart renders the full BTC history with the default indicators', async ({ page }) => {
  await mockCharts(page)
  const started = Date.now()
  await page.goto('/charts?coin=BTC')
  await chartReady(page)
  expect(Date.now() - started).toBeLessThan(5_000)
  const readout = page.getByTestId('chart-readout')
  await expect(readout).toContainText('SMA 200')
  await expect(readout).toContainText('20W SMA')
  await expect(readout).toContainText('RSI 14')
  await expect(page.getByRole('heading', { name: /BTC \/ USD/ })).toContainText('Daily')
  // The license requires the TradingView attribution; the chart's logo links to it.
  await expect(page.locator('a[href*="tradingview.com"]')).toHaveCount(2) // chart logo + footer
})

test('the crosshair readout follows the pointer', async ({ page }) => {
  await mockCharts(page)
  await page.goto('/charts?coin=BTC')
  await chartReady(page)
  const box = await page.getByTestId('candle-chart').boundingBox()
  if (!box) throw new Error('no chart box')
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.3)
  await expect(page.getByTestId('chart-readout')).not.toContainText('2026-10-29 UTC')
})

test('timeframe, scale, panes and settings survive a reload', async ({ page }) => {
  await mockCharts(page)
  await page.goto('/charts?coin=BTC')
  await chartReady(page)
  await page.getByRole('button', { name: '1W' }).click()
  await page.getByRole('button', { name: 'Linear' }).click()
  await page.getByRole('button', { name: 'Indicators' }).click()
  await page.getByRole('menuitemcheckbox', { name: 'MACD (12, 26, 9)' }).click()
  await page.getByRole('menuitemcheckbox', { name: 'RSI (14)' }).click()
  await page.keyboard.press('Escape')
  const heading = page.getByRole('heading', { name: /BTC \/ USD/ })
  await expect(heading).toContainText('Weekly')
  await expect(heading).toContainText('linear')
  await expect(page.getByTestId('chart-readout')).toContainText('MACD')
  await expect(page.getByTestId('chart-readout')).not.toContainText('RSI 14')
  await page.reload()
  await expect(page.getByRole('heading', { name: /BTC \/ USD/ })).toContainText('Weekly')
  await expect(page.getByRole('button', { name: 'Linear' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('chart-readout')).toContainText('MACD')
})

test('ratio mode plots ETH/BTC as a close-only line', async ({ page }) => {
  await mockCharts(page)
  await page.goto('/charts?coin=ETH')
  await page.getByLabel('Ratio denominator').selectOption('BTC')
  await expect(page.getByRole('heading', { name: /ETH \/ BTC/ })).toContainText('ratio')
  await expect(page.getByTestId('chart-readout')).toContainText('2026-10-29 UTC')
  await expect(page.getByTestId('chart-readout')).not.toContainText('O ')
  await expect(page.getByRole('link', { name: 'View data (BTC)' })).toBeVisible()
})

test('an empty timeframe says so instead of drawing nothing', async ({ page }) => {
  await mockCharts(page)
  await page.goto('/charts?coin=BTC')
  await chartReady(page)
  await page.getByRole('button', { name: '4H' }).click()
  await expect(page.getByText('No bars for this selection.')).toBeVisible()
})

test('View data links to the candles for the visible range', async ({ page }) => {
  await mockCharts(page)
  await page.goto('/charts?coin=BTC')
  await chartReady(page)
  const link = page.getByRole('link', { name: 'View data' })
  await expect(link).toHaveAttribute(
    'href',
    /table=candles_daily&coin=BTC&from=\d{4}-\d\d-\d\d&to=/,
  )
})

test('MCO toggles stay hidden until v1.2', async ({ page }) => {
  await mockCharts(page)
  await page.goto('/charts?coin=BTC')
  await page.getByRole('button', { name: 'Overlays' }).click()
  await expect(page.getByRole('menuitemcheckbox', { name: 'Key levels' })).toBeVisible()
  await expect(page.getByText('MCO levels')).toHaveCount(0)
})

test('no horizontal scroll and no CSP violations on the Charts tab', async ({ page }) => {
  const violations: string[] = []
  page.on('console', (message) => {
    if (/Content Security Policy/i.test(message.text())) violations.push(message.text())
  })
  await mockCharts(page)
  await page.goto('/charts?coin=BTC')
  await chartReady(page)
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
  expect(violations).toEqual([])
})
