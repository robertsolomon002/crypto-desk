import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CandleChartProps } from '@/components/charts/CandleChart'
import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { ChartsPage } from './charts'

// Lightweight Charts needs a real canvas, so the chart itself is covered by Playwright; here a
// stand-in records the props the page hands it.
const chartProps = vi.hoisted(() => ({ last: null as CandleChartProps | null }))
vi.mock('@/components/charts/CandleChart', () => ({
  CandleChart: (props: CandleChartProps) => {
    chartProps.last = props
    return <div data-testid="candle-chart" data-bars={props.bars.length} data-mode={props.mode} />
  },
}))

const candles = (closes: number[]) =>
  closes.map((close, i) => ({
    time: new Date(Date.UTC(2026, 9, 1 + i)).toISOString(),
    open: close,
    high: close,
    low: close,
    close,
    volume: 10,
  }))

const ME = (mco: boolean) => ({
  clerk_id: 'user_test',
  role: 'member',
  features: { onchain_macro: false, mco, agent: false, signals: false },
})
const COINS = envelope(
  ['BTC', 'ETH', 'SOL'].map((symbol) => ({ symbol, name: symbol, is_watchlist: false })),
)
const analytics = (result: unknown) =>
  envelope({ name: 'x', coin: 'ETH', params: {}, cached: false, result })

function setup(mco = false) {
  return stubApi({
    '/api/me': ME(mco),
    '/api/coins': COINS,
    '/api/ohlcv/ETH': envelope(candles([10, 11, 12])),
    '/api/ohlcv/BTC': envelope(candles([100, 100, 100])),
    '/api/levels/ETH': analytics([{ name: 'ath', value: 20, date: '2025-08-24', distance: 0.6 }]),
  })
}

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('ChartsPage', () => {
  it('draws candles with levels and shows the last bar in the readout', async () => {
    setup()
    renderWithProviders(<ChartsPage />, { route: '/charts?coin=ETH' })
    await waitFor(() =>
      expect(screen.getByTestId('candle-chart')).toHaveAttribute('data-bars', '3'),
    )
    expect(screen.getByTestId('chart-readout')).toHaveTextContent('2026-10-03 UTC')
    expect(screen.getByTestId('chart-readout')).toHaveTextContent('C 12.00')
    await waitFor(() => expect(chartProps.last?.levels).toEqual([{ label: 'ATH', value: 20 }]))
    expect(screen.getByRole('heading', { name: /ETH \/ USD/ })).toBeInTheDocument()
  })

  it('switches timeframe through the API and remembers it per user', async () => {
    const fetch = setup()
    renderWithProviders(<ChartsPage />, { route: '/charts?coin=ETH' })
    await waitFor(() =>
      expect(screen.getByTestId('candle-chart')).toHaveAttribute('data-bars', '3'),
    )
    await userEvent.click(screen.getByRole('button', { name: '1W' }))
    await waitFor(() =>
      expect(fetch.mock.calls.some(([r]) => (r as Request).url.includes('tf=1w'))).toBe(true),
    )
    expect(JSON.parse(localStorage.getItem('desk.charts.v1.user_test') ?? '{}').tf).toBe('1w')
  })

  it('plots a ratio as a line without levels', async () => {
    setup()
    renderWithProviders(<ChartsPage />, { route: '/charts?coin=ETH' })
    await waitFor(() => expect(screen.getByRole('option', { name: 'ETH/BTC' })).toBeInTheDocument())
    await userEvent.selectOptions(screen.getByLabelText('Ratio denominator'), 'BTC')
    await waitFor(() =>
      expect(screen.getByTestId('candle-chart')).toHaveAttribute('data-mode', 'line'),
    )
    expect(chartProps.last?.bars.map((b) => b.close)).toEqual([0.1, 0.11, 0.12])
    expect(chartProps.last?.levels).toEqual([])
    expect(screen.getByRole('heading', { name: /ETH \/ BTC/ })).toBeInTheDocument()
  })

  it('shows MCO toggles only when the feature is on, and disabled until v1.2', async () => {
    setup(true)
    renderWithProviders(<ChartsPage />, { route: '/charts?coin=ETH' })
    await waitFor(() =>
      expect(screen.getByTestId('candle-chart')).toHaveAttribute('data-bars', '3'),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Overlays' }))
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('menuitemcheckbox', { name: 'MCO levels' })).toHaveAttribute(
      'data-disabled',
    )
  })

  it('offers a retry when candles fail to load', async () => {
    stubApi({ '/api/me': ME(false), '/api/coins': COINS, '/api/ohlcv/ETH': 500 })
    renderWithProviders(<ChartsPage />, { route: '/charts?coin=ETH' })
    expect(await screen.findByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
