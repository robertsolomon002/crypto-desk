// Shapes of the `/api/cycles` results (`analytics/cycles.py`) and the transforms the Cycles tab
// draws from. All dates are UTC days.

export type AnchorMode = 'halving' | 'bottom' | 'top'
export type YMode = 'multiple' | 'drawdown'

export interface PathRow {
  cycle: string
  day: number
  date: string
  close: number
  multiple: number
  drawdown: number // from the cycle's running ATH close
}

export interface DayNRow {
  cycle: string
  anchor_date: string
  anchor_price: number
  day: number
  date: string
  close: number
  multiple: number
  drawdown: number
  max_multiple: number
  min_multiple: number
  top_day: number | null
  reached_day_n: boolean
}

export interface DayN {
  mode: AnchorMode
  current_cycle: string
  day: number
  table: DayNRow[]
}

/** Return since the bottom (a fraction) at `d30` ... and at the current day N (`d<N>`). */
export type RoiRow = { cycle: string; bottom_date: string; bottom_price: number } & Record<
  `d${number}`,
  number | null
>

export interface YoyRow {
  year: number
  day: number // day of the year, 1 = Jan 1
  date: string
  close: number
  multiple: number
}

export interface CyclePath {
  cycle: string
  /** Day offset -> row, for the same-day hover lookup. */
  byDay: Map<number, PathRow>
  rows: PathRow[]
}

/** Paths grouped per cycle, oldest first, each sorted by day. */
export function groupPaths(rows: PathRow[]): CyclePath[] {
  const groups = new Map<string, PathRow[]>()
  for (const row of rows) {
    const list = groups.get(row.cycle)
    if (list) list.push(row)
    else groups.set(row.cycle, [row])
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([cycle, list]) => {
      const sorted = [...list].sort((a, b) => a.day - b.day)
      return { cycle, rows: sorted, byDay: new Map(sorted.map((r) => [r.day, r])) }
    })
}

export const yValue = (row: PathRow, mode: YMode): number =>
  mode === 'multiple' ? row.multiple : row.drawdown

/** Every cycle's row on the same day offset (cycles that have no such day are left out). */
export function rowsAtDay(paths: CyclePath[], day: number): { cycle: string; row: PathRow }[] {
  const out: { cycle: string; row: PathRow }[] = []
  for (const p of paths) {
    const row = p.byDay.get(day)
    if (row) out.push({ cycle: p.cycle, row })
  }
  return out
}

/** The ROI columns in day order: d30, d90, ... and the current day N last. */
export function roiColumns(rows: RoiRow[]): { key: `d${number}`; day: number }[] {
  const days = new Set<number>()
  for (const row of rows)
    for (const key of Object.keys(row)) {
      const m = /^d(\d+)$/.exec(key)
      if (m) days.add(Number(m[1]))
    }
  return [...days].sort((a, b) => a - b).map((day) => ({ key: `d${day}` as const, day }))
}

/** YoY rows grouped per year, oldest first. */
export function groupYears(rows: YoyRow[]): { year: number; rows: YoyRow[] }[] {
  const groups = new Map<number, YoyRow[]>()
  for (const row of rows) {
    const list = groups.get(row.year)
    if (list) list.push(row)
    else groups.set(row.year, [row])
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([year, list]) => ({ year, rows: [...list].sort((a, b) => a.day - b.day) }))
}

/** "Day 924 after the 2024-04-20 halving" style label for an anchor mode. */
export const ANCHOR_NAME: Record<AnchorMode, string> = {
  halving: 'halving',
  bottom: 'cycle bottom',
  top: 'cycle top',
}
