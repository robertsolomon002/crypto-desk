import { expect, test } from '@playwright/test'

import { mockApi, ME } from './fixtures.ts'

// Runs at 1440 px (desktop) and 390 px (phone); see playwright.config.ts.

function isPhone(width: number | undefined) {
  return (width ?? 1440) < 768
}

test('the shell and Overview render from a mocked API', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await expect(page.getByTestId('coin-card-BTC')).toContainText('90,123.45')
  await expect(page.getByTestId('coin-card-BTC')).toContainText('+1.2%')
  await expect(page.getByTestId('coin-card-LINK')).toContainText('Watchlist')
  await expect(page.getByTestId('fng')).toContainText('Greed')
  await expect(page.getByTestId('macro-events')).toContainText('FOMC decision')
  await expect(page.getByTestId('headlines')).toContainText('Ether upgrade lands')
  await expect(page.getByTestId('freshness')).toContainText('(stale)')
  await expect(page.getByText('Not financial advice')).toBeVisible()
  await expect(page.getByText('Arrives with Signals (v1.3)').first()).toBeVisible()
})

test('headlines stay text and unsafe links are not links', async ({ page }) => {
  let dialogs = 0
  page.on('dialog', (dialog) => {
    dialogs += 1
    return dialog.dismiss()
  })
  await mockApi(page)
  await page.goto('/')
  const headlines = page.getByTestId('headlines')
  await expect(headlines).toContainText('<img src=x onerror=alert(1)>')
  await expect(headlines.locator('img')).toHaveCount(0)
  await expect(headlines.getByRole('link', { name: 'Ether upgrade lands' })).toHaveCount(0)
  expect(dialogs).toBe(0)
})

test('tabs navigate, keep the coin, and hide later versions', async ({ page, viewport }) => {
  await mockApi(page)
  await page.goto('/?coin=ETH')
  await expect(page.getByTestId('coin-card-ETH')).toHaveAttribute('aria-current', 'true')
  const tabs = page.getByRole('navigation', { name: 'Tabs' }).locator('visible=true')
  await expect(tabs.getByRole('link', { name: 'Agent' })).toHaveCount(0)
  await expect(tabs.getByRole('link', { name: 'Signals' })).toHaveCount(0)

  await tabs.getByRole('link', { name: 'Charts' }).click()
  await expect(page).toHaveURL(/\/charts\?coin=ETH$/)
  await expect(page.getByRole('toolbar', { name: 'Chart settings' })).toBeVisible()

  if (isPhone(viewport?.width)) {
    await tabs.getByRole('button', { name: 'More tabs' }).click()
    await page.getByRole('menuitem', { name: 'Settings' }).click()
  } else {
    await tabs.getByRole('link', { name: 'Settings' }).click()
  }
  await expect(page).toHaveURL(/\/settings\?coin=ETH$/)
  await expect(page.getByText('Coming in Stage 3.4')).toBeVisible()
})

test('feature flags from /api/me show later tabs', async ({ page, viewport }) => {
  test.skip(isPhone(viewport?.width), 'the desktop strip lists every tab')
  await mockApi(page, { '/api/me': { ...ME, features: { ...ME.features, agent: true } } })
  await page.goto('/')
  await expect(
    page.getByRole('navigation', { name: 'Tabs' }).getByRole('link', { name: 'Agent' }),
  ).toBeVisible()
})

test('the coin selector updates the URL', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('combobox', { name: 'Coin' }).selectOption('SOL')
  await expect(page).toHaveURL(/coin=SOL/)
  await expect(page.getByTestId('coin-card-SOL')).toHaveAttribute('aria-current', 'true')
})

test('View data links open the Data tab with the table', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByTestId('coin-card-BTC').getByRole('link', { name: 'View data' }).click()
  await expect(page).toHaveURL(/\/data\?table=candles_daily&coin=BTC$/)
  await expect(page.getByText('candles_daily')).toBeVisible()
})

test('follows the system theme until toggled, then persists', async ({ page }) => {
  await mockApi(page)
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/')
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.getByRole('button', { name: 'Switch to light theme' }).click()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await page.reload()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await page.evaluate(() => localStorage.clear())
  await page.emulateMedia({ colorScheme: 'light' })
  await page.reload()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
})

test('a slow first load explains the cold start', async ({ page }) => {
  await mockApi(page)
  // Every API call takes 3 s, like a Cloud Run cold start (registered last, so it runs first).
  await page.route('**/api/**', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 3000))
    await route.fallback()
  })
  await page.goto('/')
  await expect(page.getByRole('status')).toContainText('Waking up the server')
  await expect(page.getByTestId('coin-card-BTC')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByRole('status')).toHaveCount(0)
})

test('an API error shows a retry, not a broken page', async ({ page }) => {
  await mockApi(page)
  await page.route(/\/api\/news(\?|$)/, (route) => route.fulfill({ status: 500, json: {} }))
  await page.goto('/')
  await expect(page.getByTestId('coin-card-BTC')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible({ timeout: 10_000 })
})

test('no horizontal scroll', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await expect(page.getByTestId('coin-card-BTC')).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
})

test('the page is served with the production CSP and violates none of it', async ({ page }) => {
  const violations: string[] = []
  page.on('console', (message) => {
    if (/Content Security Policy/i.test(message.text())) violations.push(message.text())
  })
  await mockApi(page)
  const response = await page.goto('/')
  const csp = response?.headers()['content-security-policy'] ?? ''
  expect(csp).toContain("script-src 'self'")
  expect(csp).toContain("frame-ancestors 'none'")
  await expect(page.getByTestId('coin-card-BTC')).toBeVisible()
  expect(violations).toEqual([])
})

test('the health page still works', async ({ page }) => {
  await mockApi(page)
  await page.goto('/health')
  await expect(page.getByTestId('health-status')).toHaveText('ok')
})
