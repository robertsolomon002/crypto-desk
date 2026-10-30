import type { Bar, IndicatorLine } from '@/lib/chart-data'
import { formatPct, formatPrice } from '@/lib/format'
import { cn } from '@/lib/utils'

// The crosshair readout: the hovered bar (or the last one) with OHLC, change, volume and every
// visible indicator value. Times are UTC like the API; daily and weekly bars show the date only.

const SWATCH: Record<IndicatorLine['color'], string> = {
  'series-1': 'bg-series-1',
  'series-2': 'bg-series-2',
  'series-3': 'bg-series-3',
  'series-4': 'bg-series-4',
  'series-5': 'bg-series-5',
  muted: 'bg-muted-foreground',
  'macd-hist': 'bg-muted-foreground',
}

function formatBarTime(t: number, intraday: boolean): string {
  const iso = new Date(t * 1000).toISOString()
  return intraday ? `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC` : `${iso.slice(0, 10)} UTC`
}

function formatCompact(v: number): string {
  return v.toLocaleString('en-US', { notation: 'compact', maximumFractionDigits: 2 })
}

function formatValue(line: IndicatorLine, v: number): string {
  if (!Number.isFinite(v)) return '—'
  if (line.pane === 'rsi') return v.toFixed(1)
  return formatPrice(v)
}

export function Readout({
  bars,
  index,
  lines,
  intraday,
  ratio,
}: {
  bars: Bar[]
  index: number | null
  lines: IndicatorLine[]
  intraday: boolean
  ratio: boolean
}) {
  const i = index ?? bars.length - 1
  const bar = bars[i]
  if (!bar) return <div className="h-10" />
  const prev = bars[i - 1]
  const change = prev ? bar.close / prev.close - 1 : null
  const closeOnly = !ratio && bar.open === null
  const fmt = ratio ? (v: number) => v.toPrecision(5) : formatPrice
  return (
    <div
      className="flex min-h-10 flex-wrap items-baseline gap-x-3 gap-y-0.5 font-mono text-xs tabular-nums"
      aria-live="off"
      data-testid="chart-readout"
    >
      <span className="text-muted-foreground">{formatBarTime(bar.time, intraday)}</span>
      {closeOnly || ratio ? (
        <span>
          C <span className="text-foreground">{fmt(bar.close)}</span>
          {closeOnly && (
            <span className="ml-1 text-muted-foreground">close only (Coin Metrics)</span>
          )}
        </span>
      ) : (
        <>
          <span>O {formatPrice(bar.open)}</span>
          <span>H {formatPrice(bar.high)}</span>
          <span>L {formatPrice(bar.low)}</span>
          <span>C {formatPrice(bar.close)}</span>
        </>
      )}
      {change !== null && (
        <span className={cn(change >= 0 ? 'text-positive' : 'text-negative')}>
          {formatPct(change)}
        </span>
      )}
      {bar.volume !== null && (
        <span className="text-muted-foreground">Vol {formatCompact(bar.volume)}</span>
      )}
      {lines.map((line) => (
        <span key={line.id} className="inline-flex items-center gap-1">
          <span
            className={cn('inline-block size-2 rounded-full', SWATCH[line.color])}
            aria-hidden
          />
          <span className="text-muted-foreground">{line.label}</span>
          {ratio && line.pane === 'price' ? fmt(line.values[i]) : formatValue(line, line.values[i])}
        </span>
      ))}
    </div>
  )
}
