import { describe, expect, it } from 'vitest'

import { cycleOverlayOption, dayLabel, yoyOption } from './cycle-options'
import { readChartColors } from './chart-colors'
import {
  groupPaths,
  groupYears,
  roiColumns,
  rowsAtDay,
  type PathRow,
  type RoiRow,
} from './cycles-data'
import { formatMultiple } from './format'

const row = (cycle: string, day: number, multiple: number, drawdown = 0): PathRow => ({
  cycle,
  day,
  date: `2020-01-${String(day + 1).padStart(2, '0')}`,
  close: 100 * multiple,
  multiple,
  drawdown,
})

const ROWS = [
  row('2025', 1, 1.1),
  row('2021', 1, 1.5),
  row('2025', 0, 1),
  row('2021', 0, 1),
  row('2021', 2, 2),
]
const colors = readChartColors()

interface Series {
  name: string
  type: string
  data: number[][]
  lineStyle?: { width: number }
  markLine?: { data: { xAxis: number }[]; label: { formatter: string } }
}

describe('cycle paths', () => {
  it('groups rows per cycle, oldest cycle first, sorted by day', () => {
    const paths = groupPaths(ROWS)
    expect(paths.map((p) => p.cycle)).toEqual(['2021', '2025'])
    expect(paths[1].rows.map((r) => r.day)).toEqual([0, 1])
  })

  it('looks every cycle up on the same day offset, skipping cycles that ended', () => {
    const paths = groupPaths(ROWS)
    expect(rowsAtDay(paths, 1).map((r) => [r.cycle, r.row.multiple])).toEqual([
      ['2021', 1.5],
      ['2025', 1.1],
    ])
    expect(rowsAtDay(paths, 2).map((r) => r.cycle)).toEqual(['2021'])
  })

  it('orders ROI columns by day, with the current day N last', () => {
    const rows = [
      { cycle: '2025', bottom_date: 'x', bottom_price: 1, d30: 0.1, d1440: 3.9, d365: 1.2 },
    ] as unknown as RoiRow[]
    expect(roiColumns(rows).map((c) => c.key)).toEqual(['d30', 'd365', 'd1440'])
  })

  it('groups YoY rows per year', () => {
    const years = groupYears([
      { year: 2026, day: 2, date: '', close: 1, multiple: 1 },
      { year: 2025, day: 1, date: '', close: 1, multiple: 1 },
      { year: 2026, day: 1, date: '', close: 1, multiple: 1 },
    ])
    expect(years.map((y) => [y.year, y.rows.map((r) => r.day)])).toEqual([
      [2025, [1]],
      [2026, [1, 2]],
    ])
  })
})

describe('cycle overlay option', () => {
  const paths = groupPaths(ROWS)

  it('highlights the current cycle and marks today on its last day', () => {
    const option = cycleOverlayOption({
      paths,
      current: '2025',
      y: 'multiple',
      mode: 'halving',
      colors,
    })
    const series = option.series as Series[]
    const current = series.find((s) => s.name === '2025')!
    const past = series.find((s) => s.name === '2021')!
    expect(current.lineStyle!.width).toBeGreaterThan(past.lineStyle!.width)
    expect(current.markLine!.data[0].xAxis).toBe(1)
    expect(current.markLine!.label.formatter).toBe('Today · day 1')
    expect(series.find((s) => s.name === 'Today')!.data).toEqual([[1, 1.1]])
    expect((option.yAxis as { type: string }).type).toBe('log')
  })

  it('plots the drawdown from the cycle ATH on a linear axis in drawdown mode', () => {
    const dd = groupPaths([row('2025', 0, 1, 0), row('2025', 1, 0.8, -0.2)])
    const option = cycleOverlayOption({
      paths: dd,
      current: '2025',
      y: 'drawdown',
      mode: 'top',
      colors,
    })
    const series = option.series as Series[]
    expect(series[0].data).toEqual([
      [0, 0],
      [1, -0.2],
    ])
    expect((option.yAxis as { type: string; max: number }).max).toBe(0)
  })

  it('shows every cycle on the hovered day in the tooltip', () => {
    const option = cycleOverlayOption({
      paths,
      current: '2025',
      y: 'multiple',
      mode: 'bottom',
      colors,
    })
    const formatter = (option.tooltip as { formatter: (p: unknown) => string }).formatter
    const html = formatter([{ axisValue: 1.2 }])
    expect(html).toContain('Day 1 after the cycle bottom')
    expect(html).toContain('2021')
    expect(html).toContain('×1.5')
    expect(html).toContain('×1.1')
    expect(formatter([{ axisValue: 99 }])).toBe('')
  })

  it('escapes cycle names in the tooltip', () => {
    const odd = groupPaths([row('<b>x</b>', 0, 1)])
    const option = cycleOverlayOption({
      paths: odd,
      current: null,
      y: 'multiple',
      mode: 'halving',
      colors,
    })
    const formatter = (option.tooltip as { formatter: (p: unknown) => string }).formatter
    expect(formatter([{ axisValue: 0 }])).toContain('&lt;b&gt;x&lt;/b&gt;')
  })
})

describe('yoy option', () => {
  it('draws the current (latest) year thickest', () => {
    const years = groupYears([
      { year: 2025, day: 1, date: '', close: 1, multiple: 1 },
      { year: 2026, day: 1, date: '', close: 1, multiple: 1 },
    ])
    const series = yoyOption({ years, colors }).series as Series[]
    expect(series[1].lineStyle!.width).toBeGreaterThan(series[0].lineStyle!.width)
  })

  it('labels days of the year as calendar dates', () => {
    expect(dayLabel(1)).toBe('Jan 1')
    expect(dayLabel(60)).toBe('Mar 1')
  })
})

describe('formatMultiple', () => {
  it('uses 3 significant digits, 4 from 100 up', () => {
    expect(formatMultiple(1.19171)).toBe('×1.19')
    expect(formatMultiple(106.46)).toBe('×106.5')
    expect(formatMultiple(null)).toBe('—')
  })
})
