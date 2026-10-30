import { describe, expect, it } from 'vitest'

import { computeIndicators, ratioBars, toBars, type Bar } from './chart-data'
import { DEFAULT_SETTINGS } from './chart-settings'

const bar = (time: number, close: number): Bar => ({
  time,
  open: close,
  high: close,
  low: close,
  close,
  volume: 1,
})

describe('toBars', () => {
  it('converts UTC times to seconds and keeps close-only days', () => {
    const [b] = toBars([{ time: '2015-07-19T00:00:00Z', open: null, close: 280, volume: null }])
    expect(b).toEqual({
      time: 1437264000,
      open: null,
      high: null,
      low: null,
      close: 280,
      volume: null,
    })
  })
})

describe('ratioBars', () => {
  it('divides closes on the bars both coins have', () => {
    const eth = [bar(1, 2), bar(2, 3), bar(3, 4)]
    const btc = [bar(2, 30), bar(3, 40), bar(4, 50)]
    expect(ratioBars(eth, btc).map((b) => [b.time, b.close])).toEqual([
      [2, 0.1],
      [3, 0.1],
    ])
    expect(ratioBars(eth, btc).every((b) => b.open === null && b.volume === null)).toBe(true)
  })

  it('skips a zero denominator rather than plotting infinity', () => {
    expect(ratioBars([bar(1, 2)], [bar(1, 0)])).toEqual([])
  })
})

describe('computeIndicators', () => {
  const bars = Array.from({ length: 300 }, (_, i) => bar(1_700_000_000 + i * 86_400, 100 + i))

  it('returns the selected lines in their panes', () => {
    const lines = computeIndicators(bars, {
      ...DEFAULT_SETTINGS,
      panes: { rsi: true, macd: true },
    })
    const ids = lines.map((l) => l.id)
    expect(ids).toEqual(
      expect.arrayContaining(['sma50', 'sma200', 'sma20w', 'ema21w', 'rsi14', 'macd', 'macd_hist']),
    )
    expect(ids).not.toContain('sma20')
    expect(lines.find((l) => l.id === 'rsi14')?.pane).toBe('rsi')
    expect(lines.find((l) => l.id === 'macd')?.pane).toBe('macd')
    expect(lines.find((l) => l.id === 'sma50')?.values[299]).toBeCloseTo(374.5, 9)
  })

  it('uses the bars themselves for the band on the weekly timeframe', () => {
    const weekly = computeIndicators(bars, { ...DEFAULT_SETTINGS, tf: '1w' })
    const sma20w = weekly.find((l) => l.id === 'sma20w')
    expect(sma20w?.values[19]).toBeCloseTo(109.5, 9)
  })
})
