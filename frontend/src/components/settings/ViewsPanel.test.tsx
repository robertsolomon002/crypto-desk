import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { ViewsPanel } from './ViewsPanel'

const COINS = envelope(
  ['BTC', 'ETH'].map((symbol) => ({ symbol, name: symbol, is_watchlist: false })),
)
const MANUAL = {
  id: 'manual:3',
  kind: 'manual',
  source: 'Some Analyst',
  coin: 'ETH',
  published_at: '2026-11-01T10:00:00Z',
  bias: 'bullish',
  wave_position: null,
  levels: [{ price: 4000, label: 'breakout' }],
  invalidation: 3000,
  targets: [],
  scenarios: [],
  confidence: null,
  low_detail: false,
  url: null,
}
const MCO = { ...MANUAL, id: 'mco:x', kind: 'mco', source: 'More Crypto Online' }

afterEach(() => vi.unstubAllGlobals())

describe('ViewsPanel', () => {
  it('lists manual views only, adds one and deletes one', async () => {
    const sent: { method: string; path: string; body: unknown }[] = []
    stubApi({
      '/api/coins': COINS,
      '/api/views': envelope([MANUAL, MCO]),
      '/api/admin/views': async (r: Request) => {
        sent.push({ method: r.method, path: '/api/admin/views', body: await r.json() })
        return Response.json(MANUAL, { status: 201 })
      },
      '/api/admin/views/3': (r: Request) => {
        sent.push({ method: r.method, path: '/api/admin/views/3', body: null })
        return new Response(null, { status: 204 })
      },
    })
    renderWithProviders(<ViewsPanel />)
    const list = await screen.findByRole('list', { name: 'Manual views' })
    expect(list.querySelectorAll('li')).toHaveLength(1)

    const add = screen.getByRole('button', { name: 'Add view' })
    expect(add).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Source'), 'Some Analyst')
    await userEvent.type(screen.getByLabelText('Levels (optional)'), 'breakout 70000')
    expect(screen.getByText(/needs a price and a label/)).toBeInTheDocument()
    expect(add).toBeDisabled()
    await userEvent.clear(screen.getByLabelText('Levels (optional)'))
    await userEvent.type(screen.getByLabelText('Levels (optional)'), '70,000 breakout')
    await userEvent.selectOptions(screen.getByLabelText('Bias'), 'bullish')
    await userEvent.type(screen.getByLabelText('Invalidation (optional)'), '61000')
    await userEvent.click(add)
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0].body).toEqual({
      source: 'Some Analyst',
      coin: 'BTC',
      bias: 'bullish',
      levels: [{ price: 70000, label: 'breakout' }],
      invalidation: 61000,
      url: null,
    })

    await userEvent.click(
      screen.getByRole('button', { name: 'Delete the Some Analyst view on ETH' }),
    )
    await waitFor(() => expect(sent.map((s) => s.method)).toEqual(['POST', 'DELETE']))
  })
})
