import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { DataPage } from './data'

vi.mock('@/components/charts/EChart', () => ({
  EChart: ({ label, testId }: { label: string; testId?: string }) => (
    <div data-testid={testId} aria-label={label} />
  ),
}))

const col = (name: string, type: string) => ({ name, type, filterable: true })
const TABLES = envelope([
  {
    name: 'candles_daily',
    description: 'Closed daily candles',
    visibility: 'member',
    rows: 5950,
    last_updated: '2026-10-31',
    columns: [col('coin', 'VARCHAR(16)'), col('date', 'DATE'), col('close', 'DOUBLE')],
  },
  {
    name: 'news',
    description: 'RSS headlines (untrusted text)',
    visibility: 'member',
    rows: 2,
    last_updated: '2026-10-31T12:00:00+00:00',
    columns: [
      col('id', 'BIGINT'),
      col('title', 'TEXT'),
      col('published_at', 'DATETIME'),
      col('coins', 'ARRAY'),
    ],
  },
])
const page = (rows: Record<string, unknown>[], total = rows.length) =>
  envelope({
    table: 'x',
    columns: Object.keys(rows[0] ?? {}),
    total,
    page: 1,
    page_size: 100,
    rows,
  })
const COINS = envelope(
  ['BTC', 'ETH'].map((symbol) => ({ symbol, name: symbol, is_watchlist: false })),
)

function setup(extra: Record<string, unknown> = {}) {
  return stubApi({
    '/api/data/tables': TABLES,
    '/api/coins': COINS,
    '/api/data/tables/candles_daily': page(
      [
        { coin: 'BTC', date: '2026-10-31', close: 77423.98 },
        { coin: 'BTC', date: '2026-10-30', close: 76000 },
      ],
      5950,
    ),
    '/api/data/tables/news': page([
      {
        id: 1,
        title: '<img src=x onerror=alert(1)> Bitcoin',
        published_at: '2026-10-31T12:00:00+00:00',
        coins: ['BTC'],
      },
    ]),
    ...extra,
  })
}

const queryOf = (fetch: ReturnType<typeof setup>, path: string) =>
  fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname === path)

afterEach(() => vi.unstubAllGlobals())

describe('DataPage', () => {
  it('lists the tables and the computed analytics', async () => {
    setup()
    renderWithProviders(<DataPage />, { route: '/data?coin=BTC' })
    const link = await screen.findByRole('link', { name: /candles_daily/ })
    expect(link).toHaveAttribute('href', '/data?coin=BTC&table=candles_daily')
    expect(link).toHaveTextContent('5,950 rows')
    expect(screen.getByRole('link', { name: /cycles_paths/ })).toHaveAttribute(
      'href',
      '/data?coin=BTC&table=analytics&fn=cycles_paths',
    )
  })

  it('opens a deep link with its coin and date filters', async () => {
    const fetch = setup()
    renderWithProviders(<DataPage />, {
      route: '/data?table=candles_daily&coin=BTC&from=2026-10-01&to=2026-10-31',
    })
    const grid = await screen.findByTestId('data-grid')
    expect(within(grid).getByText('77423.98')).toBeInTheDocument()
    expect(screen.getByTestId('pager-status')).toHaveTextContent('Rows 1–100 of 5,950')
    const url = queryOf(fetch, '/api/data/tables/candles_daily').at(-1)!
    expect(url.searchParams.getAll('filter')).toEqual([
      'coin:eq:BTC',
      'date:gte:2026-10-01',
      'date:lte:2026-10-31',
    ])
  })

  it('sorts by a column and pages through', async () => {
    const fetch = setup()
    renderWithProviders(<DataPage />, { route: '/data?table=candles_daily&coin=BTC' })
    await screen.findByTestId('data-grid')
    await userEvent.click(screen.getByRole('button', { name: 'close' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('sort=close'))
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => {
      const url = queryOf(fetch, '/api/data/tables/candles_daily').at(-1)!
      expect(url.searchParams.get('order')).toBe('close')
      expect(url.searchParams.get('page')).toBe('2')
    })
  })

  it('shows all coins when asked, and headline text only as text', async () => {
    const fetch = setup()
    renderWithProviders(<DataPage />, { route: '/data?table=news&coin=BTC' })
    expect(await screen.findByText('<img src=x onerror=alert(1)> Bitcoin')).toBeInTheDocument()
    expect(document.querySelector('img')).toBeNull()
    await userEvent.selectOptions(screen.getByLabelText('Coin filter'), '')
    await waitFor(() => {
      const url = queryOf(fetch, '/api/data/tables/news').at(-1)!
      expect(url.searchParams.getAll('filter')).toEqual([])
    })
  })

  it('charts a numeric column from the newest rows', async () => {
    const fetch = setup()
    renderWithProviders(<DataPage />, { route: '/data?table=candles_daily&coin=BTC' })
    await screen.findByTestId('data-grid')
    await userEvent.selectOptions(screen.getByLabelText('Chart a column'), 'close')
    expect(await screen.findByTestId('data-preview')).toBeInTheDocument()
    const preview = queryOf(fetch, '/api/data/tables/candles_daily').find(
      (u) => u.searchParams.get('page_size') === '500',
    )
    expect(preview?.searchParams.get('order')).toBe('date')
  })

  it('shows a computed analytics result as tables with its single values', async () => {
    setup({
      '/api/cycles/BTC/day-n': envelope({
        name: 'cycles_day_n',
        coin: 'BTC',
        params: {},
        cached: true,
        result: {
          mode: 'bottom',
          current_cycle: '2025',
          day: 1440,
          table: [{ cycle: '2013', day: 1152 }],
        },
      }),
    })
    renderWithProviders(<DataPage />, {
      route: '/data?table=analytics&fn=cycles_day_n&coin=BTC&mode=bottom',
    })
    expect(await screen.findByTestId('result-values')).toHaveTextContent('current_cycle2025')
    expect(within(screen.getByTestId('data-grid')).getByText('1152')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'bottom' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('explains an unknown table', async () => {
    setup()
    renderWithProviders(<DataPage />, { route: '/data?table=users' })
    expect(await screen.findByText(/no table “users” you can open/)).toBeInTheDocument()
  })
})
