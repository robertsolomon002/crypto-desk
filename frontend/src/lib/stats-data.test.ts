import { describe, expect, it } from 'vitest'

import { readChartColors } from './chart-colors'
import { mix } from './echarts-theme'
import {
  binIndex,
  correlationMatrix,
  heatmapCells,
  ordinal,
  periodOf,
  sinceSpan,
  type CorrRow,
  type Distribution,
  type MatrixRow,
} from './stats-data'
import { distributionOption, monthlyHeatmapOption, timeSeriesOption } from './stats-options'

const colors = readChartColors()

describe('stats data', () => {
  it('builds heatmap cells per month and year, skipping empty months', () => {
    const matrix = [
      { year: 2011, '1': 0.5, '2': null },
      { year: 2010, '12': -0.1 },
    ] as unknown as MatrixRow[]
    expect(heatmapCells(matrix)).toEqual({
      years: [2010, 2011],
      cells: [
        [11, 0, -0.1],
        [0, 1, 0.5],
      ],
    })
  })

  it('finds the histogram bin of a value, the last bin including its right edge', () => {
    const bins = [-0.1, 0, 0.1, 0.2]
    expect(binIndex(bins, -0.05)).toBe(0)
    expect(binIndex(bins, 0)).toBe(1)
    expect(binIndex(bins, 0.2)).toBe(2)
    expect(binIndex(bins, 0.3)).toBe(-1)
    expect(binIndex(bins, null)).toBe(-1)
  })

  it('falls back to the row position when a summary has no period key', () => {
    expect(periodOf({ mean: 0, median: 0, pct_positive: 0, count: 1 }, 0, 'monthly')).toBe(1)
    expect(periodOf({ mean: 0, median: 0, pct_positive: 0, count: 1 }, 0, 'dow')).toBe(0)
    expect(periodOf({ weekday: 4, mean: 0, median: 0, pct_positive: 0, count: 1 }, 0, 'dow')).toBe(
      4,
    )
  })

  it('builds a symmetric correlation matrix from the latest values, selected coin first', () => {
    const rows = [
      { date: '2026-10-30', 'SOL/BTC': 0.8, 'SOL/ETH': 0.7, 'BTC/ETH': 0.9 },
      { date: '2026-10-31', 'SOL/BTC': 0.84, 'SOL/ETH': null, 'BTC/ETH': 0.89 },
    ] as unknown as CorrRow[]
    const m = correlationMatrix(rows, 'BTC')
    expect(m.coins).toEqual(['BTC', 'SOL', 'ETH'])
    expect(m.values).toEqual([
      [1, 0.84, 0.89],
      [0.84, 1, 0.7],
      [0.89, 0.7, 1],
    ])
    expect(m.date).toBe('2026-10-31')
  })

  it('cuts time series to the last 1 or 4 years', () => {
    const rows = ['2021-10-31', '2022-10-31', '2025-10-30', '2025-10-31', '2026-10-31'].map(
      (date) => ({
        date,
      }),
    )
    expect(sinceSpan(rows, 'all')).toHaveLength(5)
    expect(sinceSpan(rows, '4y').map((r) => r.date)).toEqual(rows.slice(1).map((r) => r.date))
    expect(sinceSpan(rows, '1y').map((r) => r.date)).toEqual(['2025-10-31', '2026-10-31'])
  })

  it('writes ordinals', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 29.2, 100].map(ordinal)).toEqual([
      '1st',
      '2nd',
      '3rd',
      '4th',
      '11th',
      '12th',
      '13th',
      '21st',
      '29th',
      '100th',
    ])
  })
})

describe('stats options', () => {
  it('clips heatmap colors symmetrically and labels cells in whole percent', () => {
    const option = monthlyHeatmapOption(
      [{ year: 2026, '1': 0.1234 } as unknown as MatrixRow],
      colors,
    )
    const vm = option.visualMap as { min: number; max: number; inRange: { color: string[] } }
    expect(vm.min).toBe(-vm.max)
    expect(vm.inRange.color).toHaveLength(5)
    const label = (option.series as { label: { formatter: (p: unknown) => string } }[])[0].label
    expect(label.formatter({ value: [0, 0, 0.1234] })).toBe('+12%')
    expect(label.formatter({ value: [0, 0, -0.05] })).toBe('−5%')
  })

  it('fills the latest return bin and draws a line there', () => {
    const d: Distribution = {
      horizon: '1w',
      count: 6,
      mean: 0,
      std: 0.1,
      quantiles: {},
      bins: [-0.2, -0.1, 0, 0.1],
      counts: [1, 3, 2],
      current_date: '2026-10-19',
      current: -0.02,
      current_percentile: 40,
    }
    const option = distributionOption(d, colors)
    const bars = (
      option.series as {
        data: { itemStyle: { color: string } }[]
        markLine: { data: { xAxis: number }[] }
      }[]
    )[0]
    expect(bars.data[1].itemStyle.color).toBe(colors['series-2'])
    expect(bars.data[0].itemStyle.color).not.toBe(colors['series-2'])
    expect(bars.markLine.data[0].xAxis).toBe(1)
  })

  it('sends dates to the time axis as UTC midnight', () => {
    const option = timeSeriesOption({
      lines: [{ name: 'x', color: '#000', points: [['2026-10-31', 0.1]] }],
      colors,
    })
    const data = (option.series as { data: [number, number][] }[])[0].data
    expect(data[0][0]).toBe(Date.UTC(2026, 9, 31))
  })

  it('blends colors into opaque rgb', () => {
    expect(mix('rgb(0, 0, 0)', '#ffffff', 0.5)).toBe('rgb(128, 128, 128)')
  })
})
