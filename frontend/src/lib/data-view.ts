// Pure helpers for the Data tab (Stage 3.4): filters from deep links, column kinds, analytics
// results flattened into rows, and CSV that neutralizes spreadsheet formulas like the backend's
// export does (OWASP CSV injection).

export interface ColumnInfo {
  name: string
  type: string // SQLAlchemy type as text: DOUBLE, INTEGER, NUMERIC(12, 6), DATE, DATETIME, ARRAY...
  filterable: boolean
}

export type Row = Record<string, unknown>

/** URL parameters that steer the view rather than filter a column. */
export const RESERVED = new Set([
  'table',
  'fn',
  'coin',
  'from',
  'to',
  'page',
  'size',
  'sort',
  'desc',
  'preview',
  'part',
  'allcoins',
  'snapshot',
])

export const isNumeric = (c: ColumnInfo) =>
  /^(DOUBLE|FLOAT|REAL|INTEGER|BIGINT|SMALLINT|NUMERIC)/.test(c.type)
export const isDateLike = (c: ColumnInfo) =>
  c.type === 'DATE' || c.type.startsWith('DATETIME') || c.type.startsWith('TIMESTAMP')

const DATE_PREFERENCE = [
  'date',
  'ts',
  'published_at',
  'week',
  'started_at',
  'resolved_at',
  'created_at',
]

/** The column the date range applies to: the table's main date, else its first date column. */
export function dateColumn(columns: ColumnInfo[]): ColumnInfo | null {
  const dated = columns.filter((c) => isDateLike(c) && c.filterable)
  for (const name of DATE_PREFERENCE) {
    const hit = dated.find((c) => c.name === name)
    if (hit) return hit
  }
  return dated[0] ?? null
}

/**
 * The column the coin filter applies to: `coin`, or the `coins` array on headlines. The `coins`
 * table's `symbol` is left alone, so the selected coin doesn't hide the other coins there.
 */
export function coinColumn(columns: ColumnInfo[]): ColumnInfo | null {
  return (
    columns.find((c) => c.name === 'coin') ??
    columns.find((c) => c.name === 'coins' && c.type === 'ARRAY') ??
    null
  )
}

const nextDay = (day: string) => {
  const d = new Date(`${day}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + 1)
  return d.toISOString().slice(0, 10)
}

/**
 * `column:op:value` filters for `/api/data/tables/{name}` from the view's parameters. `to` is
 * inclusive: on a timestamp column it becomes "before the next day" (UTC).
 */
export function buildFilters(
  columns: ColumnInfo[],
  params: {
    coin?: string | null
    from?: string | null
    to?: string | null
    extra?: [string, string][]
  },
): string[] {
  const out: string[] = []
  const coin = coinColumn(columns)
  if (params.coin && coin)
    out.push(`${coin.name}:${coin.type === 'ARRAY' ? 'contains' : 'eq'}:${params.coin}`)
  const date = dateColumn(columns)
  if (date && params.from) out.push(`${date.name}:gte:${params.from}`)
  if (date && params.to)
    out.push(
      date.type === 'DATE'
        ? `${date.name}:lte:${params.to}`
        : `${date.name}:lt:${nextDay(params.to)}`,
    )
  const byName = new Map(columns.map((c) => [c.name, c]))
  for (const [key, value] of params.extra ?? []) {
    const col = byName.get(key)
    if (col?.filterable && !RESERVED.has(key))
      out.push(`${key}:${col.type === 'ARRAY' ? 'contains' : 'eq'}:${value}`)
  }
  return out
}

/** A cell as text: dates and numbers as sent, arrays joined, objects as compact JSON. */
export function cellText(value: unknown): string {
  if (value == null) return ''
  if (Array.isArray(value)) return value.map(cellText).join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const FORMULA = /^[=+\-@\t\r]/

function csvCell(value: unknown): string {
  let text = cellText(value)
  // Numbers stay numbers (a negative return is not a formula); text gets the leading quote.
  if (typeof value !== 'number' && FORMULA.test(text)) text = `'${text}`
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function toCsv(columns: string[], rows: Row[]): string {
  return [
    columns.map(csvCell).join(','),
    ...rows.map((r) => columns.map((c) => csvCell(r[c])).join(',')),
  ].join('\r\n')
}

// --- Analytics results (computed, not stored; `table=analytics&fn=...`, D41) ---------------------

/** Nested objects become dotted columns: `{bottom: {date}}` -> `bottom.date`. */
function flatten(value: Row, prefix = '', out: Row = {}): Row {
  for (const [key, v] of Object.entries(value)) {
    const name = prefix ? `${prefix}.${key}` : key
    if (v && typeof v === 'object' && !Array.isArray(v)) flatten(v as Row, name, out)
    else out[name] = v
  }
  return out
}

const isRecordList = (v: unknown): v is Row[] =>
  Array.isArray(v) &&
  v.length > 0 &&
  v.every((x) => x !== null && typeof x === 'object' && !Array.isArray(x))

export interface ResultPart {
  name: string
  columns: string[]
  rows: Row[]
}

export interface ResultView {
  parts: ResultPart[]
  /** Single values beside the tables (current day N, mode, percentile...). */
  values: [string, unknown][]
}

function part(name: string, records: Row[]): ResultPart {
  const rows = records.map((r) => flatten(r))
  const columns: string[] = []
  for (const r of rows) for (const k of Object.keys(r)) if (!columns.includes(k)) columns.push(k)
  return { name, columns, rows }
}

/**
 * Any analytics result as tables: a list of records is one table; an object gives one table per
 * list of records in it (`matrix`, `summary`, `table`), a histogram from `bins` and `counts`,
 * and its single values.
 */
export function resultView(result: unknown): ResultView {
  if (isRecordList(result)) return { parts: [part('result', result)], values: [] }
  if (Array.isArray(result)) return { parts: [], values: [] }
  if (!result || typeof result !== 'object') return { parts: [], values: [['result', result]] }
  const obj = result as Row
  const parts: ResultPart[] = []
  const values: [string, unknown][] = []
  if (Array.isArray(obj.bins) && Array.isArray(obj.counts)) {
    const bins = obj.bins as number[]
    parts.push(
      part(
        'histogram',
        (obj.counts as number[]).map((count, i) => ({
          bin_from: bins[i],
          bin_to: bins[i + 1],
          count,
        })),
      ),
    )
  }
  for (const [key, v] of Object.entries(obj)) {
    if (key === 'bins' || key === 'counts') continue
    if (isRecordList(v)) parts.push(part(key, v))
    else if (v && typeof v === 'object' && !Array.isArray(v))
      for (const [k, x] of Object.entries(flatten(v as Row))) values.push([`${key}.${k}`, x])
    else if (!Array.isArray(v)) values.push([key, v])
  }
  return { parts, values }
}

/** What each analytics result is, for the Data tab's list (registry names, `analytics/registry.py`). */
export const ANALYTICS: {
  fn: string
  label: string
  params?: Record<string, readonly string[]>
}[] = [
  { fn: 'cycles_anchors', label: 'Cycle anchors (bottom, halving, top)' },
  {
    fn: 'cycles_paths',
    label: 'Cycle paths by day since anchor',
    params: { mode: ['halving', 'bottom', 'top'] },
  },
  {
    fn: 'cycles_day_n',
    label: 'Every cycle at the current day N',
    params: { mode: ['halving', 'bottom', 'top'] },
  },
  { fn: 'roi_since_bottom', label: 'Return since each cycle bottom' },
  { fn: 'yoy', label: 'Year-over-year paths' },
  { fn: 'seasonality_monthly', label: 'Monthly returns (year x month)' },
  { fn: 'seasonality_weekly', label: 'ISO-week returns' },
  { fn: 'seasonality_dow', label: 'Day-of-week returns' },
  {
    fn: 'return_distribution',
    label: 'Return distribution',
    params: { horizon: ['1w', '1d', '30d'] },
  },
  { fn: 'drawdowns', label: 'Drawdown from the running ATH' },
  { fn: 'drawdown_episodes', label: 'Deepest drawdowns' },
  { fn: 'rolling_volatility', label: 'Rolling 30/90-day volatility' },
  {
    fn: 'rolling_correlation',
    label: 'Rolling correlation between coins',
    params: { window: ['90', '30', '180'] },
  },
  { fn: 'onchain', label: 'On-chain: MVRV, realized price, NUPL, addresses, hash rate (BTC, ETH)' },
]

// --- Agent snapshots (Stage 5.2) ----------------------------------------------------------------

const isCompactTable = (v: unknown): v is { columns: string[]; rows: unknown[][] } =>
  !!v &&
  typeof v === 'object' &&
  Array.isArray((v as Row).columns) &&
  ((v as Row).columns as unknown[]).every((c) => typeof c === 'string') &&
  Array.isArray((v as Row).rows) &&
  ((v as Row).rows as unknown[]).every(Array.isArray)

/** desk-mcp writes long series as `{columns, rows, total_rows}` (D44); turn those into records. */
export function expandCompact(value: unknown): unknown {
  if (isCompactTable(value)) {
    const { columns, rows } = value
    return rows.map((r) => Object.fromEntries(columns.map((c, i) => [c, r[i]])))
  }
  if (Array.isArray(value)) return value.map(expandCompact)
  if (value && typeof value === 'object') {
    const out: Row = {}
    for (const [k, v] of Object.entries(value as Row)) out[k] = expandCompact(v)
    return out
  }
  return value
}

export interface SnapshotResult {
  asOf: string | null
  sources: string[]
  error: string | null
  view: ResultView
}

/** A tool result (`{as_of, sources, data}`, or `{error}` for a failed call) as tables. */
export function snapshotView(result: unknown): SnapshotResult {
  const r = (result && typeof result === 'object' ? result : {}) as Row
  const sources = Array.isArray(r.sources) ? r.sources.map((s) => cellText(s)) : []
  const error = typeof r.error === 'string' ? r.error : null
  const data = 'data' in r ? r.data : error || 'as_of' in r ? undefined : result
  let view = resultView(expandCompact(data))
  // A bare record (one coin's regime, say) reads better as a one-row table than as values.
  if (view.parts.length === 0 && view.values.length > 0 && data && typeof data === 'object')
    view = { parts: [part('result', [data as Row])], values: [] }
  return { asOf: typeof r.as_of === 'string' ? r.as_of : null, sources, error, view }
}
