import { afterEach, describe, expect, it, vi } from 'vitest'

import { sseResponse, stubApi } from '@/test/render'

import {
  applyEvent,
  ChatRequestError,
  describeArgs,
  modelOptions,
  parseSse,
  previewAsOf,
  streamChat,
  toolLabel,
  type ChatEvent,
  type Turn,
} from './agent'

const OR_KEY = 'sk-or-v1-0123456789abcdef0123456789abcdef'

afterEach(() => vi.unstubAllGlobals())

describe('parseSse', () => {
  it('returns complete events and keeps the unfinished rest', () => {
    const { events, rest } = parseSse(
      ': ping\n\nevent: token\ndata: {"text":"Hi"}\n\nevent: tool_start\ndata: {"call',
    )
    expect(events).toEqual([{ event: 'token', data: { text: 'Hi' } }])
    expect(rest).toBe('event: tool_start\ndata: {"call')
  })

  it('handles CRLF and skips unknown or malformed events', () => {
    const { events } = parseSse(
      'event: token\r\ndata: {"text":"a"}\r\n\r\nevent: evil\ndata: {}\n\nevent: token\ndata: {nope\n\n',
    )
    expect(events).toEqual([{ event: 'token', data: { text: 'a' } }])
  })
})

describe('streamChat', () => {
  const events: [string, unknown][] = [
    ['conversation', { id: 3, title: 'Q', model: 'm', server_key: false }],
    ['tool_start', { call_id: 'c1', name: 'get_key_levels', args: { coin: 'BTC' } }],
    ['tool_end', { call_id: 'c1', name: 'get_key_levels', snapshot_id: 7, ok: true, preview: 'x' }],
    ['token', { text: 'BTC is ' }],
    ['token', { text: 'above.' }],
    [
      'done',
      {
        message_id: 9,
        model: 'm',
        tokens_in: 10,
        tokens_out: 2,
        cost_usd: null,
        tool_calls: 1,
        limited: false,
        truncated: false,
      },
    ],
  ]

  it('sends the key only in X-LLM-Key and yields every event in order', async () => {
    const fetch = stubApi({ '/api/agent/chat': () => sseResponse(events, 7) })
    const got: ChatEvent[] = []
    await streamChat(
      {
        message: 'Where?',
        conversationId: null,
        key: { provider: 'openrouter', key: OR_KEY, model: null },
        model: 'openai/gpt-5-mini',
      },
      (e) => got.push(e),
    )
    expect(got.map((e) => e.event)).toEqual(events.map(([e]) => e))
    const request = fetch.mock.calls[0][0] as Request
    expect(request.method).toBe('POST')
    expect(request.headers.get('X-LLM-Key')).toBe(OR_KEY)
    const body = await request.json()
    expect(body).toEqual({
      message: 'Where?',
      conversation_id: null,
      provider: 'openrouter',
      model: 'openai/gpt-5-mini',
    })
    expect(JSON.stringify(body)).not.toContain(OR_KEY)
  })

  it('sends no key, provider or model for the server key', async () => {
    const fetch = stubApi({ '/api/agent/chat': () => sseResponse([]) })
    await streamChat({ message: 'Hi', conversationId: 4, key: null, model: 'x' }, () => {})
    const request = fetch.mock.calls[0][0] as Request
    expect(request.headers.has('X-LLM-Key')).toBe(false)
    expect(await request.json()).toMatchObject({ conversation_id: 4, provider: null, model: null })
  })

  it("turns a refusal into the API's own message", async () => {
    stubApi({
      '/api/agent/chat': () =>
        Response.json(
          { detail: "You've asked 30 questions in the last hour." },
          { status: 429, headers: { 'Retry-After': '120' } },
        ),
    })
    const err = await streamChat(
      { message: 'Hi', conversationId: null, key: null, model: null },
      () => {},
    ).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ChatRequestError)
    expect((err as ChatRequestError).status).toBe(429)
    expect((err as ChatRequestError).retryAfter).toBe(120)
    expect((err as ChatRequestError).message).toMatch(/30 questions/)
  })
})

describe('applyEvent', () => {
  it('builds an answer from its events', () => {
    let turn: Turn = { key: 't', role: 'assistant', text: '', tools: [], streaming: true }
    const steps: ChatEvent[] = [
      { event: 'tool_start', data: { call_id: 'a', name: 'list_coins', args: {} } },
      { event: 'token', data: { text: 'Three ' } },
      {
        event: 'tool_end',
        data: { call_id: 'a', name: 'list_coins', snapshot_id: 5, ok: false, preview: 'err' },
      },
      { event: 'token', data: { text: 'coins.' } },
      { event: 'error', data: { code: 'timeout', message: 'Took too long.' } },
    ]
    for (const e of steps) turn = applyEvent(turn, e)
    expect(turn.text).toBe('Three coins.')
    expect(turn.tools).toEqual([
      { callId: 'a', name: 'list_coins', args: {}, snapshotId: 5, ok: false, preview: 'err' },
    ])
    expect(turn.error).toBe('Took too long.')
    expect(turn.streaming).toBe(false)
  })
})

describe('plain words', () => {
  it('labels tools and describes their arguments', () => {
    expect(toolLabel('get_cycle_comparison')).toBe('Cycle comparison')
    expect(toolLabel('get_new_thing')).toBe('New thing')
    expect(describeArgs({ coin: 'BTC', mode: 'halving' })).toBe('BTC · mode halving · latest data')
    expect(describeArgs({ coins: ['BTC', 'ETH'], window: 90, as_of: '2026-10-01' })).toBe(
      'BTC, ETH · window 90 · as of 2026-10-01',
    )
    expect(describeArgs({ coin: 'SOL', as_of: null })).toBe('SOL · latest data')
  })

  it('reads the as-of date from a preview', () => {
    expect(previewAsOf('{"as_of":"2026-11-02","sources":["x"]')).toBe('2026-11-02')
    expect(previewAsOf('Unknown tool: x')).toBeNull()
  })

  it('offers the saved model first, then the default and choices, without repeats', () => {
    const providers = [
      { id: 'openrouter', default: 'a/1', choices: ['a/1', 'b/2'] },
      { id: 'openai', default: 'gpt-6-luna', choices: ['gpt-6-luna'] },
    ]
    expect(modelOptions('openrouter', providers, 'c/3')).toEqual(['c/3', 'a/1', 'b/2'])
    expect(modelOptions('openrouter', providers, null)).toEqual(['a/1', 'b/2'])
    expect(modelOptions('anthropic', providers, null)).toEqual([])
  })
})
