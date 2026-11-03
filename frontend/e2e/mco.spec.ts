import { expect, test, type Page } from '@playwright/test'

import { ME, mockApi } from './fixtures.ts'

// MCO tab smoke tests at 1440 and 390 px (Stage 6.2), on made-up videos (no MCO content in the
// repo, Decision 6). Thumbnails are served locally so the test never calls YouTube.

const env = (data: unknown) => ({ as_of: '2026-10-29', sources: [], data })
const DAYS = Array.from({ length: 120 }, (_, i) =>
  new Date(Date.UTC(2026, 6, 1) + i * 86_400_000).toISOString().slice(0, 10),
)
const candles = DAYS.map((d, i) => ({
  time: `${d}T00:00:00Z`,
  open: 100 + i,
  high: 102 + i,
  low: 99 + i,
  close: 101 + i + Math.sin(i / 5) * 4,
  volume: 10,
}))

const scenario = (name: 'primary' | 'alternative', bias: string, target: number) => ({
  name,
  color: null,
  bias,
  description: `A made-up ${name} scenario.`,
  levels: [{ price: target - 5, label: 'fib level' }],
  targets: [target],
  invalidation: name === 'primary' ? target + 40 : null,
  trigger: name === 'alternative' ? 'a break above the made-up line' : null,
})

const video = (n: number, day: string, coin: string, bias: string) => ({
  video_id: `fakeVideo0${n}`,
  title: `Made-up video ${n} about ${coin}`,
  url: `https://www.youtube.com/watch?v=fakeVideo0${n}`,
  published_at: `${day}T13:00:00Z`,
  low_detail: n === 3,
  model: 'gemini-3.5-flash-lite',
  prompt_version: 'mco_extract_v2',
  summary: `A made-up summary for video ${n}.`,
  checks: [],
  coins: [
    {
      coin,
      bias,
      wave_position: 'a made-up count',
      timeframe: 'days',
      key_levels: [{ price: 150, label: 'support box' }],
      scenarios: [scenario('primary', bias, 180), scenario('alternative', 'bullish', 240)],
      extraction_confidence: 'medium',
    },
  ],
})

const VIDEOS = [
  video(1, DAYS[110], 'BTC', 'bearish'),
  video(2, DAYS[100], 'ETH', 'bullish'),
  video(3, DAYS[90], 'BTC', 'neutral'),
]

async function mock(page: Page) {
  await page.route('https://i.ytimg.com/**', (route) =>
    route.fulfill({
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"/>',
    }),
  )
  await mockApi(page, {
    '/api/me': { ...ME, features: { ...ME.features, mco: true } },
    '/api/mco/videos': env(VIDEOS),
    '/api/ohlcv/BTC': env(candles),
    '/api/ohlcv/ETH': env(candles),
    '/api/levels/BTC': env({ name: 'levels', coin: 'BTC', params: {}, cached: false, result: [] }),
  })
}

function watchCsp(page: Page) {
  const violations: string[] = []
  page.on('console', (message) => {
    if (/Content Security Policy/i.test(message.text())) violations.push(message.text())
  })
  return violations
}

test('the MCO tab shows the notice, the timeline and the video cards', async ({ page }) => {
  const violations = watchCsp(page)
  await mock(page)
  const started = Date.now()
  await page.goto('/mco')
  await expect(page.getByRole('note').first()).toContainText('always check the video')
  await expect(page.getByTestId('mco-timeline').locator('canvas').first()).toBeVisible()
  await expect(page.getByLabel(/^Video: Made-up video/)).toHaveCount(3)
  expect(Date.now() - started).toBeLessThan(5_000)
  const first = page.getByLabel('Video: Made-up video 1 about BTC')
  await expect(first.getByText('Alternative', { exact: true })).toBeVisible()
  await expect(first.getByRole('link', { name: 'Made-up video 1 about BTC' })).toHaveAttribute(
    'href',
    'https://www.youtube.com/watch?v=fakeVideo01',
  )
  await expect(page.getByText('low detail: title and description only')).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
  expect(violations).toEqual([])
})

test('the coin filter keeps only that coin in the URL and the feed', async ({ page }) => {
  await mock(page)
  await page.goto('/mco')
  await page.getByRole('group', { name: 'Coin' }).getByRole('button', { name: 'ETH' }).click()
  await expect(page).toHaveURL(/mco_coin=ETH/)
  await expect(page.getByLabel(/^Video: Made-up video/)).toHaveCount(1)
  await expect(page.getByRole('heading', { name: 'MCO bias over ETH price' })).toBeVisible()
})

test('the tab opens from the navigation', async ({ page, viewport }) => {
  await mock(page)
  await page.goto('/')
  const tabs = page.getByRole('navigation', { name: 'Tabs' }).locator('visible=true')
  if ((viewport?.width ?? 1440) < 768) {
    await tabs.getByRole('button', { name: 'More tabs' }).click()
    await page.getByRole('menuitem', { name: 'MCO' }).click()
  } else {
    await tabs.getByRole('link', { name: 'MCO' }).click()
  }
  await expect(page).toHaveURL(/\/mco/)
  await expect(page.getByRole('heading', { name: 'MCO', exact: true })).toBeVisible()
})

test('the Charts tab offers the MCO scenario toggles', async ({ page }) => {
  await mock(page)
  await page.goto('/charts?coin=BTC')
  await expect(page.getByText(/MCO lines AI-extracted from the video of/)).toBeVisible()
  await page.getByRole('button', { name: 'Overlays' }).click()
  await expect(page.getByRole('menuitemcheckbox', { name: 'Primary scenario' })).toBeVisible()
  await expect(page.getByRole('menuitemcheckbox', { name: 'Alternative scenario' })).toBeVisible()
})
