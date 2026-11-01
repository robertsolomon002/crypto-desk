import { describe, expect, it } from 'vitest'

import { readChartColors } from './chart-colors'
import { dualAxisOption, formatCompact, formatUsd } from './onchain-options'

const colors = readChartColors()
const line = (name: string) => ({
  name,
  color: '#123456',
  points: [
    ['2026-10-30', 1],
    ['2026-10-31', 2],
  ] as [string, number][],
})

type Opt = {
  yAxis: { type: string; position: string }[]
  series: {
    yAxisIndex: number
    data: [number, number][]
    markArea?: { data: Record<string, unknown>[][] }
    markLine?: { data: { yAxis: number }[] }
  }[]
  tooltip: { formatter: (p: unknown) => string }
}

describe('dualAxisOption', () => {
  it('puts the right-hand lines on a second (log) axis', () => {
    const opt = dualAxisOption({
      left: { lines: [line('MVRV')], format: String },
      right: { lines: [line('BTC price')], format: formatUsd, log: true },
      colors,
    }) as unknown as Opt
    expect(opt.yAxis.map((a) => [a.type, a.position])).toEqual([
      ['value', 'left'],
      ['log', 'right'],
    ])
    expect(opt.series.map((s) => s.yAxisIndex)).toEqual([0, 1])
    expect(opt.series[0].data[0][0]).toBe(Date.UTC(2026, 9, 30)) // UTC midnight, not local
  })

  it('draws open-ended bands to the axis edge and reference lines', () => {
    const opt = dualAxisOption({
      left: { lines: [line('MVRV')], format: String },
      bands: [
        { to: 1, color: 'red', label: 'Below 1' },
        { from: 3.5, color: 'blue' },
      ],
      refLines: [{ value: 1 }],
      colors,
    }) as unknown as Opt
    const [low, high] = opt.series[0].markArea!.data
    expect(low[0]).not.toHaveProperty('yAxis')
    expect(low[1]).toEqual({ yAxis: 1 })
    expect(high[0]).toMatchObject({ yAxis: 3.5 })
    expect(high[1]).toEqual({})
    expect(opt.series[0].markLine!.data).toEqual([{ yAxis: 1, name: '' }])
    expect(opt.yAxis).toHaveLength(1)
  })

  it('escapes series names and values in the tooltip and formats per axis', () => {
    const opt = dualAxisOption({
      left: { lines: [line('<b>x</b>')], format: (v) => `${v}%` },
      right: { lines: [line('BTC price')], format: formatUsd },
      colors,
    }) as unknown as Opt
    const html = opt.tooltip.formatter([
      { seriesName: '<b>x</b>', value: [Date.UTC(2026, 9, 31), 2], color: 'red' },
      { seriesName: 'BTC price', value: [Date.UTC(2026, 9, 31), 77_000], color: 'red' },
    ])
    expect(html).toContain('&lt;b&gt;x&lt;/b&gt;')
    expect(html).toContain('2%')
    expect(html).toContain('$77K')
    expect(html).toContain('Oct 31, 2026')
  })
})

describe('axis formats', () => {
  it('formats tiny and large values readably', () => {
    expect(formatUsd(77_423)).toBe('$77.42K')
    expect(formatUsd(0.0495)).toBe('$0.0495')
    expect(formatCompact(0.000001)).toBe('1e-6')
    expect(formatCompact(1030)).toBe('1.03K')
  })

  it('fits log axes to the data', () => {
    const opt = dualAxisOption({
      left: { lines: [line('x')], format: String, log: true },
      colors,
    }) as unknown as { yAxis: { min: unknown; max: unknown }[] }
    expect(opt.yAxis[0]).toMatchObject({ min: 'dataMin', max: 'dataMax' })
  })
})
