import type { EChartOption } from '@/components/charts/EChart'

import type { ChartColors, ColorToken } from './chart-colors'
import { axisStyle, baseOption, escapeHtml } from './echarts-theme'
import { formatDate, formatPct } from './format'
import { shortDate } from './mco'
import type { ScoreStats, SignalOut, SignalSource, SourceScore } from './queries'

// Signals tab helpers (Stage 7.2, D52). Signals, rationales and briefs are model output: they
// are rendered as text only. Scores come from `signals/score.py` on the backend.

export const SOURCES: SignalSource[] = ['desk', 'coinflip', 'trend', 'mco']

export const SOURCE_LABEL: Record<SignalSource, string> = {
  desk: 'Desk',
  coinflip: 'Coin flip',
  trend: 'Trend rule',
  mco: 'MCO bias',
}

export const SOURCE_NOTE: Record<SignalSource, string> = {
  desk: 'The multi-agent desk (Haiku 5.5)',
  coinflip: 'Baseline: always flat at 0.5',
  trend: 'Baseline: long above the 20-week SMA',
  mco: "MCO's latest video bias (AI-extracted)",
}

export const SOURCE_TOKEN: Record<SignalSource, ColorToken> = {
  desk: 'series-1',
  coinflip: 'muted-foreground',
  trend: 'series-3',
  mco: 'series-4',
}

export const stanceLabel = (s: SignalOut['stance']) => (s === 'lean_long' ? 'lean long' : 'flat')

/** "60%" for a confidence of 0.6. */
export const confidencePct = (c: number) => `${Math.round(c * 100)}%`

/** A rate as "67% (2/3)", or a dash without data. */
export function rateText(rate: number | null | undefined, n?: number, of?: number): string {
  if (rate == null) return '—'
  const pct = formatPct(rate, false)
  return n != null && of != null ? `${pct} (${n}/${of})` : pct
}

export const brierText = (b: number | null | undefined) => (b == null ? '—' : b.toFixed(3))

/** What happened to a resolved signal, in a few words. */
export function outcomeText(s: SignalOut): string {
  const o = s.outcome
  if (!o) return 'open'
  const move =
    o.reference_close != null && o.reference_close > 0
      ? formatPct(o.week_close / o.reference_close - 1)
      : null
  const parts = [o.direction_hit ? 'hit' : 'miss']
  if (move) parts.push(`week ${move}`)
  if (o.first_hit === 'target') parts.push('target first')
  if (o.first_hit === 'invalidation') parts.push('invalidated first')
  if (s.stance === 'lean_long' && o.paper_pnl != null) parts.push(`P&L ${formatPct(o.paper_pnl)}`)
  return parts.join(' · ')
}

/** Coins of a week's signals, core first, then alphabetically. */
export function signalCoins(signals: SignalOut[], core: readonly string[] = ['BTC', 'ETH', 'SOL']) {
  const all = new Set(signals.map((s) => s.coin))
  return [...core.filter((c) => all.has(c)), ...[...all].filter((c) => !core.includes(c)).sort()]
}

/** Sources present in a week, in the scorecard order. */
export const signalSources = (signals: SignalOut[]) =>
  SOURCES.filter((src) => signals.some((s) => s.source === src))

/** signals[coin][source] */
export function signalGrid(signals: SignalOut[]): Map<string, Map<SignalSource, SignalOut>> {
  const grid = new Map<string, Map<SignalSource, SignalOut>>()
  for (const s of signals) {
    if (!grid.has(s.coin)) grid.set(s.coin, new Map())
    grid.get(s.coin)!.set(s.source, s)
  }
  return grid
}

export const earlyDays = (st: ScoreStats, weeks: number) =>
  st.early_days ? `early days: ${st.weeks} of ${weeks} weeks` : null

export type CumulativeMetric = 'paper_return' | 'hit_rate' | 'brier'

export const METRIC_LABEL: Record<CumulativeMetric, string> = {
  paper_return: 'Paper P&L',
  hit_rate: 'Hit rate',
  brier: 'Brier',
}

const METRIC_UNITS: Record<CumulativeMetric, string> = {
  paper_return: 'cumulative, after 0.2% per side, equal weight per week',
  hit_rate: 'cumulative share of weeks called right',
  brier: 'cumulative mean, lower is better; the coin flip scores 0.25',
}

export const metricUnits = (m: CumulativeMetric) => METRIC_UNITS[m]

const metricValue = (m: CumulativeMetric, v: number) =>
  m === 'brier' ? v.toFixed(3) : formatPct(v, m === 'paper_return')

/** One line per source over the resolved weeks. */
export function cumulativeOption(
  c: ChartColors,
  sources: SourceScore[],
  metric: CumulativeMetric,
): EChartOption {
  const axis = axisStyle(c)
  const weeks = [...new Set(sources.flatMap((s) => s.cumulative.map((p) => p.week)))].sort()
  return {
    ...baseOption(c),
    grid: { left: 48, right: 12, top: 28, bottom: 24 },
    legend: { top: 0, textStyle: { color: c['muted-foreground'] }, itemWidth: 14 },
    tooltip: {
      ...baseOption(c).tooltip,
      trigger: 'axis',
      formatter: (items: { seriesName: string; value: number | null; axisValue: string }[]) => {
        const head = `Week of ${escapeHtml(formatDate(items[0]?.axisValue))}`
        const rows = items
          .filter((i) => i.value != null)
          .map((i) => `${escapeHtml(i.seriesName)}: ${metricValue(metric, i.value as number)}`)
        return [head, ...rows].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: weeks,
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: string) => shortDate(`${v}T00:00:00Z`) },
    },
    yAxis: {
      type: 'value',
      scale: metric !== 'hit_rate',
      ...(metric === 'hit_rate' ? { min: 0, max: 1 } : {}),
      ...axis,
      axisLabel: {
        ...axis.axisLabel,
        formatter: (v: number) => (metric === 'brier' ? v.toFixed(2) : formatPct(v, false)),
      },
    },
    series: sources.map((s) => {
      const byWeek = new Map(s.cumulative.map((p) => [p.week, p[metric]]))
      return {
        name: SOURCE_LABEL[s.source],
        type: 'line',
        connectNulls: true,
        showSymbol: weeks.length < 30,
        symbolSize: 5,
        lineStyle: { width: s.source === 'desk' ? 2 : 1.5, color: c[SOURCE_TOKEN[s.source]] },
        itemStyle: { color: c[SOURCE_TOKEN[s.source]] },
        data: weeks.map((w) => byWeek.get(w) ?? null),
      }
    }),
  }
}
