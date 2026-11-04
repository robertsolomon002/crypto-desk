import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { OnchainPage } from './onchain'

vi.mock('@/components/charts/EChart', () => ({
  EChart: ({ label, testId }: { label: string; testId?: string }) => (
    <div data-testid={testId} aria-label={label} />
  ),
}))

const DAYS = Array.from({ length: 800 }, (_, i) =>
  new Date(Date.UTC(2024, 7, 25) + i * 86_400_000).toISOString().slice(0, 10),
)

const onchain = (coin: string) =>
  envelope({
    name: 'onchain',
    coin,
    params: {},
    cached: false,
    result: DAYS.map((date, i) => ({
      date,
      mvrv: 1.2 + i / 1000,
      market_cap: 1e12,
      realized_cap: 7e11,
      realized_price: 50_000,
      nupl: 0.3,
      supply: 2e7,
      active_addresses: 700_000 + i,
      hash_rate: coin === 'BTC' ? 9e8 + i * 1e5 : null,
    })),
  })

const candles = DAYS.map((d, i) => ({
  time: `${d}T00:00:00Z`,
  open: 1,
  high: 1,
  low: 1,
  close: 60_000 + i * 10,
  volume: 1,
}))

const macroRows = DAYS.map((date, i) => ({
  date,
  DTWEXBGS: 120 + Math.sin(i / 20),
  DGS10: 4 + Math.cos(i / 15) / 5,
  DFF: 4.33,
  M2SL: date.endsWith('-01') ? 21_000 + i : null,
}))

const MACRO = envelope({
  series: [
    { id: 'DTWEXBGS', label: 'Broad U.S. dollar index', units: 'index', release_lag_days: 8 },
    { id: 'DGS10', label: '10-year Treasury yield', units: 'percent', release_lag_days: 6 },
    { id: 'DFF', label: 'Effective federal funds rate', units: 'percent', release_lag_days: 6 },
    { id: 'M2SL', label: 'M2 money supply', units: 'billions USD', release_lag_days: 60 },
  ],
  rows: macroRows,
})

function setup() {
  return stubApi({
    '/api/onchain/BTC': onchain('BTC'),
    '/api/onchain/ETH': onchain('ETH'),
    '/api/ohlcv/BTC': envelope(candles),
    '/api/ohlcv/ETH': envelope(candles),
    '/api/macro': MACRO,
    '/api/macro/fng': envelope(DAYS.map((date, i) => ({ date, value: 20 + (i % 60) }))),
    '/api/macro/dominance': envelope({
      rows: [
        { date: '2026-10-29', btc: 59.5, eth: 10.5 },
        { date: '2026-10-30', btc: 59.7, eth: 10.4 },
      ],
    }),
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('OnchainPage', () => {
  it('draws every BTC panel with readouts and data links', async () => {
    setup()
    renderWithProviders(<OnchainPage />, { route: '/onchain?coin=BTC' })
    for (const id of [
      'mvrv-chart',
      'realized-chart',
      'nupl-chart',
      'addresses-chart',
      'hash-chart',
      'fng-chart',
      'dominance-chart',
      'macro-DTWEXBGS',
      'macro-DGS10',
      'macro-DFF',
      'macro-M2SL',
    ])
      expect(await screen.findByTestId(id)).toBeInTheDocument()
    expect(screen.getByTestId('nupl-readout')).toHaveTextContent('0.30')
    expect(screen.getByTestId('nupl-readout')).toHaveTextContent('Optimism / anxiety')
    expect(screen.getByTestId('mvrv-readout')).toHaveTextContent('100th percentile')
    expect(screen.getByTestId('hash-readout')).toHaveTextContent('EH/s')
    expect(screen.getByTestId('dominance-readout')).toHaveTextContent('BTC 59.7%')
    // Fed funds never moves in the fixture, so its correlation is undefined.
    expect(screen.getByTestId('corr-DFF')).toHaveTextContent('1Y —')
    expect(screen.getByTestId('corr-DGS10')).toHaveTextContent(/1Y r = [+−]\d\.\d\d/)
    expect(screen.getByTestId('corr-M2SL')).toHaveTextContent('monthly changes')
    const links = screen.getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(links).toContain('/data?table=analytics&fn=onchain&coin=BTC')
    expect(links).toContain('/data?table=series&key=fred%3AM2SL')
    expect(links).toContain('/data?table=series&key=cm%3ABTC%3AHashRate')
    expect(screen.queryByTestId('onchain-coin-note')).not.toBeInTheDocument()
    // Source terms (Stage 8.2): FRED's required notice and CoinGecko's linked credit.
    expect(screen.getByTestId('fred-notice')).toHaveTextContent(
      'This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.',
    )
    expect(links).toContain('https://fred.stlouisfed.org/docs/api/terms_of_use.html')
    expect(screen.getByTestId('coingecko-credit')).toHaveTextContent('Data provided by CoinGecko')
    expect(links).toContain('https://www.coingecko.com/')
  })

  it('notes the missing ETH hash rate instead of drawing it', async () => {
    setup()
    renderWithProviders(<OnchainPage />, { route: '/onchain?coin=ETH' })
    expect(await screen.findByTestId('panel-unavailable')).toHaveTextContent('proof of stake')
    expect(screen.queryByTestId('hash-chart')).not.toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: /ETH MVRV/ })).toBeInTheDocument()
  })

  it('shows BTC on-chain data for a coin without free on-chain data', async () => {
    const fetch = setup()
    renderWithProviders(<OnchainPage />, { route: '/onchain?coin=SOL' })
    expect(await screen.findByTestId('onchain-coin-note')).toHaveTextContent('BTC and ETH only')
    expect(await screen.findByRole('heading', { name: /BTC MVRV/ })).toBeInTheDocument()
    const paths = fetch.mock.calls.map(([r]) => new URL((r as Request).url).pathname)
    expect(paths).not.toContain('/api/onchain/SOL')
  })

  it('keeps overlays, range and the M2 view in the URL', async () => {
    setup()
    const user = userEvent.setup()
    renderWithProviders(<OnchainPage />, { route: '/onchain?coin=BTC' })
    await screen.findByTestId('macro-M2SL')
    const overlays = screen.getAllByRole('button', { name: 'Overlay on BTC' })
    expect(overlays).toHaveLength(4)
    await user.click(overlays[3])
    await user.click(overlays[1])
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('overlay=DGS10%2CM2SL'),
    )
    expect(overlays[1]).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('macro-M2SL')).toHaveAttribute(
      'aria-label',
      'M2 money supply with the Bitcoin price',
    )
    await user.click(screen.getByRole('button', { name: 'Level' }))
    await user.click(screen.getByRole('button', { name: '1Y' }))
    const loc = screen.getByTestId('location')
    expect(loc).toHaveTextContent('m2=level')
    expect(loc).toHaveTextContent('range=1y')
    await user.click(overlays[1])
    await waitFor(() => expect(loc).toHaveTextContent('overlay=M2SL'))
  })
})
