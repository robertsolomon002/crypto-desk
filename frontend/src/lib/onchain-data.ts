import type { Span } from './stats-data'

// Shapes and pure helpers for the On-chain & Macro tab (Stage 4.1). Rows come from
// `/api/onchain/{coin}` (Coin Metrics, D21), `/api/macro` (FRED with release lags, D32),
// `/api/macro/fng` and `/api/macro/dominance`. Everything here is trailing (causal): a readout
// uses only rows up to its own last date.

export interface OnchainRow {
  date: string
  mvrv: number | null
  market_cap: number | null
  realized_cap: number | null
  realized_price: number | null
  nupl: number | null
  supply: number | null
  active_addresses: number | null
  hash_rate: number | null // TH/s for BTC (Coin Metrics docs)
}

export type MacroRow = { date: string } & Record<string, number | string | null>
export type DominanceRow = { date: string; btc: number | null; eth: number | null }
export type Point = [string, number | null] // UTC date, value

/** Free Coin Metrics community data covers BTC and ETH only (D21); other coins show BTC. */
export const ONCHAIN_COINS = ['BTC', 'ETH'] as const
export type OnchainCoin = (typeof ONCHAIN_COINS)[number]
export const onchainCoin = (coin: string): OnchainCoin =>
  (ONCHAIN_COINS as readonly string[]).includes(coin) ? (coin as OnchainCoin) : 'BTC'

/** `[date, value]` pairs for one column, skipping rows where it is missing. */
export function points<T extends { date: string }>(rows: T[], get: (r: T) => unknown): Point[] {
  const out: Point[] = []
  for (const r of rows) {
    const v = get(r)
    if (typeof v === 'number' && Number.isFinite(v)) out.push([r.date.slice(0, 10), v])
  }
  return out
}

/** Points in the last 4 years or 1 year before the final point (like `sinceSpan` on Stats). */
export function trimPoints(pts: Point[], span: Span): Point[] {
  if (span === 'all' || pts.length === 0) return pts
  const last = new Date(`${pts[pts.length - 1][0]}T00:00:00Z`)
  last.setUTCFullYear(last.getUTCFullYear() - (span === '4y' ? 4 : 1))
  const start = last.toISOString().slice(0, 10)
  return pts.filter(([d]) => d >= start)
}

/** Trailing mean over the last `n` points (null until `n` points exist). */
export function rollingMean(pts: Point[], n: number): Point[] {
  let sum = 0
  let count = 0
  return pts.map(([d, v], i) => {
    if (v != null) {
      sum += v
      count += 1
    }
    const old = i >= n ? pts[i - n][1] : null
    if (old != null) {
      sum -= old
      count -= 1
    }
    return [d, i >= n - 1 && count === n ? sum / n : null]
  })
}

/** Share of `values` at or below `v`, as a 0 to 100 percentile. */
export function percentileOf(values: number[], v: number): number | null {
  if (!values.length) return null
  let below = 0
  for (const x of values) if (x <= v) below += 1
  return (below / values.length) * 100
}

/**
 * Year-over-year change of a series dated on the first of each month (FRED M2SL): each value
 * against the value dated exactly one year earlier.
 */
export function yoyChange(pts: Point[]): Point[] {
  const byDate = new Map(pts.map(([d, v]) => [d, v]))
  const out: Point[] = []
  for (const [d, v] of pts) {
    const prev = byDate.get(`${Number(d.slice(0, 4)) - 1}${d.slice(4)}`)
    if (v != null && prev != null && prev !== 0) out.push([d, v / prev - 1])
  }
  return out
}

/** The NUPL zone names commonly used for Bitcoin (a convention, not a data fact; D43). */
export const NUPL_ZONES = [
  { from: -Infinity, to: 0, label: 'Capitulation' },
  { from: 0, to: 0.25, label: 'Hope / fear' },
  { from: 0.25, to: 0.5, label: 'Optimism / anxiety' },
  { from: 0.5, to: 0.75, label: 'Belief / denial' },
  { from: 0.75, to: Infinity, label: 'Euphoria / greed' },
] as const

export const nuplZone = (v: number) =>
  NUPL_ZONES.find((z) => v >= z.from && v < z.to)?.label ?? NUPL_ZONES[0].label

// --- Correlation with BTC ------------------------------------------------------------------------

export type Freq = 'week' | 'month'
/** `log`: log changes (an index, money supply); `diff`: plain differences (rates in percent). */
export type ChangeMode = 'log' | 'diff'

const DAY_MS = 86_400_000

/** The period a UTC date falls in: its Monday (UTC weeks, D33) or its month. */
export function periodKey(date: string, freq: Freq): string {
  if (freq === 'month') return date.slice(0, 7)
  const t = Date.parse(`${date.slice(0, 10)}T00:00:00Z`)
  const weekday = (new Date(t).getUTCDay() + 6) % 7 // Monday = 0
  return new Date(t - weekday * DAY_MS).toISOString().slice(0, 10)
}

/** The last value in each period, in date order. */
function lastPerPeriod(pts: Point[], freq: Freq): Map<string, number> {
  const out = new Map<string, number>()
  for (const [d, v] of pts) if (v != null) out.set(periodKey(d, freq), v)
  return out
}

export function pearson(xs: number[], ys: number[]): number | null {
  const n = xs.length
  if (n < 3 || ys.length !== n) return null
  const mx = xs.reduce((a, b) => a + b, 0) / n
  const my = ys.reduce((a, b) => a + b, 0) / n
  let sxy = 0
  let sxx = 0
  let syy = 0
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx
    const dy = ys[i] - my
    sxy += dx * dy
    sxx += dx * dx
    syy += dy * dy
  }
  if (sxx === 0 || syy === 0) return null // a flat series (fed funds between moves)
  return sxy / Math.sqrt(sxx * syy)
}

export interface Correlation {
  r: number | null
  n: number // number of period changes used
  from: string | null // first and last period
  to: string | null
}

/**
 * Pearson correlation between BTC's log change and the series' change over the last `periods`
 * periods both have. BTC's latest period may still be in progress, so it is left out. A change
 * is taken between consecutive common periods, so a missing FRED week is skipped, not spanned.
 */
export function changeCorrelation(
  btc: Point[],
  series: Point[],
  { freq, periods, mode }: { freq: Freq; periods: number; mode: ChangeMode },
): Correlation {
  const b = lastPerPeriod(btc, freq)
  const latest = [...b.keys()].pop()
  if (latest) b.delete(latest)
  const s = lastPerPeriod(series, freq)
  const keys = [...b.keys()].filter((k) => s.has(k))
  const xs: number[] = []
  const ys: number[] = []
  const used: string[] = []
  for (let i = 1; i < keys.length; i++) {
    const [p, k] = [keys[i - 1], keys[i]]
    const [b0, b1, s0, s1] = [b.get(p)!, b.get(k)!, s.get(p)!, s.get(k)!]
    if (b0 <= 0 || b1 <= 0 || (mode === 'log' && (s0 <= 0 || s1 <= 0))) continue
    xs.push(Math.log(b1 / b0))
    ys.push(mode === 'log' ? Math.log(s1 / s0) : s1 - s0)
    used.push(k)
  }
  const start = Math.max(0, xs.length - periods)
  const tail = used.slice(start)
  return {
    r: pearson(xs.slice(start), ys.slice(start)),
    n: tail.length,
    from: tail[0] ?? null,
    to: tail[tail.length - 1] ?? null,
  }
}

/** How each FRED series is compared with BTC, and the two windows its readout shows. */
export const MACRO_SPECS: Record<
  string,
  { mode: ChangeMode; freq: Freq; windows: [number, string][]; explainer: string }
> = {
  DTWEXBGS: {
    mode: 'log',
    freq: 'week',
    windows: [
      [52, '1Y'],
      [208, '4Y'],
    ],
    explainer:
      'The trade-weighted value of the US dollar against a broad basket of currencies. A ' +
      'stronger dollar tightens global financial conditions and has often coincided with ' +
      'weaker crypto prices.',
  },
  DGS10: {
    mode: 'diff',
    freq: 'week',
    windows: [
      [52, '1Y'],
      [208, '4Y'],
    ],
    explainer:
      'The market yield on 10-year US Treasury notes. Rising yields raise the return on ' +
      'risk-free assets and the discount rate applied to risky ones.',
  },
  DFF: {
    mode: 'diff',
    freq: 'week',
    windows: [
      [52, '1Y'],
      [208, '4Y'],
    ],
    explainer:
      'The overnight rate banks charge each other, steered by the Federal Reserve. It moves ' +
      'only around FOMC decisions, so its weekly changes are mostly zero and the correlation ' +
      'can be undefined.',
  },
  M2SL: {
    mode: 'log',
    freq: 'month',
    windows: [
      [36, '3Y'],
      [120, '10Y'],
    ],
    explainer:
      'Cash, deposits and other near-money in the US, seasonally adjusted and published ' +
      'monthly. Its year-over-year growth is a common gauge of liquidity.',
  },
}

/** Correlation readout units: "weekly changes" or "monthly changes". */
export const FREQ_TEXT: Record<Freq, string> = { week: 'weekly', month: 'monthly' }

/** Overlay list kept in the URL (`?overlay=DGS10,M2SL`): known ids only, in a stable order. */
export function parseOverlay(raw: string | null, known: readonly string[]): string[] {
  const wanted = new Set((raw ?? '').split(','))
  return known.filter((id) => wanted.has(id))
}

export function toggleOverlay(list: string[], id: string, known: readonly string[]): string[] {
  const next = new Set(list)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  return known.filter((k) => next.has(k))
}
