import { expect, test } from '@playwright/test'

test('home page shows backend health from a mocked API', async ({ page }) => {
  await page.route('**/api/health', (route) =>
    route.fulfill({
      json: { status: 'ok', version: '0.1.0', time_utc: '2026-10-28T00:00:00Z' },
    }),
  )
  await page.goto('/')
  await expect(page.getByTestId('health-status')).toHaveText('ok')
  await expect(page.getByText('Not financial advice')).toBeVisible()
})

test('the page is served with the production CSP and violates none of it', async ({ page }) => {
  const violations: string[] = []
  page.on('console', (message) => {
    if (/Content Security Policy/i.test(message.text())) violations.push(message.text())
  })
  await page.route('**/api/health', (route) =>
    route.fulfill({
      json: { status: 'ok', version: '0.1.0', time_utc: '2026-10-28T00:00:00Z' },
    }),
  )
  const response = await page.goto('/')
  const csp = response?.headers()['content-security-policy'] ?? ''
  expect(csp).toContain("script-src 'self'")
  expect(csp).toContain("frame-ancestors 'none'")
  await expect(page.getByTestId('health-status')).toHaveText('ok')
  expect(violations).toEqual([])
})
