import { expect, test, type Page } from '@playwright/test'

import { ME, mockApi } from './fixtures.ts'

// Data and Settings smoke tests at 1440 and 390 px.

const env = <T>(data: T) => ({ as_of: '2026-10-31', sources: [], data })
const col = (name: string, type: string) => ({ name, type, filterable: true })

const TABLES = env([
  {
    name: 'candles_daily',
    description: 'Closed daily candles',
    visibility: 'member',
    rows: 400,
    last_updated: '2026-10-31',
    columns: [
      col('coin', 'VARCHAR(16)'),
      col('date', 'DATE'),
      col('close', 'DOUBLE'),
      col('source', 'VARCHAR(32)'),
    ],
  },
  {
    name: 'series',
    description: 'Daily series: Fear & Greed, FRED, Coin Metrics, dominance',
    visibility: 'member',
    rows: 60000,
    last_updated: '2026-10-31',
    columns: [col('key', 'VARCHAR(64)'), col('date', 'DATE'), col('value', 'DOUBLE')],
  },
])

const DAYS = Array.from({ length: 400 }, (_, i) =>
  new Date(Date.UTC(2026, 9, 31) - i * 86_400_000).toISOString().slice(0, 10),
)
const CANDLES = DAYS.map((date, i) => ({
  coin: 'BTC',
  date,
  close: 70000 + Math.sin(i / 20) * 5000,
  source: 'coinbase',
}))

const MODELS = env([
  {
    id: 'openrouter',
    label: 'OpenRouter',
    recommended: true,
    default: 'anthropic/claude-haiku-5.5',
    choices: ['anthropic/claude-haiku-5.5'],
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    recommended: false,
    default: 'claude-haiku-5-5',
    choices: [],
  },
  { id: 'openai', label: 'OpenAI', recommended: false, default: null, choices: [] },
])

async function mock(page: Page, me = ME) {
  await mockApi(page, {
    '/api/me': me,
    '/api/data/tables': TABLES,
    '/api/agent/models': MODELS,
    '/api/admin/watchlist': [],
    '/api/admin/invites': [],
    '/api/admin/users': [
      { id: 1, clerk_id: 'user_e2e', role: 'admin', created_at: '2026-10-30T00:00:00Z' },
    ],
    '/api/admin/usage': {
      month: '2026-11',
      spend_usd: 0.12,
      cap_usd: 8,
      by_source: [],
      by_model: [],
      users: [],
      jobs: [],
    },
  })
  await page.route('**/api/data/tables/candles_daily**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/export.csv'))
      return route.fulfill({
        body: 'coin,date,close\nBTC,2026-10-31,77423.98\n',
        contentType: 'text/csv',
      })
    const size = Number(url.searchParams.get('page_size') ?? 100)
    const pageNo = Number(url.searchParams.get('page') ?? 1)
    const rows = CANDLES.slice((pageNo - 1) * size, pageNo * size)
    return route.fulfill({
      json: env({
        table: 'candles_daily',
        columns: ['coin', 'date', 'close', 'source'],
        total: CANDLES.length,
        page: pageNo,
        page_size: size,
        rows,
      }),
    })
  })
  await page.route('**/api/agent/test-key', (route) => {
    const ok = route.request().headers()['x-llm-key']?.startsWith('sk-or-') ?? false
    return route.fulfill({
      json: {
        ok,
        provider: 'openrouter',
        model: 'anthropic/claude-haiku-5.5',
        message: ok ? 'The key works: the provider answered.' : 'The key was rejected.',
      },
    })
  })
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
}

test('the Data tab lists tables and opens a View data link', async ({ page }) => {
  await mock(page)
  await page.goto('/data?coin=BTC')
  await expect(page.getByRole('link', { name: /candles_daily/ })).toContainText('400 rows')
  await page.goto('/data?table=candles_daily&coin=BTC&from=2026-01-01')
  await expect(page.getByTestId('data-grid')).toContainText('2026-10-31')
  await expect(page.getByTestId('pager-status')).toContainText('Rows 1–100 of 400')
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.getByTestId('pager-status')).toContainText('Rows 101–200 of 400')
  await noOverflow(page)
})

test('a column can be charted and the table exported as CSV', async ({ page }) => {
  await mock(page)
  await page.goto('/data?table=candles_daily&coin=BTC')
  await page.getByLabel('Chart a column').selectOption('close')
  await expect(page.getByTestId('data-preview').locator('canvas').first()).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export CSV' }).click()
  expect((await download).suggestedFilename()).toMatch(/^candles_daily_\d{8}\.csv$/)
})

test('Settings: a friend tests and saves an OpenRouter key', async ({ page }) => {
  const violations: string[] = []
  page.on('console', (m) => {
    if (/Content Security Policy/i.test(m.text())) violations.push(m.text())
  })
  await mock(page)
  await page.goto('/settings')
  await expect(page.getByRole('radio', { name: /OpenRouter/ })).toHaveAttribute(
    'aria-checked',
    'true',
  )
  await page.getByLabel('OpenRouter API key').fill('sk-or-v1-0123456789abcdef0123456789abcdef')
  await page.getByRole('button', { name: /Test key/ }).click()
  await expect(page.getByText('The key works: the provider answered.')).toBeVisible()
  await page.getByRole('button', { name: 'Save in this browser' }).click()
  await expect(page.getByTestId('saved-key')).toHaveText('sk-or-v1-…cdef')
  await page.reload()
  await expect(page.getByTestId('saved-key')).toHaveText('sk-or-v1-…cdef')
  await expect(page.getByRole('region', { name: /Watchlist/ })).toHaveCount(0)
  await noOverflow(page)
  expect(violations).toEqual([])
})

test('Settings: the admin sees watchlist, invites, users and usage', async ({ page }) => {
  await mock(page, { ...ME, role: 'admin' })
  await page.goto('/settings')
  for (const name of [/Watchlist/, /Invite friends/, /Users and roles/, /Usage and cost/])
    await expect(page.getByRole('region', { name })).toBeVisible()
  await expect(page.getByTestId('spend')).toHaveText('$0.12')
  await noOverflow(page)
})
