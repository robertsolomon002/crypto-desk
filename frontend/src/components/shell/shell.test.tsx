import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { CoinSelector } from './CoinSelector'
import { ColdStartBanner, SLOW_MS } from './ColdStartBanner'
import { ErrorBoundary } from './ErrorBoundary'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('ColdStartBanner', () => {
  function Pending({ resolve }: { resolve: Promise<string> }) {
    useQuery({ queryKey: ['slow'], queryFn: () => resolve })
    return null
  }

  it('appears only when the first load is slow, and goes once data arrives', async () => {
    vi.useFakeTimers()
    let done: (value: string) => void = () => {}
    const promise = new Promise<string>((r) => (done = r))
    const client = new QueryClient()
    render(
      <QueryClientProvider client={client}>
        <ColdStartBanner />
        <Pending resolve={promise} />
      </QueryClientProvider>,
    )
    await act(() => vi.advanceTimersByTimeAsync(SLOW_MS - 100))
    expect(screen.queryByRole('status')).toBeNull()
    await act(() => vi.advanceTimersByTimeAsync(200))
    expect(screen.getByRole('status')).toHaveTextContent('Waking up the server')
    await act(async () => done('ok'))
    await act(() => vi.advanceTimersByTimeAsync(10)) // Query batches its notifications
    expect(screen.queryByRole('status')).toBeNull()
  })
})

describe('ErrorBoundary', () => {
  it('shows a fallback and recovers on retry', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    let broken = true
    function Flaky() {
      if (broken) throw new Error('boom')
      return <p>fine</p>
    }
    render(
      <ErrorBoundary label="This tab">
        <Flaky />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('This tab hit an error.')
    broken = false
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(screen.getByText('fine')).toBeInTheDocument()
  })
})

describe('CoinSelector', () => {
  it('lists core coins then the watchlist and writes the choice to the URL', async () => {
    stubApi({
      '/api/coins': envelope([
        { symbol: 'BTC', name: 'Bitcoin', is_watchlist: false },
        { symbol: 'ETH', name: 'Ethereum', is_watchlist: false },
        { symbol: 'LINK', name: 'Chainlink', is_watchlist: true },
      ]),
    })
    renderWithProviders(<CoinSelector />, { route: '/charts?coin=eth' })
    const select = screen.getByRole('combobox', { name: 'Coin' })
    expect(await screen.findByRole('option', { name: 'LINK' })).toBeInTheDocument()
    expect(select).toHaveValue('ETH')
    expect(screen.getByRole('group', { name: 'Watchlist' })).toBeInTheDocument()
    await userEvent.selectOptions(select, 'LINK')
    expect(screen.getByTestId('location')).toHaveTextContent('/charts?coin=LINK')
  })
})
