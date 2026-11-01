import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { StatsPage } from './stats'

vi.mock('@/components/charts/EChart', () => ({
  EChart: ({ label, testId }: { label: string; testId?: string }) => (
    <div data-testid={testId} aria-label={label} />
  ),
}))

const analytics = (result: unknown) =>
  envelope({ name: 'x', coin: 'BTC', params: {}, cached: false, result })
const summary = (n: number, key?: string) =>
  Array.from({ length: n }, (_, i) => ({
    ...(key ? { [key]: key === 'weekday' ? i : i + 1 } : {}),
    mean: 0.01 * (i - 3),
    median: 0.005,
    pct_positive: 0.5,
    count: 16,
  }))
const dist = (horizon: string) => ({
  horizon,
  count: 848,
  mean: 0.02,
  std: 0.13,
  quantiles: { p5: -0.155, p50: 0.008, p95: 0.223 },
  bins: [-0.2, -0.1, 0, 0.1, 0.2],
  counts: [10, 300, 400, 138],
  current_date: '2026-10-19',
  current: -0.0238,
  current_percentile: 29.2,
})

function setup() {
  return stubApi({
    // Monthly and day-of-week summaries without their period key, as older cached results are.
    '/api/stats/BTC/seasonality/monthly': analytics({
      matrix: [{ year: 2026, '1': 0.1, '2': -0.05 }],
      summary: summary(12),
    }),
    '/api/stats/BTC/seasonality/weekly': analytics({ matrix: [], summary: summary(53, 'week') }),
    '/api/stats/BTC/seasonality/dow': analytics({ matrix: [], summary: summary(7) }),
    '/api/stats/BTC/distribution': analytics(dist('1w')),
    '/api/stats/BTC/drawdowns': analytics([
      { date: '2026-10-30', close: 1, peak: 2, drawdown: -0.5 },
      { date: '2026-10-31', close: 1.5, peak: 2, drawdown: -0.25 },
    ]),
    '/api/stats/BTC/drawdown-episodes': analytics([
      {
        peak_date: '2025-10-06',
        peak: 124720.09,
        trough_date: '2026-02-05',
        trough: 62000,
        depth: -0.503,
        recovery_date: null,
        days: 390,
      },
    ]),
    '/api/stats/BTC/volatility': analytics([{ date: '2026-10-31', vol30: 0.4, vol90: 0.45 }]),
    '/api/stats/BTC/correlation': analytics([
      { date: '2026-10-31', 'BTC/ETH': 0.89, 'BTC/SOL': 0.84, 'ETH/SOL': 0.83 },
    ]),
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('StatsPage', () => {
  it('draws every Stats chart', async () => {
    setup()
    renderWithProviders(<StatsPage />, { route: '/stats?coin=BTC' })
    for (const id of [
      'monthly-heatmap',
      'weekly-seasonality',
      'dow-seasonality',
      'distribution',
      'drawdown-chart',
      'volatility-chart',
      'correlation-chart',
    ])
      expect(await screen.findByTestId(id)).toBeInTheDocument()
  })

  it('states the latest week and its percentile', async () => {
    setup()
    renderWithProviders(<StatsPage />, { route: '/stats?coin=BTC' })
    expect(await screen.findByTestId('distribution-current')).toHaveTextContent(
      'BTC returned −2.4% over the latest complete week (from Oct 19, 2026): the 29th percentile of 848 weeks.',
    )
  })

  it('labels month summaries even without a month key', async () => {
    setup()
    renderWithProviders(<StatsPage />, { route: '/stats?coin=BTC' })
    const table = await screen.findByRole('table', { name: 'Per-month summary across years' })
    const header = within(table)
      .getAllByRole('columnheader')
      .map((th) => th.textContent)
    expect(header.slice(1, 4)).toEqual(['Jan', 'Feb', 'Mar'])
    expect(within(table).getByRole('rowheader', { name: 'Mean' }).parentElement).toHaveTextContent(
      '−3.0%',
    )
  })

  it('shows the latest correlation matrix with the selected coin first', async () => {
    setup()
    renderWithProviders(<StatsPage />, { route: '/stats?coin=BTC' })
    const matrix = await screen.findByTestId('correlation-matrix')
    const rows = within(matrix)
      .getAllByRole('row')
      .map((r) => r.textContent)
    expect(rows).toEqual(['BTCETHSOL', 'BTC1.000.890.84', 'ETH0.891.000.83', 'SOL0.840.831.00'])
  })

  it('refetches the distribution for another horizon and keeps it in the URL', async () => {
    const fetch = setup()
    renderWithProviders(<StatsPage />, { route: '/stats?coin=BTC' })
    await screen.findByTestId('distribution')
    await userEvent.click(screen.getByRole('button', { name: '30D' }))
    expect(screen.getByTestId('location')).toHaveTextContent('horizon=30d')
    await waitFor(() =>
      expect(fetch.mock.calls.some(([r]) => (r as Request).url.includes('horizon=30d'))).toBe(true),
    )
  })

  it('lists the deepest drawdowns, open ones as not recovered yet', async () => {
    setup()
    renderWithProviders(<StatsPage />, { route: '/stats?coin=BTC' })
    expect(await screen.findByText('Deepest 1 drawdowns')).toBeInTheDocument()
    expect(screen.getByText('not yet')).toBeInTheDocument()
    expect(screen.getByText('−50.3%')).toBeInTheDocument()
  })
})
