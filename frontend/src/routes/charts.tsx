import { ChevronDown } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { CandleChart, type LevelLine, type PivotMark } from '@/components/charts/CandleChart'
import { Readout } from '@/components/charts/Readout'
import { QueryStatus } from '@/components/overview/Panel'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ViewDataLink } from '@/components/ViewDataLink'
import { useChartColors } from '@/lib/chart-colors'
import { computeIndicators, ratioBars, toBars } from '@/lib/chart-data'
import {
  useChartSettings,
  type ChartSettings,
  type Overlay,
  type Pane,
  type Timeframe,
} from '@/lib/chart-settings'
import { useSelectedCoin } from '@/lib/coin'
import { useCoins, useLevels, useMe, useOhlcv, usePivots } from '@/lib/queries'
import { cn } from '@/lib/utils'

const TF_LABEL: Record<Timeframe, string> = { '1d': '1D', '1w': '1W', '4h': '4H' }
const TF_NAME: Record<Timeframe, string> = { '1d': 'Daily', '1w': 'Weekly', '4h': '4-hour' }
// The first view: about a year of daily bars, five years of weekly, three months of 4H.
const INITIAL_BARS: Record<Timeframe, number> = { '1d': 365, '1w': 260, '4h': 540 }

const LEVEL_LABEL: Record<string, string> = {
  prev_week_high: 'Prev wk high',
  prev_week_low: 'Prev wk low',
  sma20w: '20W SMA',
  sma50d: '50D SMA',
  sma200d: '200D SMA',
  ath: 'ATH',
  swing_high: 'Swing high',
  swing_low: 'Swing low',
}

const INDICATOR_ITEMS: [Overlay, string][] = [
  ['sma20', 'SMA 20'],
  ['sma50', 'SMA 50'],
  ['sma200', 'SMA 200'],
  ['ema20', 'EMA 20'],
  ['ema50', 'EMA 50'],
  ['ema200', 'EMA 200'],
  ['band', '20W SMA band (bull market support)'],
  ['bb', 'Bollinger Bands (20, 2)'],
]
const PANE_ITEMS: [Pane, string][] = [
  ['rsi', 'RSI (14)'],
  ['macd', 'MACD (12, 26, 9)'],
]

interface LevelRow {
  name: string
  value: number
}
interface PivotRow {
  kind: 'high' | 'low'
  date: string
  confirmed: boolean
}

const toDate = (t: number) => new Date(t * 1000).toISOString().slice(0, 10)

function Toggle({
  pressed,
  onClick,
  children,
  disabled,
  title,
}: {
  pressed: boolean
  onClick: () => void
  children: React.ReactNode
  disabled?: boolean
  title?: string
}) {
  return (
    <Button
      variant={pressed ? 'secondary' : 'ghost'}
      size="sm"
      aria-pressed={pressed}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn('h-7 px-2 font-mono text-xs', pressed && 'text-foreground')}
    >
      {children}
    </Button>
  )
}

/** A checkbox item that leaves the menu open, so several can be toggled in one go. */
function Check(props: React.ComponentProps<typeof DropdownMenuCheckboxItem>) {
  return <DropdownMenuCheckboxItem {...props} onSelect={(e) => e.preventDefault()} />
}

function Menu({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 gap-1 px-2 text-xs">
          {label}
          <ChevronDown className="size-3" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-56">
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function ChartsPage() {
  const [coin] = useSelectedCoin()
  const { data: me } = useMe()
  const { data: coinsData } = useCoins()
  const [settings, update] = useChartSettings(me?.clerk_id)
  const colors = useChartColors()

  const ratioCoin = settings.ratio && settings.ratio !== coin ? settings.ratio : null
  const isRatio = ratioCoin !== null
  const tf = settings.tf
  const pivotTf = tf === '4h' ? null : tf

  const main = useOhlcv(coin, tf)
  const denom = useOhlcv(ratioCoin, tf)
  const levelsQ = useLevels(coin, settings.overlays.levels && !isRatio)
  const pivotsQ = usePivots(
    coin,
    pivotTf ?? '1d',
    settings.overlays.pivots && !isRatio && !!pivotTf,
  )

  const bars = useMemo(() => {
    const a = main.data ? toBars(main.data.data) : []
    if (!isRatio) return a
    return denom.data ? ratioBars(a, toBars(denom.data.data)) : []
  }, [main.data, denom.data, isRatio])

  const lines = useMemo(() => computeIndicators(bars, settings), [bars, settings])

  const levels = useMemo<LevelLine[]>(() => {
    if (isRatio || !settings.overlays.levels) return []
    const rows = (levelsQ.data?.data.result ?? []) as LevelRow[]
    return rows.map((r) => ({ label: LEVEL_LABEL[r.name] ?? r.name, value: r.value }))
  }, [levelsQ.data, isRatio, settings.overlays.levels])

  const pivots = useMemo<PivotMark[]>(() => {
    if (isRatio || !settings.overlays.pivots || !pivotTf) return []
    const times = new Set(bars.map((b) => b.time))
    return ((pivotsQ.data?.data.result ?? []) as PivotRow[])
      .map((p) => ({
        time: Date.parse(`${p.date.slice(0, 10)}T00:00:00Z`) / 1000,
        kind: p.kind,
        confirmed: p.confirmed,
      }))
      .filter((p) => times.has(p.time))
  }, [pivotsQ.data, bars, isRatio, settings.overlays.pivots, pivotTf])

  const [hover, setHover] = useState<number | null>(null)
  const [range, setRange] = useState<[number, number] | null>(null)
  const rangeTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const onRange = useCallback((from: number, to: number) => {
    clearTimeout(rangeTimer.current)
    rangeTimer.current = setTimeout(() => setRange([from, to]), 250)
  }, [])
  useEffect(() => () => clearTimeout(rangeTimer.current), [])

  const set = (fn: (s: ChartSettings) => ChartSettings) => update(fn)
  const toggleOverlay = (key: Overlay) =>
    set((s) => ({ ...s, overlays: { ...s.overlays, [key]: !s.overlays[key] } }))
  const togglePane = (key: Pane) =>
    set((s) => ({ ...s, panes: { ...s.panes, [key]: !s.panes[key] } }))

  const others = (coinsData?.data ?? []).filter((c) => c.symbol !== coin)
  const loading = main.isPending || (isRatio && denom.isPending)
  const failed = main.isError || (isRatio && denom.isError)
  const refetch = () => {
    void main.refetch()
    if (isRatio) void denom.refetch()
  }
  const table = tf === '4h' ? 'candles_4h' : 'candles_daily'
  const linkRange = range ? { from: toDate(range[0]), to: toDate(range[1]) } : {}
  const title = isRatio ? `${coin} / ${ratioCoin}` : `${coin} / USD`

  return (
    <div className="mx-auto max-w-7xl space-y-2">
      <h1 className="sr-only">Charts</h1>
      <div
        className="flex flex-wrap items-center gap-1.5"
        role="toolbar"
        aria-label="Chart settings"
      >
        <div className="flex rounded-md border p-0.5" role="group" aria-label="Timeframe">
          {(Object.keys(TF_LABEL) as Timeframe[]).map((t) => (
            <Toggle key={t} pressed={tf === t} onClick={() => set((s) => ({ ...s, tf: t }))}>
              {TF_LABEL[t]}
            </Toggle>
          ))}
        </div>
        <div className="flex rounded-md border p-0.5" role="group" aria-label="Price scale">
          <Toggle pressed={settings.log} onClick={() => set((s) => ({ ...s, log: true }))}>
            Log
          </Toggle>
          <Toggle pressed={!settings.log} onClick={() => set((s) => ({ ...s, log: false }))}>
            Linear
          </Toggle>
        </div>
        <label className="flex items-center gap-1 text-xs text-muted-foreground">
          Ratio
          <select
            aria-label="Ratio denominator"
            value={ratioCoin ?? ''}
            onChange={(e) => set((s) => ({ ...s, ratio: e.target.value || null }))}
            className="h-7 rounded-md border bg-card px-1.5 font-mono text-xs text-foreground"
          >
            <option value="">off</option>
            {others.map((c) => (
              <option key={c.symbol} value={c.symbol}>
                {coin}/{c.symbol}
              </option>
            ))}
          </select>
        </label>
        <Menu label="Indicators">
          <DropdownMenuLabel>On price</DropdownMenuLabel>
          {INDICATOR_ITEMS.map(([key, label]) => (
            <Check
              key={key}
              checked={settings.overlays[key]}
              onCheckedChange={() => toggleOverlay(key)}
            >
              {label}
            </Check>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuLabel>Panes</DropdownMenuLabel>
          {PANE_ITEMS.map(([key, label]) => (
            <Check key={key} checked={settings.panes[key]} onCheckedChange={() => togglePane(key)}>
              {label}
            </Check>
          ))}
        </Menu>
        <Menu label="Overlays">
          <Check
            checked={settings.overlays.volume}
            disabled={isRatio}
            onCheckedChange={() => toggleOverlay('volume')}
          >
            Volume
          </Check>
          <Check
            checked={settings.overlays.levels}
            disabled={isRatio}
            onCheckedChange={() => toggleOverlay('levels')}
          >
            Key levels
          </Check>
          <Check
            checked={settings.overlays.pivots}
            disabled={isRatio || !pivotTf}
            onCheckedChange={() => toggleOverlay('pivots')}
          >
            Swing pivots (zigzag){!pivotTf && ' · 1D and 1W only'}
          </Check>
          {me?.features.mco && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>MCO (coming in v1.2)</DropdownMenuLabel>
              <Check checked={false} disabled>
                MCO levels
              </Check>
              <Check checked={false} disabled>
                MCO wave labels
              </Check>
            </>
          )}
        </Menu>
      </div>

      <Card size="sm" className="gap-1 px-3 py-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <h2 className="text-sm font-medium">
            {title}{' '}
            <span className="font-normal text-muted-foreground">
              · {TF_NAME[tf]} · {isRatio ? 'ratio' : 'USD'} · {settings.log ? 'log' : 'linear'}
            </span>
          </h2>
          <div className="flex gap-3">
            <ViewDataLink
              table={table}
              params={{ coin, ...linkRange }}
              label={isRatio ? `View data (${coin})` : 'View data'}
            />
            {isRatio && ratioCoin && (
              <ViewDataLink
                table={table}
                params={{ coin: ratioCoin, ...linkRange }}
                label={`View data (${ratioCoin})`}
              />
            )}
          </div>
        </div>
        <Readout bars={bars} index={hover} lines={lines} intraday={tf === '4h'} ratio={isRatio} />
        <div className="relative h-[min(68vh,640px)] min-h-[380px]">
          {(loading || failed) && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-card p-6">
              <div className="w-full max-w-sm">
                <QueryStatus isPending={loading} isError={failed} refetch={refetch} lines={3} />
              </div>
            </div>
          )}
          {!loading && !failed && bars.length === 0 && (
            <p className="absolute inset-0 z-10 flex items-center justify-center text-sm text-muted-foreground">
              No bars for this selection.
            </p>
          )}
          <CandleChart
            bars={bars}
            mode={isRatio ? 'line' : 'candles'}
            lines={lines}
            levels={levels}
            pivots={pivots}
            showVolume={settings.overlays.volume && !isRatio}
            log={settings.log}
            intraday={tf === '4h'}
            colors={colors}
            frameKey={`${coin}:${ratioCoin}:${tf}`}
            initialBars={INITIAL_BARS[tf]}
            onHover={setHover}
            onRange={onRange}
          />
        </div>
      </Card>
    </div>
  )
}
