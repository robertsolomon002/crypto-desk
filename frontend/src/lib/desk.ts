import { useQuery } from '@tanstack/react-query'

import { ChatRequestError, detailOf, readEvents, type ToolCall } from './agent'
import { api } from './api'
import type { components } from './api-schema'
import { keyHeader, type LlmKey } from './keys'
import { unwrap } from './queries'

// "Ask the desk" (Stage 5.3, D47): `POST /api/agent/desk` streams the multi-agent desk's
// progress as Server-Sent Events. Everything the models wrote (reports, debate, rationale) is
// untrusted text and is rendered as plain text, never HTML.

type Schemas = components['schemas']
export type DeskRunEvent = Schemas['DeskRunEvent']
export type NodeStartEvent = Schemas['NodeStartEvent']
export type DeskToolStartEvent = Schemas['DeskToolStartEvent']
export type DeskToolEndEvent = Schemas['DeskToolEndEvent']
export type NodeEndEvent = Schemas['NodeEndEvent']
export type SignalEvent = Schemas['SignalEvent']
export type DeskDoneEvent = Schemas['DeskDoneEvent']
export type DeskErrorEvent = Schemas['DeskErrorEvent']
export type DeskReport = Schemas['DeskReport']
export type DeskCase = Schemas['DeskCase']
export type DeskSignal = Schemas['DeskSignal']
export type Validation = Schemas['Validation']
export type NodeUsage = Schemas['NodeUsage']
export type DeskRunState = Schemas['DeskRunState']
export type DeskEstimate = Schemas['DeskEstimate']
export type DeskNode = NodeStartEvent['node']

export type DeskEvent =
  | { event: 'desk'; data: DeskRunEvent }
  | { event: 'node_start'; data: NodeStartEvent }
  | { event: 'tool_start'; data: DeskToolStartEvent }
  | { event: 'tool_end'; data: DeskToolEndEvent }
  | { event: 'node_end'; data: NodeEndEvent }
  | { event: 'signal'; data: SignalEvent }
  | { event: 'done'; data: DeskDoneEvent }
  | { event: 'error'; data: DeskErrorEvent }

const DESK_EVENT_NAMES = new Set([
  'desk',
  'node_start',
  'tool_start',
  'tool_end',
  'node_end',
  'signal',
  'done',
  'error',
])

export const DESK_NODES: DeskNode[] = [
  'technical',
  'context',
  'bull_open',
  'bear_open',
  'bull_rebut',
  'bear_rebut',
  'head',
  'validator',
]

export const NODE_LABELS: Record<DeskNode, string> = {
  technical: 'Technical analyst',
  context: 'Context analyst',
  bull_open: 'Bull · opening',
  bear_open: 'Bear · opening',
  bull_rebut: 'Bull · rebuttal',
  bear_rebut: 'Bear · rebuttal',
  head: 'Head of desk',
  validator: 'Validator',
}

// --- The run as the UI shows it -----------------------------------------------------------------

export type NodeStatus = 'waiting' | 'running' | 'done' | 'unavailable' | 'failed'

export interface NodeView {
  status: NodeStatus
  report?: DeskReport
  case?: DeskCase
  error?: string | null
  usage?: NodeUsage
  tools: ToolCall[]
  /** How many times the node started (the head and validator can run twice). */
  runs: number
}

export interface DeskView {
  coin: string
  asOf: string | null
  model: string | null
  serverKey: boolean
  referenceClose: number | null
  referenceDate: string | null
  nodes: Record<DeskNode, NodeView>
  signal: DeskSignal | null
  validation: Validation | null
  done: DeskDoneEvent | null
  error: string | null
  snapshotId: number | null
  running: boolean
}

function emptyNodes(): Record<DeskNode, NodeView> {
  return Object.fromEntries(
    DESK_NODES.map((n) => [n, { status: 'waiting', tools: [], runs: 0 }]),
  ) as unknown as Record<DeskNode, NodeView>
}

export function emptyDesk(coin: string): DeskView {
  return {
    coin,
    asOf: null,
    model: null,
    serverKey: false,
    referenceClose: null,
    referenceDate: null,
    nodes: emptyNodes(),
    signal: null,
    validation: null,
    done: null,
    error: null,
    snapshotId: null,
    running: true,
  }
}

function withNode(view: DeskView, node: DeskNode, fn: (n: NodeView) => NodeView): DeskView {
  return { ...view, nodes: { ...view.nodes, [node]: fn(view.nodes[node]) } }
}

/** One event applied to the run being streamed. */
export function applyDeskEvent(view: DeskView, e: DeskEvent): DeskView {
  switch (e.event) {
    case 'desk':
      return {
        ...view,
        coin: e.data.coin,
        asOf: e.data.as_of ?? null,
        model: e.data.model,
        serverKey: e.data.server_key,
        referenceClose: e.data.reference_close ?? null,
        referenceDate: e.data.reference_date ?? null,
      }
    case 'node_start':
      return withNode(view, e.data.node, (n) => ({
        ...n,
        status: 'running',
        runs: n.runs + 1,
        error: null,
      }))
    case 'tool_start':
      return withNode(view, e.data.node, (n) => ({
        ...n,
        tools: [
          ...n.tools,
          {
            callId: e.data.call_id,
            name: e.data.name,
            args: e.data.args,
            snapshotId: null,
            ok: null,
            preview: null,
          },
        ],
      }))
    case 'tool_end':
      return withNode(view, e.data.node, (n) => ({
        ...n,
        tools: n.tools.map((t) =>
          t.callId === e.data.call_id
            ? { ...t, snapshotId: e.data.snapshot_id, ok: e.data.ok, preview: e.data.preview }
            : t,
        ),
      }))
    case 'node_end': {
      const d = e.data
      const next = withNode(view, d.node, (n) => ({
        ...n,
        status: d.status,
        report: d.report ?? n.report,
        case: d.case ?? n.case,
        error: d.error ?? null,
        usage: d.usage,
      }))
      if (d.node === 'head' && d.signal) return { ...next, signal: d.signal }
      if (d.node === 'validator' && d.validation) return { ...next, validation: d.validation }
      return next
    }
    case 'signal':
      return { ...view, signal: e.data.signal ?? null, validation: e.data.validation }
    case 'done':
      return { ...view, done: e.data, snapshotId: e.data.snapshot_id, running: false }
    case 'error':
      return {
        ...view,
        error: e.data.message,
        snapshotId: e.data.snapshot_id ?? null,
        running: false,
        nodes: Object.fromEntries(
          DESK_NODES.map((n) => [
            n,
            view.nodes[n].status === 'running'
              ? { ...view.nodes[n], status: 'failed' }
              : view.nodes[n],
          ]),
        ) as unknown as Record<DeskNode, NodeView>,
      }
    default:
      return view
  }
}

/** A saved run (the `desk_run` snapshot) as the same view. Tool calls aren't stored per node, so
 * history shows the reports without their tool cards. */
export function deskFromState(state: DeskRunState, snapshotId: number): DeskView {
  const nodes = emptyNodes()
  for (const u of state.usage ?? []) nodes[u.node] = { ...nodes[u.node], usage: u }
  for (const [name, r] of Object.entries(state.reports ?? {})) {
    const n = name as DeskNode
    nodes[n] = { ...nodes[n], status: r.status, report: r, runs: 1 }
  }
  for (const [name, c] of Object.entries(state.debate ?? {})) {
    const n = name as DeskNode
    nodes[n] = { ...nodes[n], status: 'done', case: c, runs: 1 }
  }
  const finished = state.status === 'valid' || state.status === 'invalid'
  const attempts = state.validation?.attempts ?? 0
  if (state.signal || finished)
    nodes.head = { ...nodes.head, status: 'done', runs: Math.max(1, attempts) }
  if (state.validation) nodes.validator = { ...nodes.validator, status: 'done', runs: attempts }
  if (state.status === 'error')
    for (const n of DESK_NODES)
      if (nodes[n].status === 'waiting' && nodes[n].usage)
        nodes[n] = { ...nodes[n], status: 'failed' }
  return {
    coin: state.coin,
    asOf: state.as_of ?? null,
    model: state.model,
    serverKey: false,
    referenceClose: state.reference_close ?? null,
    referenceDate: state.reference_date ?? null,
    nodes,
    signal: state.signal ?? null,
    validation: state.validation ?? null,
    done: null,
    error: state.status === 'error' ? (state.error ?? 'The run stopped.') : null,
    snapshotId,
    running: false,
  }
}

/** Every finding id the reports contain, to show citations that point nowhere. */
export function findingIds(view: DeskView): Set<string> {
  const ids = new Set<string>()
  for (const n of ['technical', 'context'] as const)
    for (const f of view.nodes[n].report?.findings ?? []) ids.add(f.id)
  return ids
}

export function stanceLabel(stance: DeskSignal['stance']): string {
  return stance === 'lean_long' ? 'Lean long' : 'Flat'
}

// --- API ----------------------------------------------------------------------------------------

export interface DeskInput {
  coin: string
  /** Null for the admin's server key (no key in this browser). */
  key: LlmKey | null
  model: string | null
}

/** Run the desk, calling `onEvent` for each event as it arrives. */
export async function streamDesk(
  input: DeskInput,
  onEvent: (event: DeskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const { response, error } = await api.POST('/api/agent/desk', {
    body: {
      coin: input.coin,
      provider: input.key?.provider ?? null,
      model: input.key ? input.model || null : null,
    },
    headers: keyHeader(input.key),
    parseAs: 'stream',
    signal,
  })
  if (!response.ok || !response.body) {
    const retry = Number(response.headers.get('Retry-After')) || null
    throw new ChatRequestError(
      response.status,
      detailOf(error) ?? `Request failed (${response.status})`,
      retry,
    )
  }
  await readEvents<DeskEvent>(response.body, DESK_EVENT_NAMES, onEvent)
}

/** Typical tokens (and USD, when the model has a known price) for one run. */
export function useDeskEstimate(key: LlmKey | null, model: string | null, enabled: boolean) {
  const provider = key?.provider ?? null
  return useQuery({
    queryKey: ['agent', 'desk-estimate', provider, model],
    queryFn: () =>
      unwrap(
        api.GET('/api/agent/desk/estimate', {
          params: { query: provider ? { provider, model: model || undefined } : {} },
        }),
      ),
    enabled,
    staleTime: Infinity,
  })
}
