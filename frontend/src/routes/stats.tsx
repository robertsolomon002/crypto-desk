import { useMemo } from 'react'

import { ChartCard, Segmented } from '@/components/charts/ChartCard'
import { DistributionChart } from '@/components/charts/Distribution'
import { MonthlyHeatmap } from '@/components/charts/Heatmap'
import { SeasonalityBars } from '@/components/charts/SeasonalityBars'
import { TimeSeriesChart } from '@/components/charts/TimeSeries'
import { useChartColors, type ChartColors } from '@/lib/chart-colors'
import { useSelectedCoin } from '@/lib/coin'
import { mix, SERIES_TOKENS } from '@/lib/echarts-theme'
import { formatDate, formatPct, formatPrice } from '@/lib/format'
import {
  useCorrelation,
  useDistribution,
  useDrawdownEpisodes,
  useDrawdowns,
  useSeasonality,
  useVolatility,
} from '@/lib/queries'
import {
  correlationMatrix,
  MONTHS,
  ordinal,
  pairKeys,
  periodOf,
  sinceSpan,
  WEEKDAYS,
  type CorrRow,
  type Distribution,
  type DrawdownRow,
  type Episode,
  type Seasonality,
  type Span,
  type VolRow,
} from '@/lib/stats-data'
import type { Line, Stat } from '@/lib/stats-options'
import { useUrlState } from '@/lib/url-state'
import { cn } from '@/lib/utils'

const SPANS = ['all', '4y', '1y'] as const
const SPAN_OPTIONS = [
  ['all', 'All'],
  ['4y', '4Y'],
  ['1y', '1Y'],
] as const
const STATS = ['mean', 'median'] as const
const STAT_OPTIONS = [
  ['mean', 'Mean'],
  ['median', 'Median'],
] as const
const HORIZONS = ['1w', '1d', '30d'] as const
const HORIZON_OPTIONS = [
  ['1d', '1D'],
  ['1w', '1W'],
  ['30d', '30D'],
] as const
const WINDOWS = ['30', '90', '180'] as const
const WINDOW_OPTIONS = [
  ['30', '30-day'],
  ['90', '90-day'],
  ['180', '180-day'],
] as const

const HORIZON_TEXT: Record<Distribution['horizon'], (date: string) => string> = {
  '1d': (d) => `the latest day (${formatDate(d)})`,
  '1w': (d) => `the latest complete week (from ${formatDate(d)})`,
  '30d': (d) => `the latest 30 days (to ${formatDate(d)})`,
}
const HORIZON_UNIT: Record<Distribution['horizon'], string> = {
  '1d': 'days',
  '1w': 'weeks',
  '30d': 'overlapping 30-day windows',
}

const analytics = (fn: string, coin: string, extra: Record<string, string> = {}) => ({
  table: 'analytics',
  params: { fn, coin, ...extra },
})

function summaryRows(s: Seasonality | undefined, kind: 'monthly' | 'weekly' | 'dow') {
  return [...(s?.summary ?? [])]
    .map((row, i) => ({ row, period: periodOf(row, i, kind) }))
    .sort((a, b) => a.period - b.period)
}

function MonthSummary({ data }: { data: Seasonality }) {
  const rows = summaryRows(data, 'monthly')
  const line = (label: string, get: (r: (typeof rows)[number]['row']) => string) => (
    <tr className="border-b last:border-0">
      <th scope="row" className="px-1.5 py-1 text-left font-medium text-muted-foreground">
        {label}
      </th>
      {rows.map(({ row, period }) => (
        <td key={period} className="px-1.5 py-1 text-right">
          {get(row)}
        </td>
      ))}
    </tr>
  )
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] font-mono text-xs whitespace-nowrap tabular-nums">
        <caption className="sr-only">Per-month summary across years</caption>
        <thead>
          <tr className="border-b">
            <th className="px-1.5 py-1" />
            {rows.map(({ period }) => (
              <th key={period} className="px-1.5 py-1 text-right font-medium text-muted-foreground">
                {MONTHS[period - 1]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {line('Mean', (r) => formatPct(r.mean))}
          {line('Median', (r) => formatPct(r.median))}
          {line('% up', (r) => formatPct(r.pct_positive, false))}
        </tbody>
      </table>
    </div>
  )
}

/** Correlation cell background: blue for positive, orange for negative, stronger with |r|. */
function corrBackground(c: ChartColors, v: number | null): string | undefined {
  if (v == null) return undefined
  return mix(c.card, v >= 0 ? c['series-1'] : c['series-2'], Math.min(1, Math.abs(v)) * 0.55)
}

function CorrelationMatrix({ rows, coin }: { rows: CorrRow[]; coin: string }) {
  const colors = useChartColors()
  const { coins, values, date } = correlationMatrix(rows, coin)
  return (
    <div className="space-y-1">
      <table
        className="font-mono text-xs whitespace-nowrap tabular-nums"
        data-testid="correlation-matrix"
      >
        <caption className="sr-only">Latest rolling correlation between coins</caption>
        <thead>
          <tr>
            <th className="px-2 py-1" />
            {coins.map((c) => (
              <th
                key={c}
                scope="col"
                className="px-2 py-1 text-right font-medium text-muted-foreground"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {coins.map((a, i) => (
            <tr key={a}>
              <th scope="row" className="px-2 py-1 text-left font-medium text-muted-foreground">
                {a}
              </th>
              {values[i].map((v, j) => (
                <td
                  key={coins[j]}
                  className="min-w-14 px-2 py-1 text-right"
                  style={{ background: i === j ? undefined : corrBackground(colors, v) }}
                >
                  {v == null ? '—' : v.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {date && <p className="text-xs text-muted-foreground">As of {formatDate(date)}</p>}
    </div>
  )
}

function EpisodesTable({ rows }: { rows: Episode[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] font-mono text-xs whitespace-nowrap tabular-nums">
        <caption className="sr-only">Deepest drawdowns</caption>
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="px-2 py-1 text-left font-medium">Peak</th>
            <th className="px-2 py-1 text-right font-medium">Peak close</th>
            <th className="px-2 py-1 text-left font-medium">Trough</th>
            <th className="px-2 py-1 text-right font-medium">Depth</th>
            <th className="px-2 py-1 text-left font-medium">Recovered</th>
            <th className="px-2 py-1 text-right font-medium">Days</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.peak_date} className="border-b last:border-0">
              <td className="px-2 py-1">{e.peak_date}</td>
              <td className="px-2 py-1 text-right">{formatPrice(e.peak)}</td>
              <td className="px-2 py-1">{e.trough_date}</td>
              <td className="px-2 py-1 text-right text-negative">{formatPct(e.depth)}</td>
              <td className={cn('px-2 py-1', !e.recovery_date && 'text-muted-foreground')}>
                {e.recovery_date ?? 'not yet'}
              </td>
              <td className="px-2 py-1 text-right">{e.days}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function StatsPage() {
  const [coin] = useSelectedCoin()
  const colors = useChartColors()
  const [span, setSpan] = useUrlState<Span>('range', SPANS, 'all')
  const [stat, setStat] = useUrlState<Stat>('stat', STATS, 'mean')
  const [horizon, setHorizon] = useUrlState<Distribution['horizon']>('horizon', HORIZONS, '1w')
  const [windowText, setWindow] = useUrlState('window', WINDOWS, '90')
  const corrWindow = Number(windowText)

  const monthlyQ = useSeasonality(coin, 'monthly')
  const weeklyQ = useSeasonality(coin, 'weekly')
  const dowQ = useSeasonality(coin, 'dow')
  const distQ = useDistribution(coin, horizon)
  const ddQ = useDrawdowns(coin)
  const episodesQ = useDrawdownEpisodes(coin)
  const volQ = useVolatility(coin)
  const corrQ = useCorrelation(coin, corrWindow)

  const monthly = monthlyQ.data?.data.result as Seasonality | undefined
  const weekly = useMemo(
    () => summaryRows(weeklyQ.data?.data.result as Seasonality | undefined, 'weekly'),
    [weeklyQ.data],
  )
  const dow = useMemo(
    () => summaryRows(dowQ.data?.data.result as Seasonality | undefined, 'dow'),
    [dowQ.data],
  )
  const weekLabels = useMemo(() => weekly.map((w) => `W${w.period}`), [weekly])
  const dowLabels = useMemo(() => dow.map((d) => WEEKDAYS[d.period] ?? String(d.period)), [dow])
  const weeklyRows = useMemo(() => weekly.map((w) => w.row), [weekly])
  const dowRows = useMemo(() => dow.map((d) => d.row), [dow])
  const dist = distQ.data?.data.result as Distribution | undefined
  const episodes = (episodesQ.data?.data.result ?? []) as Episode[]

  const ddLines = useMemo<Line[]>(() => {
    const rows = sinceSpan((ddQ.data?.data.result ?? []) as DrawdownRow[], span)
    return [
      {
        name: 'Drawdown',
        color: colors.negative,
        area: true,
        points: rows.map((r) => [r.date, r.drawdown]),
      },
    ]
  }, [ddQ.data, span, colors])

  const volLines = useMemo<Line[]>(() => {
    const rows = sinceSpan((volQ.data?.data.result ?? []) as VolRow[], span)
    return [
      { name: '30-day', color: colors['series-1'], points: rows.map((r) => [r.date, r.vol30]) },
      {
        name: '90-day',
        color: colors['series-2'],
        width: 2,
        points: rows.map((r) => [r.date, r.vol90]),
      },
    ]
  }, [volQ.data, span, colors])

  const corrRows = useMemo(() => (corrQ.data?.data.result ?? []) as CorrRow[], [corrQ.data])
  const corrLines = useMemo<Line[]>(() => {
    const rows = sinceSpan(corrRows, span)
    return pairKeys(rows).map((key, i) => ({
      name: key,
      color: colors[SERIES_TOKENS[i % SERIES_TOKENS.length]],
      // Pairs with the selected coin are drawn thicker than the rest.
      width: key.split('/').includes(coin) ? 2 : 1,
      points: rows.map((r) => [r.date, r[key] ?? null]),
    }))
  }, [corrRows, span, colors, coin])

  return (
    <div className="mx-auto max-w-7xl space-y-3">
      <h1 className="sr-only">Stats</h1>

      <ChartCard
        title={`${coin} monthly returns`}
        units="% change, month-end close to month-end close (UTC)"
        data={[analytics('seasonality_monthly', coin)]}
        query={monthlyQ}
        empty={monthly?.matrix.length ? null : 'No monthly data.'}
      >
        {monthly && (
          <>
            <MonthlyHeatmap matrix={monthly.matrix} colors={colors} />
            <MonthSummary data={monthly} />
          </>
        )}
      </ChartCard>

      <div className="grid gap-3 lg:grid-cols-2">
        <ChartCard
          title="Weekly seasonality"
          units={`${stat} return by ISO week`}
          data={[analytics('seasonality_weekly', coin)]}
          query={weeklyQ}
          controls={
            <Segmented label="Statistic" value={stat} options={STAT_OPTIONS} onChange={setStat} />
          }
          empty={weekly.length ? null : 'No weekly data.'}
        >
          <SeasonalityBars
            rows={weeklyRows}
            labels={weekLabels}
            stat={stat}
            colors={colors}
            label="Return by ISO week of the year"
            testId="weekly-seasonality"
          />
        </ChartCard>
        <ChartCard
          title="Day of week"
          units={`${stat} daily return (UTC days)`}
          data={[analytics('seasonality_dow', coin)]}
          query={dowQ}
          empty={dow.length ? null : 'No daily data.'}
        >
          <SeasonalityBars
            rows={dowRows}
            labels={dowLabels}
            stat={stat}
            colors={colors}
            label="Return by day of the week"
            testId="dow-seasonality"
          />
        </ChartCard>
      </div>

      <ChartCard
        title="Return distribution"
        units={`count of ${HORIZON_UNIT[horizon]} per return bin`}
        data={[analytics('return_distribution', coin, { horizon })]}
        query={distQ}
        controls={
          <Segmented
            label="Horizon"
            value={horizon}
            options={HORIZON_OPTIONS}
            onChange={setHorizon}
          />
        }
        empty={dist?.counts.length ? null : 'Not enough data.'}
      >
        {dist && (
          <>
            {dist.current_date && dist.current_percentile != null && (
              <p className="text-xs text-muted-foreground" data-testid="distribution-current">
                {coin} returned{' '}
                <span className="font-mono text-foreground">{formatPct(dist.current)}</span> over{' '}
                {HORIZON_TEXT[horizon](dist.current_date)}: the{' '}
                <span className="font-mono text-foreground">
                  {ordinal(dist.current_percentile)} percentile
                </span>{' '}
                of {dist.count.toLocaleString('en-US')} {HORIZON_UNIT[horizon]}. Median{' '}
                {formatPct(dist.quantiles.p50)}, middle 90% {formatPct(dist.quantiles.p5)} to{' '}
                {formatPct(dist.quantiles.p95)}.
              </p>
            )}
            <DistributionChart data={dist} colors={colors} />
          </>
        )}
      </ChartCard>

      <div className="flex flex-wrap items-center gap-1.5" role="toolbar" aria-label="Time range">
        <span className="text-xs text-muted-foreground">Range for the charts below</span>
        <Segmented label="Range" value={span} options={SPAN_OPTIONS} onChange={setSpan} />
      </div>

      <ChartCard
        title={`${coin} drawdown from the all-time high`}
        units="% below the running ATH close"
        data={[analytics('drawdowns', coin)]}
        query={ddQ}
        empty={ddLines[0].points.length ? null : 'No data.'}
      >
        <TimeSeriesChart
          lines={ddLines}
          colors={colors}
          max={0}
          label="Drawdown from the all-time high close"
          testId="drawdown-chart"
        />
        {episodes.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer text-xs text-muted-foreground">
              Deepest {episodes.length} drawdowns
            </summary>
            <EpisodesTable rows={episodes} />
          </details>
        )}
      </ChartCard>

      <div className="grid gap-3 lg:grid-cols-2">
        <ChartCard
          title="Rolling volatility"
          units="annualized, daily log returns"
          data={[analytics('rolling_volatility', coin)]}
          query={volQ}
          empty={volLines[0].points.length ? null : 'No data.'}
        >
          <TimeSeriesChart
            lines={volLines}
            colors={colors}
            label="Rolling 30 and 90 day volatility"
            testId="volatility-chart"
          />
        </ChartCard>
        <ChartCard
          title="Rolling correlation"
          units={`${corrWindow}-day window, daily log returns`}
          data={[analytics('rolling_correlation', coin, { window: windowText })]}
          query={corrQ}
          controls={
            <Segmented
              label="Window"
              value={windowText}
              options={WINDOW_OPTIONS}
              onChange={setWindow}
            />
          }
          empty={corrRows.length ? null : 'Correlation needs at least two coins with data.'}
        >
          <CorrelationMatrix rows={corrRows} coin={coin} />
          <TimeSeriesChart
            lines={corrLines}
            colors={colors}
            percent={false}
            min={-1}
            max={1}
            label="Rolling correlation between coins"
            testId="correlation-chart"
          />
        </ChartCard>
      </div>
    </div>
  )
}
