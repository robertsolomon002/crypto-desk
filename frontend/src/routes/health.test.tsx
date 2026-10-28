import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HealthPage } from './health'

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <HealthPage />
    </QueryClientProvider>,
  )
}

describe('HealthPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the backend status', async () => {
    const body = { status: 'ok', version: '0.1.0', time_utc: '2026-10-28T00:00:00Z' }
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json(body)),
    )
    renderPage()
    expect(await screen.findByTestId('health-status')).toHaveTextContent('ok')
  })

  it('shows an error when the backend is down', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('down', { status: 503 })),
    )
    renderPage()
    expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
  })
})
