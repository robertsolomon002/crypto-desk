import { expect, test, type Page } from '@playwright/test'

import { DEBATE, HISTORY, SCORECARD, WEEK, WEEKS } from '../src/lib/__fixtures__/signals.ts'
import { ME, mockApi } from './fixtures.ts'

// Signals tab smoke tests at 1440 and 390 px (Stage 7.2), on made-up signals.

const env = (data: unknown) => ({ as_of: '2026-10-25', sources: [], data })

async function mock(page: Page) {
  await mockApi(page, {
    '/api/me': { ...ME, features: { ...ME.features, signals: true } },
    '/api/signals/week': env(WEEK),
    '/api/signals/weeks': env(WEEKS),
    '/api/signals/scorecard': env(SCORECARD),
    '/api/signals/history': env(HISTORY),
    [`/api/signals/${WEEK.signals[0].id}/debate`]: env(DEBATE),
  })
}

function watchCsp(page: Page) {
  const violations: string[] = []
  page.on('console', (message) => {
    if (/Content Security Policy/i.test(message.text())) violations.push(message.text())
  })
  return violations
}

test('the Signals tab shows the brief, signals, scorecard and history', async ({ page }) => {
  const violations = watchCsp(page)
  await mock(page)
  const started = Date.now()
  await page.goto('/signals')
  await expect(page.getByRole('heading', { name: 'Signals', exact: true })).toBeVisible()
  await expect(page.getByText('Summary line one <b>not bold</b>')).toBeVisible()
  await expect(page.getByRole('table', { name: 'Signals by coin and source' })).toBeVisible()
  await expect(page.getByTestId('signals-cumulative').locator('canvas').first()).toBeVisible()
  await expect(page.getByRole('table', { name: 'Signal history' })).toBeVisible()
  expect(Date.now() - started).toBeLessThan(5_000)
  await expect(page.getByText(/Not financial advice/).first()).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
  expect(violations).toEqual([])
})

test('a desk debate opens with the reports and the debate', async ({ page }) => {
  await mock(page)
  await page.goto('/signals')
  await page.getByText(/desk debate · lean long 60%/).click()
  await expect(page.getByText('Made-up bull point')).toBeVisible()
  await expect(page.getByText('Made-up technical report')).toBeVisible()
})

test('the tab opens from the navigation', async ({ page, viewport }) => {
  await mock(page)
  await page.goto('/')
  const tabs = page.getByRole('navigation', { name: 'Tabs' }).locator('visible=true')
  if ((viewport?.width ?? 1440) < 768) {
    await tabs.getByRole('button', { name: 'More tabs' }).click()
    await page.getByRole('menuitem', { name: 'Signals' }).click()
  } else {
    await tabs.getByRole('link', { name: 'Signals' }).click()
  }
  await expect(page).toHaveURL(/\/signals/)
  await expect(page.getByRole('heading', { name: 'Signals', exact: true })).toBeVisible()
})
