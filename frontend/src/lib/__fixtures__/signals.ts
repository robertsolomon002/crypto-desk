// Made-up signals (Stage 7.2) for component and Playwright tests. Model text in them includes
// HTML that must never render.

const outcome = (hit: boolean, close: number, first: string | null, pnl: number) => ({
  reference_close: 100,
  week_close: close,
  direction_hit: hit,
  first_hit: first,
  paper_pnl: pnl,
  brier: hit ? 0.16 : 0.36,
  resolved_at: '2026-10-27T00:20:00Z',
})

let nextId = 1
export const signal = (
  week: string,
  coin: string,
  source: 'desk' | 'coinflip' | 'trend' | 'mco',
  extra: Record<string, unknown> = {},
) => ({
  id: nextId++,
  version: 1,
  week,
  coin,
  source,
  stance: 'flat',
  confidence: 0.5,
  entry_low: null,
  entry_high: null,
  invalidation: null,
  target: null,
  rationale: null,
  has_debate: false,
  hash: 'a'.repeat(64),
  created_at: `${week}T00:16:00Z`,
  outcome: null,
  ...extra,
})

const OPEN = '2026-10-26'
const DONE = '2026-10-19'

export const WEEK_SIGNALS = [
  signal(OPEN, 'BTC', 'desk', {
    stance: 'lean_long',
    confidence: 0.6,
    entry_low: 95,
    entry_high: 98,
    invalidation: 90,
    target: 110,
    rationale: 'Made-up rationale <img src=x onerror=alert(1)>',
    has_debate: true,
  }),
  signal(OPEN, 'BTC', 'coinflip'),
  signal(OPEN, 'BTC', 'trend', { stance: 'lean_long', confidence: 0.6 }),
  signal(OPEN, 'BTC', 'mco', { stance: 'lean_long', confidence: 0.7, invalidation: 80, target: 120 }),
  signal(OPEN, 'ETH', 'desk', { confidence: 0.55 }),
  signal(OPEN, 'ETH', 'coinflip'),
]

export const WEEK = {
  week: OPEN,
  version: 1,
  resolves_on: '2026-11-03',
  withheld: null,
  brief: {
    id: 1,
    week: OPEN,
    model: 'claude-sonnet-5-5',
    prompt_version: 'brief_v1',
    created_at: '2026-10-26T00:18:00Z',
    content: '# Brief',
    summary: [
      'Summary line one <b>not bold</b>',
      'Summary line two',
      'Summary line three',
      'Summary line four',
      'Summary line five',
    ],
    coins: [
      {
        coin: 'BTC',
        setup: 'Made-up BTC setup.',
        bull_case: 'Made-up bull case.',
        bear_case: 'Made-up bear case.',
        what_would_change: 'A daily close below 90.',
        levels_to_watch: [{ label: 'desk invalidation', price: 90 }],
      },
    ],
  },
  signals: WEEK_SIGNALS,
}

export const HISTORY = [
  ...WEEK_SIGNALS,
  signal(DONE, 'BTC', 'desk', {
    stance: 'lean_long',
    confidence: 0.6,
    invalidation: 90,
    target: 104,
    outcome: outcome(true, 105, 'target', 0.036),
  }),
  signal(DONE, 'BTC', 'coinflip', { outcome: outcome(false, 105, null, 0) }),
]

const stats = (n: number, hits: number, pnl: number, extra = {}) => ({
  signals: n,
  weeks: n,
  hits,
  hit_rate: n ? hits / n : null,
  brier: 0.2,
  with_levels: 1,
  target_first: 1,
  invalidation_first: 0,
  neither: 0,
  target_first_rate: 1,
  long_weeks: 1,
  paper_return: pnl,
  early_days: true,
  ...extra,
})

const point = (week: string, pnl: number) => ({
  week,
  signals: 1,
  hit_rate: 1,
  brier: 0.16,
  paper_return: pnl,
})

export const SCORECARD = {
  version: 1,
  early_weeks: 12,
  paper_cost_per_side: 0.002,
  weeks: ['2026-10-12', DONE],
  sources: [
    {
      source: 'desk',
      stats: stats(2, 2, 0.05),
      coins: [{ coin: 'BTC', stats: stats(2, 2, 0.05) }],
      cumulative: [point('2026-10-12', 0.014), point(DONE, 0.05)],
    },
    {
      source: 'coinflip',
      stats: stats(2, 1, 0, { with_levels: 0, target_first: 0, target_first_rate: null, long_weeks: 0 }),
      coins: [{ coin: 'BTC', stats: stats(2, 1, 0) }],
      cumulative: [point('2026-10-12', 0), point(DONE, 0)],
    },
  ],
}

export const WEEKS = {
  version: 1,
  versions: [1],
  weeks: [
    { week: OPEN, signals: 6, resolved: 0, has_brief: true },
    { week: DONE, signals: 2, resolved: 2, has_brief: false },
  ],
}

export const DEBATE = {
  coin: 'BTC',
  as_of: '2026-10-25',
  model: 'claude-haiku-5-5',
  status: 'valid',
  error: null,
  reference_close: 100,
  reference_date: '2026-10-25',
  reports: {
    technical: {
      analyst: 'technical',
      status: 'done',
      summary: 'Made-up technical report',
      findings: [{ id: 'T1', claim: 'Above the 20W SMA', value: null, tool: null }],
      note: null,
    },
  },
  debate: {
    bull_open: {
      side: 'bull',
      phase: 'opening',
      points: [{ text: 'Made-up bull point', cites: ['T1'], unknown_cites: [] }],
    },
  },
  signal: {
    coin: 'BTC',
    stance: 'lean_long',
    confidence: 0.6,
    entry_low: 95,
    entry_high: 98,
    invalidation: 90,
    target: 110,
    rationale: 'Made-up rationale',
    cites: ['T1'],
  },
  validation: { ok: true, errors: [], attempts: 1 },
  usage: [],
}
