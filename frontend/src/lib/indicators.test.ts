import { describe, expect, it } from 'vitest'

import fixture from './__fixtures__/indicators_parity.json'
import { bollinger, ema, macd, rsi, sma, weeklyBand, type Series } from './indicators'

// The backend writes this fixture from `indicators.custom` (backend/tests/test_indicator_parity.py),
// so these tests fail if the TypeScript port drifts from the Python it mirrors.

type Row = Record<string, number | string | null>
const rows = fixture.rows as Row[]
const close = rows.map((r) => r.close as number)
const times = rows.map((r) => Date.parse(`${r.date as string}T00:00:00Z`) / 1000)

function expectParity(name: string, actual: Series) {
  const expected = rows.map((r) => r[name] as number | null)
  expect(expected.some((v) => v !== null)).toBe(true)
  expected.forEach((want, i) => {
    const got = actual[i]
    if (want === null) {
      expect(Number.isNaN(got), `${name} row ${i} should be warm-up`).toBe(true)
    } else {
      const scale = Math.max(1, Math.abs(want))
      expect(Math.abs(got - want) / scale, `${name} row ${i}: ${got} vs ${want}`).toBeLessThan(1e-9)
    }
  })
}

describe('indicator parity with the backend fixture', () => {
  it.each([20, 50, 200])('SMA %i', (n) => expectParity(`sma${n}`, sma(close, n)))

  it.each([20, 50, 200])('EMA %i', (n) => expectParity(`ema${n}`, ema(close, n)))

  it('Bollinger 20, 2', () => {
    const bb = bollinger(close, 20, 2)
    expectParity('bb20_2_mid', bb.mid)
    expectParity('bb20_2_upper', bb.upper)
    expectParity('bb20_2_lower', bb.lower)
  })

  it('RSI 14 (Wilder)', () => expectParity('rsi14', rsi(close, 14)))

  it('MACD 12/26/9', () => {
    const m = macd(close, 12, 26, 9)
    expectParity('macd12_26_9', m.line)
    expectParity('macd12_26_9_signal', m.signal)
    expectParity('macd12_26_9_hist', m.hist)
  })

  it('20W SMA / 21W EMA band from complete weeks, applied from the next Monday', () => {
    const band = weeklyBand(times, close)
    expectParity('sma20w', band.sma20w)
    expectParity('ema21w', band.ema21w)
  })
})

describe('edge cases', () => {
  it('RSI is 100 with no losses and 50 when flat', () => {
    expect(rsi([1, 2, 3, 4], 2)[3]).toBe(100)
    expect(rsi([5, 5, 5, 5], 2)[3]).toBe(50)
  })

  it('short series are all warm-up', () => {
    expect([...sma([1, 2], 3)].every(Number.isNaN)).toBe(true)
    expect([...ema([1, 2], 3)].every(Number.isNaN)).toBe(true)
    expect([...rsi([1, 2], 3)].every(Number.isNaN)).toBe(true)
  })

  it('the band on 4H bars matches the band on the daily closes of the same weeks', () => {
    // Six 4H bars per day whose last bar closes at the daily close.
    const t4: number[] = []
    const c4: number[] = []
    times.forEach((t, i) => {
      for (let k = 0; k < 6; k++) {
        t4.push(t + k * 4 * 3600)
        c4.push(k === 5 ? close[i] : close[i] * 1.01)
      }
    })
    const daily = weeklyBand(times, close)
    const h4 = weeklyBand(t4, c4, 4 * 3600)
    const last = times.length - 1
    expect(h4.sma20w[last * 6]).toBeCloseTo(daily.sma20w[last], 9)
    expect(h4.ema21w[last * 6 + 5]).toBeCloseTo(daily.ema21w[last], 9)
  })
})
