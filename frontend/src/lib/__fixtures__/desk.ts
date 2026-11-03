// A short "Ask the desk" stream (Stage 5.3) for component and Playwright tests. Model text in
// it includes HTML that must never render.

const usage = (node: string, tokens = 1000) => ({
  node,
  tokens_in: tokens,
  tokens_out: 100,
  model_calls: 1,
  tool_calls: 0,
  cost_usd: null,
})

const report = (analyst: 'technical' | 'context', prefix: string) => ({
  analyst,
  status: 'done',
  summary: `${analyst} summary <img src=x onerror=alert(1)>`,
  findings: [
    { id: `${prefix}1`, claim: `${analyst} finding one`, value: '91.83 USD', tool: 'get_ohlcv' },
    { id: `${prefix}2`, claim: `${analyst} finding two`, value: null, tool: null },
  ],
  note: null,
})

const caseOf = (side: 'bull' | 'bear', phase: 'opening' | 'rebuttal') => ({
  side,
  phase,
  points: [
    { text: `${side} ${phase} point`, cites: ['T1', 'C9'], unknown_cites: ['C9'] },
  ],
})

export const DESK_SIGNAL = {
  coin: 'SOL',
  stance: 'lean_long',
  confidence: 0.58,
  entry_low: 90,
  entry_high: 92,
  invalidation: 86,
  target: 100,
  rationale: 'Support holds near the 200-day SMA.',
  cites: ['T1', 'C1'],
}

export const DESK_DONE = {
  message_id: 31,
  snapshot_id: 40,
  status: 'valid',
  model: 'anthropic/claude-haiku-5.5',
  tokens_in: 48000,
  tokens_out: 4500,
  model_calls: 11,
  tool_calls: 2,
  cost_usd: null,
  usage: [],
}

export const DESK_STREAM: [string, unknown][] = [
  [
    'desk',
    {
      conversation_id: 30,
      title: 'Ask the desk: SOL',
      coin: 'SOL',
      as_of: null,
      model: 'anthropic/claude-haiku-5.5',
      server_key: false,
      reference_close: 91.83,
      reference_date: '2026-11-02',
    },
  ],
  ['node_start', { node: 'technical' }],
  ['node_start', { node: 'context' }],
  [
    'tool_start',
    { node: 'technical', call_id: 't1', name: 'get_key_levels', args: { coin: 'SOL' } },
  ],
  [
    'tool_end',
    {
      node: 'technical',
      call_id: 't1',
      name: 'get_key_levels',
      snapshot_id: 38,
      ok: true,
      preview: '{"as_of":"2026-11-02","sources":[],"data":{',
    },
  ],
  [
    'node_end',
    { node: 'context', status: 'unavailable', usage: usage('context', 0),
      report: { analyst: 'context', status: 'unavailable', summary: '', findings: [],
                note: 'took longer than 60 seconds' } },
  ],
  ['node_end', { node: 'technical', status: 'done', usage: usage('technical'), report: report('technical', 'T') }],
  ['node_start', { node: 'bull_open' }],
  ['node_start', { node: 'bear_open' }],
  ['node_end', { node: 'bull_open', status: 'done', usage: usage('bull_open'), case: caseOf('bull', 'opening') }],
  ['node_end', { node: 'bear_open', status: 'done', usage: usage('bear_open'), case: caseOf('bear', 'opening') }],
  ['node_start', { node: 'bull_rebut' }],
  ['node_start', { node: 'bear_rebut' }],
  ['node_end', { node: 'bull_rebut', status: 'done', usage: usage('bull_rebut'), case: caseOf('bull', 'rebuttal') }],
  ['node_end', { node: 'bear_rebut', status: 'done', usage: usage('bear_rebut'), case: caseOf('bear', 'rebuttal') }],
  ['node_start', { node: 'head' }],
  ['node_end', { node: 'head', status: 'done', usage: usage('head'), signal: { ...DESK_SIGNAL, target: 91 } }],
  ['node_start', { node: 'validator' }],
  [
    'node_end',
    { node: 'validator', status: 'done', usage: usage('validator', 0),
      validation: { ok: false, errors: ['target 91 must be above entry_high 92.'], attempts: 1 } },
  ],
  ['node_start', { node: 'head' }],
  ['node_end', { node: 'head', status: 'done', usage: usage('head', 2000), signal: DESK_SIGNAL }],
  ['node_start', { node: 'validator' }],
  [
    'node_end',
    { node: 'validator', status: 'done', usage: usage('validator', 0),
      validation: { ok: true, errors: [], attempts: 2 } },
  ],
  ['signal', { signal: DESK_SIGNAL, validation: { ok: true, errors: [], attempts: 2 } }],
  ['done', DESK_DONE],
]
