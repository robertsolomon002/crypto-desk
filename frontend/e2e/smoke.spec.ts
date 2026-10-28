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
