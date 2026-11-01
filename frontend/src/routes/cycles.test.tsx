import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { CyclesPage } from './cycles'

// ECharts needs a real canvas, so the charts are covered by Playwright; here a stand-in shows
// which chart the page drew.
vi.mock('@/components/charts/EChart', () => ({
  EChart: ({ label, testId }: { label: string; testId?: string }) => (
    <div data-testid={testId} aria-label={label} />
  ),
}))

const analytics = (result: unknown) =>
  envelope({ name: 'x', coin: 'BTC', params: {}, cached: false, result })

const path = (cycle: string, days: number, mode: string) =>
  Array.from({ length: days }, (_, day) => ({
    cycle,
    day,
    date: '2026-01-01',
    close: 100 + day,
    multiple: mode === 'top' ? 1 - day / 1000 : 1 + day / 100,
    drawdown: -day / 1000,
  }))

const dayRow = (cycle: string, reached: boolean) => ({
  cycle,
  anchor_date: '2024-04-20',
  anchor_price: 64968.87,
  day: reached ? 924 : 800,
  date: '2026-10-31',
  close: 77423.98,
  multiple: 1.19,
  drawdown: -0.379,
  max_multiple: 1.92,
  min_multiple: 0.8,
  top_day: 534,
  reached_day_n: reached,
})

function setup() {
  return stubApi({
    '/api/cycles/BTC/paths': analytics([
      ...path('2021', 30, 'halving'),
      ...path('2025', 10, 'halving'),
    ]),
    '/api/cycles/BTC/day-n': analytics({
      mode: 'halving',
      current_cycle: '2025',
      day: 924,
      table: [dayRow('2021', true), dayRow('2013', false), dayRow('2025', true)],
    }),
    '/api/cycles/BTC/roi': analytics([
      { cycle: '2021', bottom_date: '2018-12-15', bottom_price: 3236.76, d30: 0.2, d1440: 15 },
      { cycle: '2025', bottom_date: '2022-11-21', bottom_price: 15760.14, d30: 0.07, d1440: 3.91 },
    ]),
    '/api/cycles/BTC/yoy': analytics([
      { year: 2026, day: 1, date: '2026-01-01', close: 1, multiple: 1 },
    ]),
    '/api/cycles/SOL/paths': 404,
    '/api/cycles/SOL/day-n': 404,
    '/api/cycles/SOL/roi': 404,
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('CyclesPage', () => {
  it('draws the overlay and the day-N and ROI tables', async () => {
    setup()
    renderWithProviders(<CyclesPage />, { route: '/cycles?coin=BTC' })
    expect(await screen.findByTestId('cycle-overlay')).toBeInTheDocument()
    expect(await screen.findByTestId('cycle-now')).toHaveTextContent(
      'Today is day 924 after the Apr 20, 2024 halving: ×1.19 the anchor price, −37.9% from the cycle ATH.',
    )
    const dayN = screen.getByRole('table', { name: /day 924 after the halving/ })
    const rows = within(dayN).getAllByRole('row')
    expect(rows.map((r) => r.textContent?.slice(0, 6))).toEqual([
      'CycleA',
      '● 2013',
      '● 2021',
      '● 2025',
    ])
    expect(within(dayN).getByText('ended on day 800')).toBeInTheDocument()
    const roi = screen.getByRole('table', { name: 'Return since each cycle bottom' })
    expect(within(roi).getByText('Day 1440 (now)')).toBeInTheDocument()
    expect(within(roi).getByText('+391.0%')).toHaveAttribute('title', '×4.91')
  })

  it('keeps the anchor and y-axis modes in the URL and refetches by mode', async () => {
    const fetch = setup()
    renderWithProviders(<CyclesPage />, { route: '/cycles?coin=BTC' })
    await screen.findByTestId('cycle-overlay')
    await userEvent.click(screen.getByRole('button', { name: 'Bottom' }))
    await userEvent.click(screen.getByRole('button', { name: '% from ATH' }))
    expect(screen.getByTestId('location')).toHaveTextContent('anchor=bottom&y=drawdown')
    await waitFor(() =>
      expect(fetch.mock.calls.some(([r]) => (r as Request).url.includes('mode=bottom'))).toBe(true),
    )
    expect(screen.getByRole('heading', { name: /aligned by cycle bottom/ })).toBeInTheDocument()
  })

  it('switches to the year-over-year view', async () => {
    setup()
    renderWithProviders(<CyclesPage />, { route: '/cycles?coin=BTC' })
    await userEvent.click(await screen.findByRole('button', { name: 'Year over year' }))
    expect(await screen.findByTestId('yoy-overlay')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bottom' })).not.toBeInTheDocument()
  })

  it('links each chart to its analytics result in the Data tab', async () => {
    setup()
    renderWithProviders(<CyclesPage />, { route: '/cycles?coin=BTC&anchor=top' })
    await screen.findByTestId('cycle-overlay')
    const hrefs = screen
      .getAllByRole('link', { name: 'View data' })
      .map((a) => a.getAttribute('href'))
    expect(hrefs).toContain('/data?table=analytics&fn=cycles_paths&coin=BTC&mode=top')
    expect(hrefs).toContain('/data?table=analytics&fn=roi_since_bottom&coin=BTC')
  })

  it('says cycles cover BTC and ETH when the coin has none', async () => {
    setup()
    renderWithProviders(<CyclesPage />, { route: '/cycles?coin=SOL' })
    expect(
      await screen.findByText(/cover BTC and ETH: SOL has no complete cycle/),
    ).toBeInTheDocument()
  })
})
