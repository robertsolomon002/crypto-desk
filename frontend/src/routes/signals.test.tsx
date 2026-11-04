import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DEBATE, HISTORY, SCORECARD, WEEK, WEEKS } from '@/lib/__fixtures__/signals'
import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { SignalsPage } from './signals'

vi.mock('@/components/charts/EChart', () => ({
  EChart: ({ label, testId }: { label: string; testId?: string }) => (
    <div role="img" aria-label={label} data-testid={testId} />
  ),
}))

const desk = WEEK.signals[0]

function setup(overrides: Record<string, unknown> = {}) {
  return stubApi({
    '/api/signals/week': envelope(WEEK),
    '/api/signals/weeks': envelope(WEEKS),
    '/api/signals/scorecard': envelope(SCORECARD),
    '/api/signals/history': envelope(HISTORY),
    [`/api/signals/${desk.id}/debate`]: envelope(DEBATE),
    ...overrides,
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('SignalsPage', () => {
  it('shows the notice, the brief and the signals grid as text', async () => {
    setup()
    renderWithProviders(<SignalsPage />, { route: '/signals' })
    expect(await screen.findByText('Summary line one <b>not bold</b>')).toBeInTheDocument()
    expect(screen.getAllByRole('note')[0]).toHaveTextContent(/Not financial advice/)
    expect(screen.getByLabelText('BTC brief')).toHaveTextContent('A daily close below 90.')
    const grid = screen.getByRole('table', { name: 'Signals by coin and source' })
    const btc = within(grid).getByRole('row', { name: /^BTC/ })
    expect(btc).toHaveTextContent('lean long 60%')
    expect(btc).toHaveTextContent('entry 95.00–98.00 · inval 90.00 · target 110.00')
    expect(
      within(grid)
        .getAllByRole('columnheader')
        .map((h) => h.textContent),
    ).toEqual(['Coin', 'Desk', 'Coin flip', 'Trend rule', 'MCO bias'])
    expect(within(grid).getByRole('row', { name: /^ETH/ })).toHaveTextContent('none') // no MCO
    expect(document.querySelector('img')).toBeNull()
    expect(screen.getAllByRole('link', { name: 'View data' })[0]).toHaveAttribute(
      'href',
      '/data?table=briefs',
    )
  })

  it('opens the desk debate on demand', async () => {
    const fetch = setup()
    renderWithProviders(<SignalsPage />, { route: '/signals' })
    const summary = await screen.findByText(/desk debate · lean long 60%/)
    const debatePath = `/api/signals/${desk.id}/debate`
    const called = () => fetch.mock.calls.some(([r]) => new URL(r.url).pathname === debatePath)
    expect(called()).toBe(false)
    await userEvent.click(summary)
    expect(await screen.findByText('Made-up bull point')).toBeInTheDocument()
    expect(called()).toBe(true)
    expect(screen.getByText(/Weekly desk · BTC · week of Oct 26, 2026/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /View the full run/ })).toBeNull()
  })

  it('shows the scorecard with early-days warnings and the chart', async () => {
    setup()
    renderWithProviders(<SignalsPage />, { route: '/signals' })
    const table = await screen.findByRole('table', { name: 'Scorecard by source' })
    const deskRow = within(table).getByRole('row', { name: /^Desk/ })
    expect(deskRow).toHaveTextContent('early days: 2 of 12 weeks')
    expect(deskRow).toHaveTextContent('100.0% (2/2)')
    expect(deskRow).toHaveTextContent('+5.0%')
    expect(within(table).getByRole('row', { name: /^Coin flip/ })).toHaveTextContent('—')
    expect(screen.getByRole('img', { name: /Paper P&L by source/ })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Brier' }))
    expect(screen.getByTestId('location')).toHaveTextContent('score_metric=brier')
    expect(screen.getByRole('img', { name: /Brier by source/ })).toBeInTheDocument()
  })

  it('filters the history by source in the URL', async () => {
    const fetch = setup()
    renderWithProviders(<SignalsPage />, { route: '/signals' })
    await screen.findByRole('table', { name: 'Signal history' })
    const group = screen.getByRole('group', { name: 'History source' })
    await userEvent.click(within(group).getByRole('button', { name: 'Trend rule' }))
    expect(screen.getByTestId('location')).toHaveTextContent('hist_source=trend')
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([r]) => new URL(r.url).searchParams.get('source') === 'trend'),
      ).toBe(true),
    )
  })

  it('picks a week from the list', async () => {
    const fetch = setup()
    renderWithProviders(<SignalsPage />, { route: '/signals' })
    const picker = await screen.findByRole('combobox', { name: 'Week' })
    await userEvent.selectOptions(picker, '2026-10-19')
    expect(screen.getByTestId('location')).toHaveTextContent('week=2026-10-19')
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([r]) => new URL(r.url).searchParams.get('week') === '2026-10-19'),
      ).toBe(true),
    )
  })

  it('explains an empty desk and a withheld brief', async () => {
    setup({
      '/api/signals/week': 404,
      '/api/signals/scorecard': envelope({ ...SCORECARD, weeks: [], sources: [] }),
    })
    renderWithProviders(<SignalsPage />, { route: '/signals' })
    expect(await screen.findByText(/No signals yet\. The weekly job runs/)).toBeInTheDocument()
    expect(await screen.findByText(/Nothing scored yet/)).toBeInTheDocument()
  })

  it('says why a brief is kept back', async () => {
    setup({
      '/api/signals/week': envelope({
        ...WEEK,
        brief: null,
        withheld: 'Kept back while MCO is off.',
      }),
    })
    renderWithProviders(<SignalsPage />, { route: '/signals' })
    expect(await screen.findByText('Kept back while MCO is off.')).toBeInTheDocument()
    expect(screen.queryByText(/desk debate/)).toBeNull()
  })
})
