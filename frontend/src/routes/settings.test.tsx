import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { KEY_STORAGE } from '@/lib/keys'
import { envelope, renderWithProviders, stubApi } from '@/test/render'

import { SettingsPage } from './settings'

const OR_KEY = 'sk-or-v1-0123456789abcdef0123456789abcdef'
const ME = (role: string) => ({
  clerk_id: 'user_rob',
  role,
  features: { onchain_macro: false, mco: false, agent: false, signals: false },
})
const MODELS = envelope([
  {
    id: 'openrouter',
    label: 'OpenRouter',
    recommended: true,
    default: 'anthropic/claude-haiku-5.5',
    choices: ['anthropic/claude-haiku-5.5', 'openai/gpt-5-nano'],
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    recommended: false,
    default: 'claude-haiku-5-5',
    choices: [],
  },
  { id: 'openai', label: 'OpenAI', recommended: false, default: null, choices: [] },
])

function setup(role = 'member', extra: Record<string, unknown> = {}) {
  return stubApi({
    '/api/me': ME(role),
    '/api/agent/models': MODELS,
    '/api/agent/test-key': {
      ok: true,
      provider: 'openrouter',
      model: 'anthropic/claude-haiku-5.5',
      message: 'The key works: the provider answered with anthropic/claude-haiku-5.5.',
    },
    ...extra,
  })
}

const requests = (fetch: ReturnType<typeof setup>) => fetch.mock.calls.map(([r]) => r as Request)

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('SettingsPage', () => {
  it('walks a friend through an OpenRouter key: paste, test, save', async () => {
    const fetch = setup()
    renderWithProviders(<SettingsPage />, { route: '/settings' })
    expect(await screen.findByRole('radio', { name: /OpenRouter.*Recommended/ })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(screen.getByRole('link', { name: 'Keys' })).toHaveAttribute(
      'href',
      'https://openrouter.ai/keys',
    )
    expect(screen.getByText(/stays in this browser/)).toBeInTheDocument()

    const input = screen.getByLabelText('OpenRouter API key')
    await userEvent.type(input, 'sk-ant-api03-0123456789abcdef0123')
    expect(
      screen.getByText('This looks like an Anthropic key. Pick Anthropic above.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Test key/ })).toBeDisabled()

    await userEvent.clear(input)
    await userEvent.type(input, OR_KEY)
    await userEvent.click(screen.getByRole('button', { name: /Test key/ }))
    expect(await screen.findByText(/The key works/)).toBeInTheDocument()

    const testCall = requests(fetch).find((r) => r.url.endsWith('/api/agent/test-key'))!
    expect(testCall.headers.get('X-LLM-Key')).toBe(OR_KEY)
    expect(await testCall.clone().json()).toEqual({ provider: 'openrouter', model: null })
    // The key goes with the key test only, never with other requests.
    for (const r of requests(fetch).filter((r) => r !== testCall))
      expect(r.headers.get('X-LLM-Key')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Save in this browser' }))
    expect(JSON.parse(localStorage.getItem(KEY_STORAGE)!)).toEqual({
      provider: 'openrouter',
      key: OR_KEY,
      model: null,
    })
    expect(screen.getByText('Saved in this browser.')).toBeInTheDocument()
    expect(screen.getByTestId('saved-key')).toHaveTextContent('sk-or-v1-…cdef')
    expect(document.body.textContent).not.toContain(OR_KEY)
  })

  it('forgets a saved key', async () => {
    localStorage.setItem(
      KEY_STORAGE,
      JSON.stringify({ provider: 'openrouter', key: OR_KEY, model: 'openai/gpt-5-nano' }),
    )
    setup()
    renderWithProviders(<SettingsPage />, { route: '/settings' })
    expect(await screen.findByText('openai/gpt-5-nano')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Forget key' }))
    expect(localStorage.getItem(KEY_STORAGE)).toBeNull()
    expect(screen.getByLabelText('OpenRouter API key')).toHaveValue('')
  })

  it('switches the theme', async () => {
    setup()
    renderWithProviders(<SettingsPage />, { route: '/settings' })
    await userEvent.click(await screen.findByRole('button', { name: 'Light' }))
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Dark' }))
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('hides the admin sections from members', async () => {
    setup()
    renderWithProviders(<SettingsPage />, { route: '/settings' })
    await screen.findByRole('radio', { name: /OpenRouter/ })
    expect(screen.queryByRole('region', { name: /Watchlist/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /Invite friends/ })).not.toBeInTheDocument()
  })

  it('lets the admin check and add a watchlist coin', async () => {
    const fetch = setup('admin', {
      '/api/admin/watchlist': [],
      '/api/admin/watchlist/check/LINK': {
        symbol: 'LINK',
        market: 'LINK/USD',
        name: 'Chainlink',
        eligible: true,
        reasons: [],
      },
      '/api/admin/invites': [],
      '/api/admin/users': [
        { id: 1, clerk_id: 'user_rob', role: 'admin', created_at: '2026-10-30T00:00:00Z' },
      ],
      '/api/admin/usage': {
        month: '2026-11',
        spend_usd: 0.4,
        cap_usd: 8,
        by_source: [{ key: 'desk', cost: 0.4, tokens_in: 1000, tokens_out: 100 }],
        by_model: [],
        users: [],
        jobs: [],
      },
    })
    renderWithProviders(<SettingsPage />, { route: '/settings' })
    await userEvent.type(await screen.findByLabelText('Symbol'), 'link')
    await userEvent.click(screen.getByRole('button', { name: 'Check' }))
    expect(await screen.findByText(/LINK\/USD is on Coinbase/)).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toHaveValue('Chainlink')
    await userEvent.click(screen.getByRole('button', { name: 'Add LINK' }))
    await waitFor(() => {
      const post = requests(fetch).find(
        (r) => r.method === 'POST' && r.url.endsWith('/api/admin/watchlist'),
      )
      expect(post).toBeDefined()
    })
    expect(await screen.findByTestId('spend')).toHaveTextContent('$0.40')
  })
})
