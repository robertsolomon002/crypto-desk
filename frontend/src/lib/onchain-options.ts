import type { EChartOption } from '@/components/charts/EChart'

import type { ChartColors } from './chart-colors'
import { axisStyle, baseOption, escapeHtml } from './echarts-theme'
import { formatDate, formatPrice } from './format'
import type { Line } from './stats-options'

// ECharts options for the On-chain & Macro tab: daily lines on a UTC time axis with an optional
// second y-axis on the right (BTC price overlays), shaded value bands and reference lines.

export interface Axis {
  lines: Line[]
  format: (v: number) => string
  log?: boolean
  min?: number
  max?: number
}

/** A horizontal band on the left axis; a missing edge runs to the axis edge. */
export interface Band {
  from?: number
  to?: number
  color: string
  label?: string
}

export interface RefLine {
  value: number
  label?: string
}

// ECharts reads a date string without a zone as local time, so days go in as UTC timestamps.
const utcMs = (date: string) => Date.parse(`${date.slice(0, 10)}T00:00:00Z`)

const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 })
/** 1.2K, 3.4M; values below 0.01 (early-history log axes) in scientific notation. */
export const formatCompact = (v: number) =>
  v !== 0 && Math.abs(v) < 0.01 ? v.toExponential(0) : compact.format(v)
/** $77K, $1.2M; below $1 with 4 significant digits ($0.04951). */
export const formatUsd = (v: number) =>
  Math.abs(v) < 1 && v !== 0 ? `$${formatPrice(v)}` : `$${compact.format(v)}`
export const formatFixed = (digits: number) => (v: number) =>
  v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })

function yAxis(a: Axis, c: ChartColors, right: boolean) {
  const axis = axisStyle(c)
  return {
    type: a.log ? 'log' : 'value',
    position: right ? 'right' : 'left',
    scale: !a.log,
    // A log axis otherwise rounds out to whole steps of its tick interval (BTC hash rate spans
    // 11 powers of ten, and the axis ran to 1e10), so it is fitted to the data.
    min: a.min ?? (a.log ? 'dataMin' : undefined),
    max: a.max ?? (a.log ? 'dataMax' : undefined),
    ...axis,
    splitLine: right ? { show: false } : axis.splitLine,
    axisLabel: { ...axis.axisLabel, formatter: (v: number) => a.format(v) },
  }
}

export function dualAxisOption({
  left,
  right,
  bands = [],
  refLines = [],
  colors: c,
}: {
  left: Axis
  right?: Axis
  bands?: Band[]
  refLines?: RefLine[]
  colors: ChartColors
}): EChartOption {
  const all = [...left.lines, ...(right?.lines ?? [])]
  const formatOf = new Map<string, (v: number) => string>([
    ...left.lines.map((l) => [l.name, left.format] as const),
    ...(right?.lines ?? []).map((l) => [l.name, right!.format] as const),
  ])
  const series = all.map((l, i) => {
    const onRight = i >= left.lines.length
    return {
      name: l.name,
      type: 'line',
      yAxisIndex: onRight ? 1 : 0,
      showSymbol: l.points.length < 60, // dominance has only a few daily snapshots so far
      sampling: 'lttb',
      connectNulls: false,
      data: l.points.map(([d, v]) => [utcMs(d), v]),
      lineStyle: { width: l.width ?? 1.5 },
      itemStyle: { color: l.color },
      areaStyle: l.area ? { opacity: 0.2 } : undefined,
      z: onRight ? 1 : 2,
      ...(i === 0 && bands.length
        ? {
            markArea: {
              silent: true,
              label: { color: c['muted-foreground'], fontSize: 10, position: 'insideTopLeft' },
              data: bands.map((b) => [
                {
                  ...(b.from != null ? { yAxis: b.from } : {}),
                  name: b.label ?? '',
                  itemStyle: { color: b.color },
                },
                b.to != null ? { yAxis: b.to } : {},
              ]),
            },
          }
        : {}),
      ...(i === 0 && refLines.length
        ? {
            markLine: {
              silent: true,
              symbol: 'none',
              lineStyle: { color: c['muted-foreground'], type: 'dashed', width: 1 },
              label: { color: c['muted-foreground'], fontSize: 10, position: 'insideEndTop' },
              data: refLines.map((r) => ({ yAxis: r.value, name: r.label ?? '' })),
            },
          }
        : {}),
    }
  })
  const axis = axisStyle(c)
  return {
    ...baseOption(c),
    grid: { left: 56, right: right ? 60 : 12, top: all.length > 1 ? 28 : 12, bottom: 28 },
    legend:
      all.length > 1
        ? { top: 0, textStyle: { color: c['muted-foreground'] }, inactiveColor: c.border }
        : undefined,
    tooltip: {
      ...baseOption(c).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: c['muted-foreground'] } },
      formatter: (
        params: { seriesName: string; value: [number, number | null]; color: string }[],
      ) => {
        const t = params[0]?.value[0]
        if (t == null) return ''
        const rows = params
          .filter((p) => p.value[1] != null)
          .map((p) => {
            const fmt = formatOf.get(p.seriesName) ?? String
            return (
              `<div style="display:flex;gap:10px;justify-content:space-between">` +
              `<span><span style="color:${p.color}">●</span> ${escapeHtml(p.seriesName)}</span>` +
              `<span style="font-variant-numeric:tabular-nums">${escapeHtml(fmt(p.value[1] as number))}</span></div>`
            )
          })
        const when = formatDate(new Date(t).toISOString().slice(0, 10))
        return `<div style="margin-bottom:4px">${when} (UTC)</div>${rows.join('')}`
      },
    },
    useUTC: true, // axis labels in UTC, so a day never shows as the evening before
    xAxis: { type: 'time', ...axis, splitLine: { show: false } },
    yAxis: right ? [yAxis(left, c, false), yAxis(right, c, true)] : [yAxis(left, c, false)],
    series,
  }
}
