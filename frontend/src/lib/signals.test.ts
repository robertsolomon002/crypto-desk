import { describe, expect, it } from 'vitest'

import { HISTORY, SCORECARD, WEEK_SIGNALS } from './__fixtures__/signals'
import { readChartColors } from './chart-colors'
import type { SignalOut, SourceScore } from './queries'
import {
  cumulativeOption,
  outcomeText,
  rateText,
  signalCoins,
  signalGrid,
  signalSources,
} from './signals'

const signals = WEEK_SIGNALS as SignalOut[]

describe('signals helpers', () => {
  it('orders coins core first and sources in the scorecard order', () => {
    const extra = { ...signals[1], coin: 'LINK' }
    expect(signalCoins([extra, ...signals])).toEqual(['BTC', 'ETH', 'LINK'])
    expect(signalSources([...signals].reverse())).toEqual(['desk', 'coinflip', 'trend', 'mco'])
    expect(signalGrid(signals).get('ETH')?.get('desk')?.confidence).toBe(0.55)
  })

  it('describes outcomes', () => {
    const [desk, flip] = (HISTORY as SignalOut[]).slice(-2)
    expect(outcomeText(desk)).toBe('hit · week +5.0% · target first · P&L +3.6%')
    expect(outcomeText(flip)).toBe('miss · week +5.0%') // flat: no P&L
    expect(outcomeText(signals[0])).toBe('open')
  })

  it('formats rates', () => {
    expect(rateText(2 / 3, 2, 3)).toBe('66.7% (2/3)')
    expect(rateText(null)).toBe('—')
  })

  it('draws one line per source over every resolved week', () => {
    const option = cumulativeOption(
      readChartColors(),
      SCORECARD.sources as SourceScore[],
      'paper_return',
    ) as { series: { name: string; data: (number | null)[] }[]; xAxis: { data: string[] } }
    expect(option.xAxis.data).toEqual(['2026-10-12', '2026-10-19'])
    expect(option.series.map((s) => s.name)).toEqual(['Desk', 'Coin flip'])
    expect(option.series[0].data).toEqual([0.014, 0.05])
  })
})
