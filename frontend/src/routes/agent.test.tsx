import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { KEY_STORAGE } from '@/lib/keys'
import { envelope, renderWithProviders, sseResponse, stubApi } from '@/test/render'

import { AgentPage } from './agent'

const OR_KEY = 'sk-or-v1-0123456789abcdef0123456789abcdef'
const ME = (role: string) => ({
  clerk_id: 'user_x',
  role,
  features: { onchain_macro: true, mco: false, agent: true, signals: false },
})
const MODELS = envelope([
  {
    id: 'openrouter',
    label: 'OpenRouter',
    recommended: true,
    default: 'anthropic/claude-haiku-5.5',
    choices: ['anthropic/claude-haiku-5.5', 'openai/gpt-5-mini'],
  },
  { id: 'anthropic', label: 'Anthropic', recommended: false, default: 'x', choices: [] },
  { id: 'openai', label: 'OpenAI', recommended: false, default: 'gpt-6-luna', choices: [] },
])
const DONE = {
  message_id: 2,
  model: 'anthropic/claude-haiku-5.5',
  tokens_in: 17000,
  tokens_out: 2000,
  cost_usd: null,
  tool_calls: 1,
  limited: false,
  truncated: false,
}
const STREAM: [string, unknown][] = [
  ['conversation', { id: 12, title: 'Where is BTC?', model: 'm', server_key: false }],
  [
    'tool_start',
    { call_id: 'c1', name: 'get_cycle_comparison', args: { coin: 'BTC', mode: 'halving' } },
  ],
  [
    'tool_end',
    {
      call_id: 'c1',
      name: 'get_cycle_comparison',
      snapshot_id: 7,
      ok: true,
      preview: '{"as_of":"2026-11-02","sources":["coinmetrics"],"data":{',
    },
  ],
  ['token', { text: '**BTC** is 1.18x ' }],
  ['token', { text: 'its anchor. <img src=x onerror=alert(1)>' }],
  ['done', DONE],
]

function useKey() {
  localStorage.setItem(
    KEY_STORAGE,
    JSON.stringify({ provider: 'openrouter', key: OR_KEY, model: null }),
  )
}

function setup(role = 'member', extra: Record<string, unknown> = {}) {
  return stubApi({
    '/api/me': ME(role),
    '/api/agent/models': MODELS,
    '/api/agent/conversations': [],
    '/api/agent/chat': () => sseResponse(STREAM),
    ...extra,
  })
}

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('AgentPage', () => {
  it('asks a friend without a key to set one up', async () => {
    setup('member')
    renderWithProviders(<AgentPage />, { route: '/agent' })
    expect(await screen.findByText('Add your AI key to chat')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Set up a key/ })).toHaveAttribute('href', '/settings')
    expect(screen.queryByRole('textbox', { name: 'Ask the agent' })).toBeNull()
  })

  it('streams an answer with its tool card, View data link and data used', async () => {
    useKey()
    const fetch = setup('member')
    const user = userEvent.setup()
    renderWithProviders(<AgentPage />, { route: '/agent' })
    await user.type(await screen.findByRole('textbox', { name: 'Ask the agent' }), 'Where is BTC?')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    const answer = await screen.findByRole('article', { name: 'Answer' })
    await within(answer).findByTestId('data-used')
    const card = within(answer).getByTestId('tool-card')
    expect(card).toHaveTextContent('Cycle comparison')
    expect(card).toHaveTextContent('BTC · mode halving · latest data')
    expect(within(card).getByRole('link', { name: /View data/ })).toHaveAttribute(
      'href',
      '/data?snapshot=7',
    )
    expect(within(answer).getByTestId('data-used')).toHaveTextContent(
      'Data used: Cycle comparison (as of 2026-11-02)',
    )
    expect(answer.querySelector('strong')).toHaveTextContent('BTC')
    expect(answer.querySelector('img')).toBeNull() // model output never renders HTML
    expect(answer).toHaveTextContent('anthropic/claude-haiku-5.5 · 1 tool call · 19,000 tokens')
    expect(screen.getByText('Where is BTC?')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/agent?c=12'))

    const chat = fetch.mock.calls.map(([r]) => r as Request).find((r) => r.method === 'POST')
    expect(chat?.headers.get('X-LLM-Key')).toBe(OR_KEY)
    expect(await chat?.json()).toMatchObject({
      provider: 'openrouter',
      model: 'anthropic/claude-haiku-5.5',
    })
  })

  it('sends a starter question and the chosen model', async () => {
    useKey()
    const fetch = setup('member')
    const user = userEvent.setup()
    renderWithProviders(<AgentPage />, { route: '/agent' })
    await screen.findByRole('option', { name: 'openai/gpt-5-mini' })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Model' }), ['openai/gpt-5-mini'])
    await user.click(screen.getByRole('button', { name: 'Is SOL above its 20-week band?' }))
    await screen.findByTestId('data-used')
    const chat = fetch.mock.calls.map(([r]) => r as Request).find((r) => r.method === 'POST')
    expect(await chat?.json()).toMatchObject({
      message: 'Is SOL above its 20-week band?',
      model: 'openai/gpt-5-mini',
    })
  })

  it('lets the admin chat on the capped server key without a key', async () => {
    const fetch = setup('admin')
    const user = userEvent.setup()
    renderWithProviders(<AgentPage />, { route: '/agent' })
    expect(await screen.findByText('Server key · capped')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Ask the agent' }), 'Hi{Enter}')
    await screen.findByTestId('data-used')
    const chat = fetch.mock.calls.map(([r]) => r as Request).find((r) => r.method === 'POST')
    expect(chat?.headers.has('X-LLM-Key')).toBe(false)
  })

  it("shows the API's message when a question is refused", async () => {
    setup('admin', {
      '/api/agent/chat': () =>
        Response.json(
          { detail: "Rob's monthly AI budget is used up. It resets on the 1st (UTC)." },
          { status: 402 },
        ),
    })
    const user = userEvent.setup()
    renderWithProviders(<AgentPage />, { route: '/agent' })
    await user.type(await screen.findByRole('textbox', { name: 'Ask the agent' }), 'Hi{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('monthly AI budget is used up')
  })

  it('shows a stream error and the limit notes', async () => {
    useKey()
    setup('member', {
      '/api/agent/chat': () =>
        sseResponse([
          ['conversation', { id: 1, title: 'x', model: 'm', server_key: false }],
          ['token', { text: 'Partial' }],
          ['error', { code: 'timeout', message: 'The answer took longer than 90 seconds.' }],
        ]),
    })
    const user = userEvent.setup()
    renderWithProviders(<AgentPage />, { route: '/agent' })
    await user.type(await screen.findByRole('textbox', { name: 'Ask the agent' }), 'Hi{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('longer than 90 seconds')
    expect(screen.getByText('Partial')).toBeInTheDocument()
  })

  it('opens a past conversation with its snapshots, and deletes one', async () => {
    useKey()
    const detail = {
      id: 5,
      title: 'Cycle?',
      created_at: '2026-11-03T10:00:00Z',
      messages: [
        {
          id: 1,
          role: 'user',
          content: 'Cycle?',
          model: null,
          created_at: '2026-11-03T10:00:00Z',
          snapshots: [],
        },
        {
          id: 2,
          role: 'assistant',
          content: 'Day 926.',
          model: 'm',
          created_at: '2026-11-03T10:00:09Z',
          snapshots: [{ id: 3, tool: 'get_cycle_comparison', created_at: '2026-11-03T10:00:05Z' }],
        },
      ],
    }
    const listed = [
      {
        id: 5,
        title: 'Cycle?',
        created_at: '2026-11-03T10:00:00Z',
        updated_at: '2026-11-03T10:00:09Z',
        messages: 2,
      },
    ]
    const fetch = setup('member', {
      '/api/agent/conversations': listed,
      '/api/agent/conversations/5': (r: Request) =>
        r.method === 'DELETE' ? new Response(null, { status: 204 }) : Response.json(detail),
    })
    const user = userEvent.setup()
    renderWithProviders(<AgentPage />, { route: '/agent?c=5' })
    expect(await screen.findByText('Day 926.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /View data/ })).toHaveAttribute(
      'href',
      '/data?snapshot=3',
    )
    const nav = screen.getAllByRole('navigation', { name: 'Conversations' })[0]
    await user.click(within(nav).getByRole('button', { name: /Delete conversation Cycle\?/ }))
    await user.click(within(nav).getByRole('button', { name: 'Delete' }))
    await waitFor(() =>
      expect(fetch.mock.calls.some(([r]) => (r as Request).method === 'DELETE')).toBe(true),
    )
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/agent$/))
  })
})
