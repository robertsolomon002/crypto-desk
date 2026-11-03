import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './api'
import type { components } from './api-schema'
import { keyHeader, type LlmKey, type Provider } from './keys'
import { unwrap } from './queries'

// The Agent tab's API (Stage 5.2): `POST /api/agent/chat` streams Server-Sent Events (D45); the
// event payload types come from the OpenAPI components. The user's key goes only into this
// request's `X-LLM-Key` header.

type Schemas = components['schemas']
export type ConversationEvent = Schemas['ConversationEvent']
export type TokenEvent = Schemas['TokenEvent']
export type ToolStartEvent = Schemas['ToolStartEvent']
export type ToolEndEvent = Schemas['ToolEndEvent']
export type DoneEvent = Schemas['DoneEvent']
export type ErrorEvent = Schemas['ErrorEvent']
export type ConversationSummary = Schemas['ConversationSummary']
export type ConversationDetail = Schemas['ConversationDetail']
export type ChatMessage = Schemas['ChatMessage']
export type Snapshot = Schemas['Snapshot']

export type ChatEvent =
  | { event: 'conversation'; data: ConversationEvent }
  | { event: 'token'; data: TokenEvent }
  | { event: 'tool_start'; data: ToolStartEvent }
  | { event: 'tool_end'; data: ToolEndEvent }
  | { event: 'done'; data: DoneEvent }
  | { event: 'error'; data: ErrorEvent }

const EVENT_NAMES = new Set(['conversation', 'token', 'tool_start', 'tool_end', 'done', 'error'])

/** Complete events from an SSE buffer, and the unfinished rest to keep for the next chunk. */
export function parseSse(buffer: string): { events: ChatEvent[]; rest: string } {
  const text = buffer.replace(/\r\n/g, '\n')
  const blocks = text.split('\n\n')
  const rest = blocks.pop() ?? ''
  const events: ChatEvent[] = []
  for (const block of blocks) {
    let name: string | null = null
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith(':')) continue // keepalive comment
      if (line.startsWith('event:')) name = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
    }
    if (!name || !EVENT_NAMES.has(name) || data.length === 0) continue
    try {
      events.push({ event: name, data: JSON.parse(data.join('\n')) } as ChatEvent)
    } catch {
      // a malformed event is skipped, never shown
    }
  }
  return { events, rest }
}

/** A refused request (before streaming): its status and the API's own message. */
export class ChatRequestError extends Error {
  readonly status: number
  readonly retryAfter: number | null

  constructor(status: number, message: string, retryAfter: number | null = null) {
    super(message)
    this.status = status
    this.retryAfter = retryAfter
  }
}

export interface ChatInput {
  message: string
  conversationId: number | null
  /** Null for the admin's server key (no key in this browser). */
  key: LlmKey | null
  model: string | null
}

function detailOf(error: unknown): string | null {
  if (error && typeof error === 'object' && 'detail' in error) {
    const d = (error as { detail: unknown }).detail
    if (typeof d === 'string') return d
  }
  return null
}

/** Ask the agent, calling `onEvent` for each event as it arrives. */
export async function streamChat(
  input: ChatInput,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const { response, error } = await api.POST('/api/agent/chat', {
    body: {
      message: input.message,
      conversation_id: input.conversationId,
      provider: input.key?.provider ?? null,
      model: input.key ? input.model || null : null,
    },
    headers: keyHeader(input.key),
    parseAs: 'stream',
    signal,
  })
  if (!response.ok || !response.body) {
    const retry = Number(response.headers.get('Retry-After')) || null
    const fallback =
      response.status === 422 ? 'That question is too long.' : `Request failed (${response.status})`
    throw new ChatRequestError(response.status, detailOf(error) ?? fallback, retry)
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    const { events, rest } = parseSse(buffer)
    buffer = rest
    for (const e of events) onEvent(e)
  }
  const { events } = parseSse(buffer + '\n\n')
  for (const e of events) onEvent(e)
}

// --- Conversations and snapshots ----------------------------------------------------------------

export function useConversations(enabled = true) {
  return useQuery({
    queryKey: ['agent', 'conversations'],
    queryFn: () => unwrap(api.GET('/api/agent/conversations')),
    enabled,
    staleTime: 0,
  })
}

export function useConversation(id: number | null) {
  return useQuery({
    queryKey: ['agent', 'conversation', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/agent/conversations/{conversation_id}', {
          params: { path: { conversation_id: id as number } },
        }),
      ),
    enabled: id !== null,
    staleTime: 0,
  })
}

export function useDeleteConversation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const { response } = await api.DELETE('/api/agent/conversations/{conversation_id}', {
        params: { path: { conversation_id: id } },
      })
      if (!response.ok) throw new Error(`Delete failed (${response.status})`)
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ['agent', 'conversations'] }),
  })
}

export function useSnapshot(id: number | null) {
  return useQuery({
    queryKey: ['agent', 'snapshot', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/agent/snapshots/{snapshot_id}', {
          params: { path: { snapshot_id: id as number } },
        }),
      ),
    enabled: id !== null,
    staleTime: Infinity, // a snapshot never changes
  })
}

// --- Plain words for tool calls -----------------------------------------------------------------

const TOOL_LABELS: Record<string, string> = {
  list_coins: 'Coins tracked',
  get_ohlcv: 'Price history',
  get_indicators: 'Indicators',
  get_regime: 'Market regime',
  get_key_levels: 'Key levels',
  get_pivots: 'Swing pivots',
  compare_assets: 'Asset comparison',
  get_cycle_comparison: 'Cycle comparison',
  get_yoy: 'Year-over-year',
  get_seasonality: 'Seasonality',
  get_return_distribution: 'Return distribution',
  get_drawdowns: 'Drawdowns',
  get_correlations: 'Correlations',
  get_onchain: 'On-chain metrics',
  get_macro: 'Macro series',
  get_sentiment: 'Sentiment',
  get_news: 'Headlines',
  get_calendar: 'Macro calendar',
  get_external_views: 'Analyst views',
}

export function toolLabel(name: string): string {
  if (TOOL_LABELS[name]) return TOOL_LABELS[name]
  const words = name.replace(/^get_/, '').replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

function argText(value: unknown): string {
  if (Array.isArray(value)) return value.map(argText).join(', ')
  if (value && typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** Tool arguments in plain words: "BTC · mode halving · as of 2026-10-01". */
export function describeArgs(args: Record<string, unknown>): string {
  const parts: string[] = []
  const rest = Object.entries(args).filter(([, v]) => v !== null && v !== undefined && v !== '')
  for (const key of ['coin', 'coins', 'base', 'quote']) {
    const hit = rest.find(([k]) => k === key)
    if (hit) parts.push(argText(hit[1]))
  }
  for (const [k, v] of rest) {
    if (['coin', 'coins', 'base', 'quote', 'as_of'].includes(k)) continue
    parts.push(`${k.replace(/_/g, ' ')} ${argText(v)}`)
  }
  const asOf = rest.find(([k]) => k === 'as_of')
  parts.push(asOf ? `as of ${argText(asOf[1])}` : 'latest data')
  return parts.join(' · ')
}

/** The as-of date a tool result reports (it leads the JSON, so the preview carries it). */
export function previewAsOf(preview: string): string | null {
  const m = /"as_of"\s*:\s*"(\d{4}-\d{2}-\d{2})/.exec(preview)
  return m ? m[1] : null
}

export const snapshotLink = (id: number) => `/data?snapshot=${id}`

// --- Model choice -------------------------------------------------------------------------------

export const STARTERS = [
  'Where is BTC in its cycle vs 2017?',
  'Is SOL above its 20-week band?',
  'What macro events could move crypto this week?',
]

/** The models to offer for this key's provider: its choices, with the saved model first. */
export function modelOptions(
  provider: Provider,
  providers: { id: string; default: string | null; choices: string[] }[] | undefined,
  saved: string | null,
): string[] {
  const p = providers?.find((x) => x.id === provider)
  const out: string[] = []
  for (const m of [saved, p?.default ?? null, ...(p?.choices ?? [])])
    if (m && !out.includes(m)) out.push(m)
  return out
}

// --- Turns: what the chat view shows -------------------------------------------------------------

export interface ToolCall {
  callId: string
  name: string
  args: Record<string, unknown> | null // null for calls loaded from history
  snapshotId: number | null
  ok: boolean | null // null while running
  preview: string | null
}

export interface Turn {
  key: string
  role: 'user' | 'assistant'
  text: string
  tools: ToolCall[]
  done?: DoneEvent
  error?: string
  streaming?: boolean
}

let turnSeq = 0
export const nextTurnKey = () => `t${++turnSeq}`

export function turnsFromDetail(detail: ConversationDetail): Turn[] {
  return detail.messages.map((m) => ({
    key: `m${m.id}`,
    role: m.role,
    text: m.content,
    tools: (m.snapshots ?? []).map((s) => ({
      callId: `s${s.id}`,
      name: s.tool,
      args: null,
      snapshotId: s.id,
      ok: true,
      preview: null,
    })),
  }))
}

/** One event applied to the answer being streamed. */
export function applyEvent(turn: Turn, e: ChatEvent): Turn {
  switch (e.event) {
    case 'token':
      return { ...turn, text: turn.text + e.data.text }
    case 'tool_start':
      return {
        ...turn,
        tools: [
          ...turn.tools,
          {
            callId: e.data.call_id,
            name: e.data.name,
            args: e.data.args,
            snapshotId: null,
            ok: null,
            preview: null,
          },
        ],
      }
    case 'tool_end':
      return {
        ...turn,
        tools: turn.tools.map((t) =>
          t.callId === e.data.call_id
            ? { ...t, snapshotId: e.data.snapshot_id, ok: e.data.ok, preview: e.data.preview }
            : t,
        ),
      }
    case 'done':
      return { ...turn, done: e.data, streaming: false }
    case 'error':
      return { ...turn, error: e.data.message, streaming: false }
    default:
      return turn
  }
}
