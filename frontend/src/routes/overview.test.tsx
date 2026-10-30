import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { OverviewPage } from './overview'

const card = (symbol: string, close: number, extra = {}) => ({
  symbol,
  name: symbol === 'BTC' ? 'Bitcoin' : 'Ethereum',
  is_watchlist: false,
  date: '2026-10-29',
  close,
  change_1d: 0.0123,
  change_7d: -0.045,
  change_30d: null,
  ath: 126198.07,
  ath_date: '2025-10-06',
  ath_distance: -0.2857,
  regime: 'downtrend',
  signal: null,
  mco_bias: null,
  ...extra,
})

const OVERVIEW = envelope({
  coins: [card('BTC', 90123.45), card('ETH', 3210.5)],
  freshness: [
    {
      source: 'Prices',
      table: 'candles_daily',
      last_date: '2026-10-29',
      max_age_days: 2,
      stale: false,
    },
    { source: 'Dominance', table: 'series', last_date: '2026-10-01', max_age_days: 2, stale: true },
  ],
  daily_job: { status: 'failed', started_at: '2026-10-30T00:20:00Z', ended_at: null },
})

const API = {
  '/api/overview': OVERVIEW,
  '/api/macro/fng': envelope([
    { date: '2026-10-28', value: 20 },
    { date: '2026-10-29', value: 50 },
  ]),
  '/api/calendar': envelope([]),
  '/api/news': envelope([
    {
      source: 'CoinDesk',
      title: '<script>alert(1)</script> Bitcoin rallies',
      url: 'javascript:alert(1)',
      published_at: '2026-10-29T12:00:00Z',
      coins: ['BTC'],
    },
    {
      source: 'Decrypt',
      title: 'Ether upgrade lands',
      url: 'https://example.com/eth',
      published_at: '2026-10-29T09:00:00Z',
      coins: [],
    },
  ]),
}

describe('OverviewPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders coin cards with signed changes and placeholders', async () => {
    stubApi(API)
    renderWithProviders(<OverviewPage />, { route: '/?coin=ETH' })
    const btc = await screen.findByTestId('coin-card-BTC')
    expect(btc).toHaveTextContent('$90,123.45')
    expect(btc).toHaveTextContent('▲+1.2%')
    expect(btc).toHaveTextContent('▼−4.5%')
    expect(btc).toHaveTextContent('30d—')
    expect(btc).toHaveTextContent('−28.6% ($126,198.07, Oct 6, 2025)')
    expect(btc).toHaveTextContent('Downtrend')
    expect(btc).toHaveTextContent('Arrives with Signals (v1.3)')
    expect(screen.getByTestId('coin-card-ETH')).toHaveAttribute('aria-current', 'true')
    expect(within(btc).getByRole('link', { name: 'View data' })).toHaveAttribute(
      'href',
      '/data?table=candles_daily&coin=BTC',
    )
    await userEvent.click(within(btc).getByRole('button', { name: 'Select Bitcoin' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/?coin=BTC')
  })

  it('flags stale sources and a failed daily job', async () => {
    stubApi(API)
    renderWithProviders(<OverviewPage />)
    const strip = await screen.findByTestId('freshness')
    expect(strip).toHaveTextContent('Dominance')
    expect(strip).toHaveTextContent('(stale)')
    expect(strip).toHaveTextContent('Daily job failed')
  })

  it('renders headlines as text and links only http(s) URLs', async () => {
    stubApi(API)
    renderWithProviders(<OverviewPage />)
    const list = await screen.findByTestId('headlines')
    expect(await within(list).findByText(/Bitcoin rallies/)).toHaveTextContent(
      '<script>alert(1)</script> Bitcoin rallies',
    )
    expect(list.querySelector('script')).toBeNull()
    const links = within(list).getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', 'https://example.com/eth')
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('shows Fear & Greed with its band and an empty macro week', async () => {
    stubApi(API)
    renderWithProviders(<OverviewPage />)
    const fng = await screen.findByTestId('fng')
    expect(fng).toHaveTextContent('50')
    expect(fng).toHaveTextContent('Neutral')
    expect(await screen.findByText('No FOMC or CPI events in the next 7 days.')).toBeInTheDocument()
  })

  it('shows a retry when a card fails, and recovers', async () => {
    const fetch = stubApi({ ...API, '/api/news': 500 })
    renderWithProviders(<OverviewPage />)
    await userEvent.click(await screen.findByRole('button', { name: 'Retry' }))
    expect(fetch.mock.calls.filter(([r]) => r.url.includes('/api/news'))).toHaveLength(2)
    expect(screen.getByTestId('coin-card-BTC')).toBeInTheDocument()
  })
})
