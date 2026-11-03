import { describe, expect, it } from 'vitest'

import { FAKE_VIDEO } from './__fixtures__/mco'
import { closeOn, mcoLines, parseLevels, shortDate, videoCoins } from './mco'

describe('mcoLines', () => {
  it('draws each scenario in its colour, targets solid, shared levels muted', () => {
    const lines = mcoLines(FAKE_VIDEO, 'ETH', { primary: true, alternative: true })
    expect(lines).toEqual([
      { value: 8, label: 'MCO P target · Oct 2', color: 'series-1', style: 'solid' },
      { value: 7.5, label: 'MCO P target · Oct 2', color: 'series-1', style: 'solid' },
      { value: 13, label: 'MCO Alt resistance · Oct 2', color: 'series-4', style: 'dashed' },
      { value: 9, label: 'MCO support box · Oct 2', color: 'muted-foreground', style: 'dotted' },
    ])
  })

  it('respects the scenario toggles and the coin', () => {
    const alt = mcoLines(FAKE_VIDEO, 'ETH', { primary: false, alternative: true })
    expect(alt.map((l) => l.value)).toEqual([13]) // shared levels go with the primary
    expect(mcoLines(FAKE_VIDEO, 'SOL', { primary: true, alternative: true })).toEqual([])
    const btc = mcoLines(FAKE_VIDEO, 'BTC', { primary: true, alternative: true })
    expect(btc).toEqual([
      { value: 90, label: 'MCO P invalidation · Oct 2', color: 'series-1', style: 'dotted' },
    ])
  })
})

describe('helpers', () => {
  it('lists coins, core first', () => {
    expect(videoCoins([FAKE_VIDEO])).toEqual(['BTC', 'ETH'])
  })

  it('finds the close on or before a day', () => {
    const closes = [
      { date: '2026-10-01', close: 1 },
      { date: '2026-10-03', close: 3 },
    ]
    expect(closeOn(closes, '2026-10-02')).toBe(1)
    expect(closeOn(closes, '2026-10-03')).toBe(3)
    expect(closeOn(closes, '2026-09-30')).toBeNull()
  })

  it('formats short UTC dates', () => {
    expect(shortDate('2026-11-02T23:30:00Z')).toBe('Nov 2')
  })

  it('parses manual levels, one per line', () => {
    expect(parseLevels('70,000 breakout\n\n$58000.5 support box')).toEqual([
      { price: 70000, label: 'breakout' },
      { price: 58000.5, label: 'support box' },
    ])
    expect(parseLevels('')).toEqual([])
    expect(parseLevels('breakout 70000')).toBeNull()
    expect(parseLevels('0 zero')).toBeNull()
  })
})
