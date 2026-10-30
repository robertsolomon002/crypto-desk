import type { ChartSettings, Timeframe } from './chart-settings'
import { bollinger, ema, macd, rsi, sma, weeklyBand, type Series } from './indicators'

// Turns API candles into chart bars, builds ratio series and computes the selected indicators.

export interface Bar {
  time: number // bar open, seconds since the epoch, UTC
  open: number | null // null on close-only Coin Metrics backfill days (D31) and ratio bars
  high: number | null
  low: number | null
  close: number
  volume: number | null
}

interface ApiCandle {
  time: string
  open?: number | null
  high?: number | null
  low?: number | null
  close: number
  volume?: number | null
}

export const BAR_SECONDS: Record<Timeframe, number> = { '1d': 86_400, '1w': 604_800, '4h': 14_400 }

export function toBars(candles: ApiCandle[]): Bar[] {
  return candles.map((c) => ({
    time: Math.floor(Date.parse(c.time) / 1000),
    open: c.open ?? null,
    high: c.high ?? null,
    low: c.low ?? null,
    close: c.close,
    volume: c.volume ?? null,
  }))
}

/** A / B on the bars both coins have. Highs and lows don't divide into a true OHLC, so ratio
 * bars carry the close ratio only. */
export function ratioBars(a: Bar[], b: Bar[]): Bar[] {
  const denom = new Map(b.map((bar) => [bar.time, bar.close]))
  const out: Bar[] = []
  for (const bar of a) {
    const d = denom.get(bar.time)
    if (d)
      out.push({
        time: bar.time,
        open: null,
        high: null,
        low: null,
        close: bar.close / d,
        volume: null,
      })
  }
  return out
}

/** One computed line, keyed by a stable id; `pane` 0 is the price pane. */
export interface IndicatorLine {
  id: string
  label: string
  pane: 'price' | 'rsi' | 'macd'
  values: Series
  style?: 'line' | 'histogram' | 'dashed'
  color: 'series-1' | 'series-2' | 'series-3' | 'series-4' | 'series-5' | 'muted' | 'macd-hist'
}

export function computeIndicators(bars: Bar[], s: ChartSettings): IndicatorLine[] {
  const close = bars.map((b) => b.close)
  const times = bars.map((b) => b.time)
  const o = s.overlays
  const out: IndicatorLine[] = []
  const ma = [
    ['sma20', 'SMA 20', 'series-1', () => sma(close, 20)],
    ['sma50', 'SMA 50', 'series-2', () => sma(close, 50)],
    ['sma200', 'SMA 200', 'series-5', () => sma(close, 200)],
    ['ema20', 'EMA 20', 'series-1', () => ema(close, 20)],
    ['ema50', 'EMA 50', 'series-2', () => ema(close, 50)],
    ['ema200', 'EMA 200', 'series-5', () => ema(close, 200)],
  ] as const
  for (const [id, label, color, fn] of ma) {
    if (o[id])
      out.push({
        id,
        label,
        pane: 'price',
        values: fn(),
        color,
        style: id.startsWith('ema') ? 'dashed' : 'line',
      })
  }
  if (o.band) {
    // On weekly bars the band is just the 20-week SMA and 21-week EMA of the bars themselves.
    const band =
      s.tf === '1w'
        ? { sma20w: sma(close, 20), ema21w: ema(close, 21) }
        : weeklyBand(times, close, BAR_SECONDS[s.tf])
    out.push({
      id: 'sma20w',
      label: '20W SMA',
      pane: 'price',
      values: band.sma20w,
      color: 'series-3',
    })
    out.push({
      id: 'ema21w',
      label: '21W EMA',
      pane: 'price',
      values: band.ema21w,
      color: 'series-3',
      style: 'dashed',
    })
  }
  if (o.bb) {
    const bb = bollinger(close, 20, 2)
    out.push({
      id: 'bb_upper',
      label: 'BB upper',
      pane: 'price',
      values: bb.upper,
      color: 'series-4',
    })
    out.push({
      id: 'bb_mid',
      label: 'BB mid',
      pane: 'price',
      values: bb.mid,
      color: 'series-4',
      style: 'dashed',
    })
    out.push({
      id: 'bb_lower',
      label: 'BB lower',
      pane: 'price',
      values: bb.lower,
      color: 'series-4',
    })
  }
  if (s.panes.rsi) {
    out.push({
      id: 'rsi14',
      label: 'RSI 14',
      pane: 'rsi',
      values: rsi(close, 14),
      color: 'series-4',
    })
  }
  if (s.panes.macd) {
    const m = macd(close, 12, 26, 9)
    out.push({
      id: 'macd_hist',
      label: 'Hist',
      pane: 'macd',
      values: m.hist,
      color: 'macd-hist',
      style: 'histogram',
    })
    out.push({ id: 'macd', label: 'MACD', pane: 'macd', values: m.line, color: 'series-1' })
    out.push({
      id: 'macd_signal',
      label: 'Signal',
      pane: 'macd',
      values: m.signal,
      color: 'series-2',
    })
  }
  return out
}
