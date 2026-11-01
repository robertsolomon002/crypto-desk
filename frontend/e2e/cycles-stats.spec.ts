import { expect, test, type Page } from '@playwright/test'

import { mockApi } from './fixtures.ts'

// Cycles and Stats smoke tests at 1440 and 390 px, on synthetic analytics results shaped like
// the API's (no real data in the repo).

const env = (result: unknown) => ({
  as_of: '2026-10-31',
  sources: [],
  data: { name: 'x', coin: 'BTC', params: {}, cached: false, result },
})

function rand(seed: number) {
  let s = seed
  return () => (s = (s * 1_103_515_245 + 12_345) % 2_147_483_648) / 2_147_483_648
}

const CYCLES = [
  ['2013', 1400],
  ['2017', 1420],
  ['2021', 1440],
  ['2025', 925],
] as const

function paths() {
  const r = rand(3)
  return CYCLES.flatMap(([cycle, days]) => {
    let multiple = 1
    let peak = 1
    return Array.from({ length: days }, (_, day) => {
      if (day) multiple *= Math.exp((r() - 0.495) * 0.06)
      peak = Math.max(peak, multiple)
      return {
        cycle,
        day,
        date: '2026-01-01',
        close: 100 * multiple,
        multiple,
        drawdown: multiple / peak - 1,
      }
    })
  })
}

const DAY_N = {
  mode: 'halving',
  current_cycle: '2025',
  day: 924,
  table: CYCLES.map(([cycle]) => ({
    cycle,
    anchor_date: '2024-04-20',
    anchor_price: 64968.87,
    day: 924,
    date: '2026-10-31',
    close: 77423.98,
    multiple: 1.19,
    drawdown: -0.379,
    max_multiple: 1.92,
    min_multiple: 0.8,
    top_day: 534,
    reached_day_n: true,
  })),
}

const ROI = CYCLES.map(([cycle], i) => ({
  cycle,
  bottom_date: '2022-11-21',
  bottom_price: 15760.14,
  d30: 0.07,
  d365: 1.27,
  d1440: i === 3 ? 3.91 : null,
}))

const YOY = [2024, 2025, 2026].flatMap((year) =>
  Array.from({ length: year === 2026 ? 304 : 365 }, (_, i) => ({
    year,
    day: i + 1,
    date: `${year}-01-01`,
    close: 1,
    multiple: 1 + Math.sin(i / 40) * 0.2,
  })),
)

const summary = (n: number, key: string) =>
  Array.from({ length: n }, (_, i) => ({
    [key]: key === 'weekday' ? i : i + 1,
    mean: Math.sin(i) * 0.05,
    median: Math.cos(i) * 0.03,
    pct_positive: 0.55,
    count: 16,
  }))

const MONTHLY = {
  matrix: Array.from({ length: 17 }, (_, y) => {
    const row: Record<string, number | null> = { year: 2010 + y }
    for (let m = 1; m <= 12; m++) row[m] = Math.sin(y * 12 + m) * 0.3
    return row
  }),
  summary: summary(12, 'month'),
}

const DATES = Array.from({ length: 1962 }, (_, i) =>
  new Date(Date.UTC(2021, 5, 18) + i * 86_400_000).toISOString().slice(0, 10),
)

const STATS: Record<string, unknown> = {
  'seasonality/monthly': MONTHLY,
  'seasonality/weekly': { matrix: [], summary: summary(53, 'week') },
  'seasonality/dow': { matrix: [], summary: summary(7, 'weekday') },
  distribution: {
    horizon: '1w',
    count: 848,
    mean: 0.02,
    std: 0.13,
    quantiles: { p5: -0.155, p50: 0.008, p95: 0.223 },
    bins: Array.from({ length: 41 }, (_, i) => -0.4 + i * 0.02),
    counts: Array.from({ length: 40 }, (_, i) =>
      Math.round(200 * Math.exp(-(((i - 20) / 5) ** 2))),
    ),
    current_date: '2026-10-19',
    current: -0.0238,
    current_percentile: 29.2,
  },
  drawdowns: DATES.map((date, i) => ({
    date,
    close: 1,
    peak: 1,
    drawdown: -Math.abs(Math.sin(i / 200)) * 0.8,
  })),
  'drawdown-episodes': [
    {
      peak_date: '2025-10-06',
      peak: 124720.09,
      trough_date: '2026-02-05',
      trough: 62000,
      depth: -0.503,
      recovery_date: null,
      days: 390,
    },
  ],
  volatility: DATES.map((date, i) => ({ date, vol30: 0.5 + Math.sin(i / 30) * 0.2, vol90: 0.5 })),
  correlation: DATES.map((date, i) => ({
    date,
    'BTC/ETH': 0.8 + Math.sin(i / 50) * 0.1,
    'BTC/SOL': 0.7,
    'ETH/SOL': 0.75,
  })),
}

const CYCLE_RESULTS: Record<string, unknown> = {
  paths: paths(),
  'day-n': DAY_N,
  roi: ROI,
  yoy: YOY,
}

async function mock(page: Page) {
  await mockApi(page)
  await page.route(/\/api\/(cycles|stats)\//, (route) => {
    const path = new URL(route.request().url()).pathname
    const m = /\/api\/(cycles|stats)\/(\w+)\/(.+)$/.exec(path)
    if (!m || m[2] !== 'BTC')
      return route.fulfill({ status: 404, json: { detail: 'not available' } })
    const body = (m[1] === 'cycles' ? CYCLE_RESULTS : STATS)[m[3]]
    return body === undefined
      ? route.fulfill({ status: 404, json: {} })
      : route.fulfill({ json: env(body) })
  })
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
}

function watchCsp(page: Page) {
  const violations: string[] = []
  page.on('console', (message) => {
    if (/Content Security Policy/i.test(message.text())) violations.push(message.text())
  })
  return violations
}

test('the Cycles tab draws the overlay and both tables', async ({ page }) => {
  const violations = watchCsp(page)
  await mock(page)
  const started = Date.now()
  await page.goto('/cycles?coin=BTC')
  await expect(page.getByTestId('cycle-overlay').locator('canvas').first()).toBeVisible()
  expect(Date.now() - started).toBeLessThan(5_000)
  await expect(page.getByTestId('cycle-now')).toContainText('Today is day 924')
  await expect(page.getByRole('table', { name: /day 924 after the halving/ })).toBeVisible()
  await expect(page.getByRole('table', { name: 'Return since each cycle bottom' })).toContainText(
    '+391.0%',
  )
  await noOverflow(page)
  expect(violations).toEqual([])
})

test('the cycle tooltip shows every cycle on the hovered day', async ({ page }) => {
  await mock(page)
  await page.goto('/cycles?coin=BTC')
  const chart = page.getByTestId('cycle-overlay')
  await expect(chart.locator('canvas').first()).toBeVisible()
  const box = await chart.boundingBox()
  if (!box) throw new Error('no chart box')
  await page.mouse.move(box.x + box.width * 0.4, box.y + box.height * 0.5)
  const title = page.getByText(/^Day \d+ after the halving$/)
  await expect(title).toBeVisible()
  for (const cycle of ['2013', '2017', '2021', '2025'])
    await expect(title.locator('..')).toContainText(cycle)
})

test('anchor, y-axis and view switches survive a reload', async ({ page }) => {
  await mock(page)
  await page.goto('/cycles?coin=BTC')
  await page.getByRole('button', { name: 'Bottom' }).click()
  await page.getByRole('button', { name: '% from ATH' }).click()
  await expect(page.getByRole('heading', { name: /aligned by cycle bottom/ })).toContainText(
    'below the cycle ATH',
  )
  await page.reload()
  await expect(page.getByRole('button', { name: 'Bottom' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Year over year' }).click()
  await expect(page.getByTestId('yoy-overlay').locator('canvas').first()).toBeVisible()
  await expect(page.getByRole('link', { name: 'View data' }).first()).toHaveAttribute(
    'href',
    '/data?table=analytics&fn=yoy&coin=BTC',
  )
})

test('a coin without cycles says so', async ({ page }) => {
  await mock(page)
  await page.goto('/cycles?coin=SOL')
  await expect(page.getByText(/SOL has no complete cycle/)).toBeVisible()
})

test('the Stats tab draws every chart', async ({ page }) => {
  const violations = watchCsp(page)
  await mock(page)
  const started = Date.now()
  await page.goto('/stats?coin=BTC')
  for (const id of [
    'monthly-heatmap',
    'weekly-seasonality',
    'dow-seasonality',
    'distribution',
    'drawdown-chart',
    'volatility-chart',
    'correlation-chart',
  ])
    await expect(page.getByTestId(id).locator('canvas').first()).toBeVisible()
  expect(Date.now() - started).toBeLessThan(5_000)
  await expect(page.getByTestId('distribution-current')).toContainText('29th percentile')
  await expect(page.getByTestId('correlation-matrix')).toContainText('0.70')
  await noOverflow(page)
  expect(violations).toEqual([])
})

test('Stats switches refetch and stay in the URL', async ({ page }) => {
  await mock(page)
  await page.goto('/stats?coin=BTC')
  await expect(page.getByTestId('distribution').locator('canvas').first()).toBeVisible()
  const refetch = page.waitForRequest(/distribution\?horizon=30d/)
  await page.getByRole('button', { name: '30D' }).click()
  await refetch
  await page.getByRole('button', { name: '1Y' }).click()
  await page.getByRole('button', { name: 'Median' }).click()
  await expect(page).toHaveURL(/horizon=30d/)
  await expect(page).toHaveURL(/range=1y/)
  await expect(page).toHaveURL(/stat=median/)
  await expect(
    page.locator('a[href="/data?table=analytics&fn=return_distribution&coin=BTC&horizon=30d"]'),
  ).toBeVisible()
})
