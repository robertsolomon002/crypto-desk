import { describe, expect, it } from 'vitest'

import {
  changeCorrelation,
  nuplZone,
  onchainCoin,
  parseOverlay,
  pearson,
  percentileOf,
  periodKey,
  points,
  rollingMean,
  toggleOverlay,
  trimPoints,
  yoyChange,
  type Point,
} from './onchain-data'

const day = (i: number) =>
  new Date(Date.UTC(2024, 0, 1) + i * 86_400_000).toISOString().slice(0, 10)

describe('onchain helpers', () => {
  it('maps BTC and ETH to themselves and anything else to BTC', () => {
    expect(onchainCoin('ETH')).toBe('ETH')
    expect(onchainCoin('SOL')).toBe('BTC')
  })

  it('keeps finite numbers only and cuts timestamps to the day', () => {
    const rows = [
      { date: '2026-10-30', v: 1 },
      { date: '2026-10-31T00:00:00Z', v: 2 },
      { date: '2026-11-01', v: null },
      { date: '2026-11-02', v: 'x' },
    ]
    expect(points(rows, (r) => r.v)).toEqual([
      ['2026-10-30', 1],
      ['2026-10-31', 2],
    ])
  })

  it('takes a trailing mean only over full windows', () => {
    const pts: Point[] = [1, 2, 3, null, 5, 6, 7].map((v, i) => [day(i), v])
    expect(rollingMean(pts, 3).map((p) => p[1])).toEqual([null, null, 2, null, null, null, 6])
  })

  it('ranks a value among history', () => {
    expect(percentileOf([1, 2, 3, 4], 3)).toBe(75)
    expect(percentileOf([], 3)).toBeNull()
  })

  it('compares each month with the same month a year earlier', () => {
    const pts: Point[] = [
      ['2024-01-01', 100],
      ['2024-02-01', 110],
      ['2025-01-01', 105],
      ['2025-03-01', 120],
    ]
    const out = yoyChange(pts)
    expect(out).toHaveLength(1)
    expect(out[0][0]).toBe('2025-01-01')
    expect(out[0][1]).toBeCloseTo(0.05)
  })

  it('trims to the last 1 or 4 years before the final point', () => {
    const pts: Point[] = [
      ['2020-01-01', 1],
      ['2025-10-31', 2],
      ['2025-11-01', 3],
      ['2026-11-01', 4],
    ]
    expect(trimPoints(pts, '1y').map((p) => p[0])).toEqual(['2025-11-01', '2026-11-01'])
    expect(trimPoints(pts, '4y')).toHaveLength(3)
    expect(trimPoints(pts, 'all')).toBe(pts)
  })

  it('names NUPL zones at their edges', () => {
    expect(nuplZone(-0.2)).toBe('Capitulation')
    expect(nuplZone(0)).toBe('Hope / fear')
    expect(nuplZone(0.3)).toBe('Optimism / anxiety')
    expect(nuplZone(0.75)).toBe('Euphoria / greed')
  })

  it('keeps overlay ids known and in a stable order', () => {
    const known = ['DTWEXBGS', 'DGS10', 'DFF', 'M2SL']
    expect(parseOverlay('M2SL,evil,DGS10', known)).toEqual(['DGS10', 'M2SL'])
    expect(parseOverlay(null, known)).toEqual([])
    expect(toggleOverlay(['M2SL'], 'DGS10', known)).toEqual(['DGS10', 'M2SL'])
    expect(toggleOverlay(['DGS10', 'M2SL'], 'DGS10', known)).toEqual(['M2SL'])
  })
})

describe('correlation with BTC', () => {
  it('groups days into UTC Monday weeks and months', () => {
    expect(periodKey('2026-11-01', 'week')).toBe('2026-10-26') // a Sunday
    expect(periodKey('2026-10-26', 'week')).toBe('2026-10-26') // a Monday
    expect(periodKey('2026-11-01', 'month')).toBe('2026-11')
  })

  it('computes Pearson r and refuses flat or short input', () => {
    expect(pearson([1, 2, 3], [2, 4, 6])).toBeCloseTo(1)
    expect(pearson([1, 2, 3], [3, 2, 1])).toBeCloseTo(-1)
    expect(pearson([1, 2, 3], [5, 5, 5])).toBeNull()
    expect(pearson([1, 2], [1, 2])).toBeNull()
  })

  it('correlates weekly log changes and drops BTC’s latest (maybe partial) week', () => {
    // 30 weeks of daily closes; the series is BTC itself, so r = 1.
    const btc: Point[] = Array.from({ length: 210 }, (_, i) => [
      day(i),
      100 * Math.exp(Math.sin(i / 9)),
    ])
    const r = changeCorrelation(btc, btc, { freq: 'week', periods: 52, mode: 'log' })
    expect(r.r).toBeCloseTo(1)
    expect(r.n).toBe(28) // 30 weeks, the last dropped, 29 levels give 28 changes
    expect(r.to).toBe('2024-07-15')
    const short = changeCorrelation(btc, btc, { freq: 'week', periods: 10, mode: 'log' })
    expect(short.n).toBe(10)
    expect(short.from).toBe('2024-05-13')
  })

  it('uses plain differences for rates and is undefined for a flat rate', () => {
    const btc: Point[] = Array.from({ length: 140 }, (_, i) => [
      day(i),
      100 * Math.exp(Math.sin(i / 9)),
    ])
    const flat = btc.map(([d]) => [d, 5.33] as Point)
    expect(changeCorrelation(btc, flat, { freq: 'week', periods: 52, mode: 'diff' }).r).toBeNull()
    const falling = btc.map(([d, v]) => [d, 10 - Math.log(v as number)] as Point)
    const r = changeCorrelation(btc, falling, { freq: 'week', periods: 52, mode: 'diff' })
    expect(r.r).toBeCloseTo(-1) // the rate falls by exactly BTC's log change
  })

  it('aligns a monthly series dated on the 1st with BTC month-end closes', () => {
    const btc: Point[] = Array.from({ length: 400 }, (_, i) => [
      day(i),
      100 * 1.002 ** i * (1 + (i % 30) / 300),
    ])
    const m2: Point[] = Array.from({ length: 13 }, (_, i) => [
      `${2024 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}-01`,
      20_000 + i * 50 + (i % 2) * 30,
    ])
    const r = changeCorrelation(btc, m2, { freq: 'month', periods: 36, mode: 'log' })
    // BTC spans Jan 2024 to early Feb 2025; Feb 2025 is dropped, M2 covers Jan 2024 to Jan 2025.
    expect(r.n).toBe(12)
    expect(r.from).toBe('2024-02')
    expect(r.to).toBe('2025-01')
    expect(r.r).not.toBeNull()
  })
})
