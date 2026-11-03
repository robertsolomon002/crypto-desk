import { describe, expect, it } from 'vitest'

import { DESK_DONE, DESK_SIGNAL, DESK_STREAM } from './__fixtures__/desk'
import { turnsFromDetail } from './agent'
import {
  applyDeskEvent,
  deskFromState,
  emptyDesk,
  findingIds,
  type DeskEvent,
  type DeskRunState,
} from './desk'

const events = DESK_STREAM.map(([event, data]) => ({ event, data }) as DeskEvent)
const replay = (upTo = events.length) =>
  events.slice(0, upTo).reduce(applyDeskEvent, emptyDesk('SOL'))

describe('applyDeskEvent', () => {
  it('builds the whole run from the stream', () => {
    const view = replay()
    expect(view.running).toBe(false)
    expect(view.referenceClose).toBe(91.83)
    expect(view.nodes.technical.status).toBe('done')
    expect(view.nodes.technical.tools).toEqual([
      expect.objectContaining({ name: 'get_key_levels', snapshotId: 38, ok: true }),
    ])
    expect(view.nodes.context.status).toBe('unavailable')
    expect(view.nodes.context.report?.note).toContain('60 seconds')
    expect(view.nodes.bear_rebut.case?.points[0].text).toBe('bear rebuttal point')
    expect(view.nodes.head.runs).toBe(2)
    expect(view.nodes.validator.runs).toBe(2)
    expect(view.signal).toEqual(DESK_SIGNAL)
    expect(view.validation).toEqual({ ok: true, errors: [], attempts: 2 })
    expect(view.done).toEqual(DESK_DONE)
    expect(view.snapshotId).toBe(40)
  })

  it('shows the first rejected signal until the retry lands', () => {
    const firstVerdict = DESK_STREAM.findIndex(
      ([e, d]) => e === 'node_end' && (d as { node: string }).node === 'validator',
    )
    const view = replay(firstVerdict + 1)
    expect(view.signal?.target).toBe(91)
    expect(view.validation?.ok).toBe(false)
    expect(view.running).toBe(true)
  })

  it('marks running nodes failed on an error and keeps the partial snapshot', () => {
    const headStarted = DESK_STREAM.findIndex(
      ([e, d]) => e === 'node_start' && (d as { node: string }).node === 'head',
    )
    const view = applyDeskEvent(replay(headStarted + 1), {
      event: 'error',
      data: { code: 'timeout', message: 'The head ran out of time.', snapshot_id: 41 },
    })
    expect(view.nodes.head.status).toBe('failed')
    expect(view.nodes.bull_open.status).toBe('done')
    expect(view.error).toBe('The head ran out of time.')
    expect(view.snapshotId).toBe(41)
    expect(view.running).toBe(false)
  })

  it('collects the finding ids the debate may cite', () => {
    expect([...findingIds(replay())].sort()).toEqual(['T1', 'T2'])
  })
})

describe('deskFromState', () => {
  const state: DeskRunState = {
    coin: 'SOL',
    as_of: null,
    model: 'claude-haiku-5-5',
    status: 'valid',
    error: null,
    reference_close: 91.83,
    reference_date: '2026-11-02',
    reports: {
      technical: replay().nodes.technical.report!,
      context: replay().nodes.context.report!,
    },
    debate: { bull_open: replay().nodes.bull_open.case! },
    signal: DESK_SIGNAL as DeskRunState['signal'],
    validation: { ok: true, errors: [], attempts: 2 },
    usage: [
      {
        node: 'head',
        tokens_in: 5000,
        tokens_out: 400,
        model_calls: 2,
        tool_calls: 0,
        cost_usd: null,
      },
    ],
  }

  it('turns a saved run into the same view', () => {
    const view = deskFromState(state, 40)
    expect(view.nodes.technical.status).toBe('done')
    expect(view.nodes.context.status).toBe('unavailable')
    expect(view.nodes.bull_open.status).toBe('done')
    expect(view.nodes.head).toMatchObject({ status: 'done', runs: 2 })
    expect(view.nodes.head.usage?.tokens_in).toBe(5000)
    expect(view.signal?.stance).toBe('lean_long')
    expect(view.running).toBe(false)
    expect(view.error).toBeNull()
  })

  it('reports a stopped run', () => {
    const view = deskFromState(
      { ...state, status: 'error', error: 'It stopped.', signal: null, validation: null },
      41,
    )
    expect(view.error).toBe('It stopped.')
    expect(view.nodes.head.status).toBe('failed')
  })
})

describe('turnsFromDetail', () => {
  it('finds a desk run among the answer snapshots', () => {
    const turns = turnsFromDetail({
      id: 30,
      title: 'Ask the desk: SOL',
      created_at: '2026-11-03T00:00:00Z',
      messages: [
        {
          id: 1,
          role: 'user',
          content: 'Ask the desk: SOL',
          model: null,
          created_at: '2026-11-03T00:00:00Z',
          snapshots: [],
        },
        {
          id: 2,
          role: 'assistant',
          content: 'summary',
          model: 'm',
          created_at: '2026-11-03T00:00:01Z',
          snapshots: [
            { id: 38, tool: 'get_key_levels', created_at: '2026-11-03T00:00:00Z' },
            { id: 40, tool: 'desk_run', created_at: '2026-11-03T00:00:01Z' },
          ],
        },
      ],
    })
    expect(turns[1].deskSnapshotId).toBe(40)
    expect(turns[1].tools.map((t) => t.name)).toEqual(['get_key_levels'])
    expect(turns[0].deskSnapshotId).toBeUndefined()
  })
})
