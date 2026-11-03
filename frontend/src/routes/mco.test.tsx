import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FAKE_VIDEO } from '@/lib/__fixtures__/mco'
import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { McoPage } from './mco'

vi.mock('@/components/charts/EChart', () => ({
  EChart: ({ label, testId }: { label: string; testId?: string }) => (
    <div role="img" aria-label={label} data-testid={testId} />
  ),
}))

const ME = { clerk_id: 'user_test', role: 'member', features: { mco: true } }
const candles = [
  { time: '2026-10-01T00:00:00Z', open: 1, high: 1, low: 1, close: 10, volume: 1 },
  { time: '2026-10-02T00:00:00Z', open: 1, high: 1, low: 1, close: 11, volume: 1 },
]
const HOSTILE = {
  ...FAKE_VIDEO,
  video_id: 'fakeVideo02',
  title: '<img src=x onerror=alert(1)> Fake second',
  url: 'javascript:alert(1)',
  published_at: '2026-10-01T10:00:00Z',
  summary: '<b>not bold</b>',
  coins: [FAKE_VIDEO.coins[1]],
}

function setup(videos: unknown[] = [FAKE_VIDEO, HOSTILE]) {
  return stubApi({
    '/api/me': ME,
    '/api/mco/videos': envelope(videos),
    '/api/ohlcv/BTC': envelope(candles),
    '/api/ohlcv/ETH': envelope(candles),
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('McoPage', () => {
  it('shows video cards with scenarios, attribution and the notice', async () => {
    setup()
    renderWithProviders(<McoPage />, { route: '/mco' })
    const card = await screen.findByLabelText('Video: Fake title about ETH')
    expect(within(card).getByRole('link', { name: 'Fake title about ETH' })).toHaveAttribute(
      'href',
      'https://www.youtube.com/watch?v=fakeVideo01',
    )
    const eth = within(card).getByLabelText('ETH view')
    expect(within(eth).getByText('Primary')).toBeInTheDocument()
    expect(within(eth).getByText('Alternative')).toBeInTheDocument()
    expect(within(eth).getByText('a break above $13')).toBeInTheDocument()
    expect(within(eth).getByText(/^\$8(\.0+)? · \$7\.50?$/)).toBeInTheDocument()
    expect(within(eth).queryByText(/yellow/)).toBeNull() // his colours are not shown (D49)
    expect(screen.getByRole('note')).toHaveTextContent(/AI-extracted .* always check the video/)
    expect(
      await screen.findByRole('img', { name: /MCO bias markers over the BTC/ }),
    ).toBeInTheDocument()
  })

  it('renders model text as text and drops unsafe links', async () => {
    setup()
    renderWithProviders(<McoPage />, { route: '/mco' })
    const card = await screen.findByLabelText(/Video: <img src=x/)
    expect(within(card).getByText('<b>not bold</b>')).toBeInTheDocument()
    expect(within(card).queryByRole('link', { name: /Fake second/ })).toBeNull()
    expect(card.querySelector('img[onerror]')).toBeNull()
  })

  it('filters by coin through the URL', async () => {
    setup()
    renderWithProviders(<McoPage />, { route: '/mco' })
    await screen.findByLabelText('Video: Fake title about ETH')
    await userEvent.click(screen.getByRole('button', { name: 'ETH' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('mco_coin=ETH'))
    expect(screen.queryByLabelText(/Video: <img/)).toBeNull()
    expect(screen.queryByLabelText('BTC view')).toBeNull()
    expect(await screen.findByRole('img', { name: /over the ETH daily close/ })).toBeInTheDocument()
  })

  it('says when nothing is summarized yet', async () => {
    setup([])
    renderWithProviders(<McoPage />, { route: '/mco' })
    expect(await screen.findByText(/No videos summarized yet/)).toBeInTheDocument()
  })
})
