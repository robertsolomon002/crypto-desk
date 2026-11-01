// Shapes of the `/api/stats` results (`analytics/seasonality.py`, `analytics/stats.py`) and the
// transforms the Stats tab draws from. Returns are fractions (0.012 = +1.2%).

export interface SummaryRow {
  month?: number // 1..12 (monthly)
  week?: number // ISO week 1..53 (weekly)
  weekday?: number // 0 = Monday (day of week)
  mean: number | null
  median: number | null
  pct_positive: number | null
  count: number
}

/** A matrix row: the year plus one key per month ("1".."12") or ISO week ("1".."53"). */
export type MatrixRow = { year: number } & Record<string, number | null>

export interface Seasonality {
  matrix: MatrixRow[]
  summary: SummaryRow[]
}

export interface Distribution {
  horizon: '1d' | '1w' | '30d'
  count: number
  mean: number | null
  std: number | null
  quantiles: Record<string, number | null>
  bins: number[] // edges, one more than counts
  counts: number[]
  current_date: string | null
  current: number | null
  current_percentile: number | null
}

export interface DrawdownRow {
  date: string
  close: number
  peak: number
  drawdown: number
}

export interface Episode {
  peak_date: string
  peak: number
  trough_date: string
  trough: number
  depth: number
  recovery_date: string | null
  days: number
}

export interface VolRow {
  date: string
  vol30: number | null
  vol90: number | null
}

/** A date plus one key per coin pair ("BTC/ETH"). */
export type CorrRow = { date: string } & Record<string, number | null>

export const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const

/**
 * The period number of each summary row. Older cached results (before Stage 3.3) dropped the
 * `month`/`weekday` key, so the position is the fallback: months start at 1, weekdays at 0.
 */
export function periodOf(row: SummaryRow, index: number, kind: 'monthly' | 'weekly' | 'dow') {
  if (kind === 'monthly') return row.month ?? index + 1
  if (kind === 'weekly') return row.week ?? index + 1
  return row.weekday ?? index
}

/** Heatmap cells `[monthIndex, yearIndex, value]` for the year x month matrix, oldest year first. */
export function heatmapCells(matrix: MatrixRow[]): {
  years: number[]
  cells: [number, number, number][]
} {
  const rows = [...matrix].sort((a, b) => a.year - b.year)
  const cells: [number, number, number][] = []
  rows.forEach((row, y) => {
    for (let m = 1; m <= 12; m++) {
      const v = row[String(m)]
      if (v != null && Number.isFinite(v)) cells.push([m - 1, y, v])
    }
  })
  return { years: rows.map((r) => r.year), cells }
}

/** The histogram bin holding `value` (the last bin includes its right edge), or -1. */
export function binIndex(bins: number[], value: number | null): number {
  if (value == null || bins.length < 2) return -1
  if (value < bins[0] || value > bins[bins.length - 1]) return -1
  for (let i = 0; i < bins.length - 1; i++) if (value < bins[i + 1]) return i
  return bins.length - 2
}

/** Coin-pair keys of a correlation row ("BTC/ETH"), in the order the API gives them. */
export const pairKeys = (rows: CorrRow[]): string[] =>
  rows.length ? Object.keys(rows[0]).filter((k) => k !== 'date') : []

/**
 * The latest value of every pair as a symmetric matrix over the coins, `coin` first. A pair
 * without a value yet stays null; the diagonal is 1.
 */
export function correlationMatrix(
  rows: CorrRow[],
  coin: string,
): { coins: string[]; values: (number | null)[][]; date: string | null } {
  const keys = pairKeys(rows)
  const coins = [...new Set(keys.flatMap((k) => k.split('/')))]
  coins.sort((a, b) => (a === coin ? -1 : b === coin ? 1 : 0))
  const latest = new Map<string, number>()
  let date: string | null = null
  for (const key of keys) {
    for (let i = rows.length - 1; i >= 0; i--) {
      const v = rows[i][key]
      if (v != null && Number.isFinite(v)) {
        latest.set(key, v)
        if (!date || rows[i].date > date) date = rows[i].date
        break
      }
    }
  }
  const get = (a: string, b: string) =>
    a === b ? 1 : (latest.get(`${a}/${b}`) ?? latest.get(`${b}/${a}`) ?? null)
  return { coins, values: coins.map((a) => coins.map((b) => get(a, b))), date }
}

export type Span = 'all' | '4y' | '1y'

/** Rows on or after the span's start, counted back from the last row's date. */
export function sinceSpan<T extends { date: string }>(rows: T[], span: Span): T[] {
  if (span === 'all' || rows.length === 0) return rows
  const last = new Date(`${rows[rows.length - 1].date.slice(0, 10)}T00:00:00Z`)
  last.setUTCFullYear(last.getUTCFullYear() - (span === '4y' ? 4 : 1))
  const start = last.toISOString().slice(0, 10)
  return rows.filter((r) => r.date >= start)
}

/** "1st", "2nd", "29th" for a percentile. */
export function ordinal(n: number): string {
  const r = Math.round(n)
  const teen = r % 100 >= 11 && r % 100 <= 13
  const suffix = teen ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[r % 10]
  return `${r}${suffix ?? 'th'}`
}
