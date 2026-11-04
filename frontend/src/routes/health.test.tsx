import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HEALTH } from '@/lib/__fixtures__/health'
import { renderWithProviders, stubApi } from '@/test/render'

import { HealthPage } from './health'

const STATUS = { status: 'ok', version: '0.1.0', time_utc: '2026-10-28T00:00:00Z' }
const ME = (role: string) => ({
  clerk_id: 'user_rob',
  role,
  features: { onchain_macro: false, mco: false, agent: false, signals: false },
})

afterEach(() => vi.unstubAllGlobals())

describe('HealthPage', () => {
  it('shows the backend status to anyone', async () => {
    const fetch = stubApi({ '/api/health': STATUS, '/api/me': ME('member') })
    renderWithProviders(<HealthPage />, { route: '/health' })
    expect(await screen.findByTestId('health-status')).toHaveTextContent('ok')
    expect(screen.queryByRole('region', { name: 'Jobs' })).not.toBeInTheDocument()
    const paths = fetch.mock.calls.map(([r]) => new URL((r as Request).url).pathname)
    expect(paths).not.toContain('/api/admin/health') // members never ask for it
  })

  it('shows an error when the backend is down', async () => {
    stubApi({ '/api/health': 503, '/api/me': 401 })
    renderWithProviders(<HealthPage />, { route: '/health' })
    expect(await screen.findByText('Backend unreachable')).toBeInTheDocument()
  })

  it('gives admins jobs, freshness, spend, errors and usage', async () => {
    stubApi({ '/api/health': STATUS, '/api/me': ME('admin'), '/api/admin/health': HEALTH })
    renderWithProviders(<HealthPage />, { route: '/health' })

    const overall = await screen.findByTestId('ops-overall')
    expect(overall).toHaveTextContent('2 to look at')
    expect(overall).toHaveTextContent('mco: no successful run in 26 h')

    const mco = screen.getByTestId('job-mco')
    expect(within(mco).getByText('overdue')).toBeInTheDocument()
    expect(mco).toHaveTextContent('gemini-3.8-flash:fallback:503')
    expect(screen.getByTestId('job-daily')).not.toHaveTextContent('overdue')
    expect(screen.getByTestId('job-backup')).toHaveTextContent('never ran')

    const fresh = screen.getByRole('region', { name: 'Data freshness' })
    expect(within(fresh).getByText('ETH Coin Metrics')).toBeInTheDocument()

    expect(screen.getByTestId('ops-spend')).toHaveTextContent('$6.80')
    const meter = screen.getByRole('meter', { name: 'Share of the monthly cap used' })
    expect(meter).toHaveAttribute('aria-valuenow', '6.8')
    expect(screen.getByText(/On: The weekly brief writer uses Haiku/)).toBeInTheDocument()

    expect(screen.getByTestId('ops-errors')).toHaveTextContent('6')
    expect(screen.getByText('OperationalError')).toBeInTheDocument()

    expect(screen.getByRole('region', { name: 'Free-tier usage' })).toHaveTextContent(
      'Database 28.0 MB of 1024.0 MB (Neon Free)',
    )
    expect(screen.getByRole('link', { name: 'Cloud Run metrics' })).toHaveAttribute(
      'href',
      'https://console.cloud.google.com/run',
    )
    // An unsafe URL is shown as text, never as a link.
    expect(screen.queryByRole('link', { name: 'Not a link' })).not.toBeInTheDocument()
    expect(screen.getByText('Not a link')).toBeInTheDocument()
  })

  it('says so when everything is fine', async () => {
    stubApi({
      '/api/health': STATUS,
      '/api/me': ME('admin'),
      '/api/admin/health': { ...HEALTH, ok: true, problems: [] },
    })
    renderWithProviders(<HealthPage />, { route: '/health' })
    expect(await screen.findByTestId('ops-overall')).toHaveTextContent('All jobs on time')
  })
})
