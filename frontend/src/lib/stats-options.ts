import type { EChartOption } from '@/components/charts/EChart'

import type { ChartColors } from './chart-colors'
import { axisStyle, baseOption, divergingColors, escapeHtml, mix, signColor } from './echarts-theme'
import { formatDate, formatPct } from './format'
import {
  binIndex,
  heatmapCells,
  MONTHS,
  type Distribution,
  type MatrixRow,
  type SummaryRow,
} from './stats-data'

// ECharts options for the Stats tab: the monthly heatmap, seasonality bars, the return
// histogram and daily time series.

export type Stat = 'mean' | 'median'

// Colors saturate at ±40%: most months sit well inside it, and a few early-history months
// (+200% and more) would otherwise wash every other cell out to neutral.
export const HEATMAP_CLIP = 0.4

/** Whole percent in cells ("+12%"), one decimal in the tooltip. */
const cellPct = (v: number) => formatPct(v).replace(/\.\d%$/, '%')

export function monthlyHeatmapOption(matrix: MatrixRow[], c: ChartColors): EChartOption {
  const { years, cells } = heatmapCells(matrix)
  const axis = axisStyle(c)
  return {
    ...baseOption(c),
    grid: { left: 44, right: 8, top: 4, bottom: 52 },
    tooltip: {
      ...baseOption(c).tooltip,
      formatter: (p: { value: [number, number, number] }) =>
        `${MONTHS[p.value[0]]} ${years[p.value[1]]}: <b>${formatPct(p.value[2])}</b>`,
    },
    xAxis: {
      type: 'category',
      data: [...MONTHS],
      position: 'top',
      ...axis,
      splitLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: years.map(String),
      inverse: true, // newest year at the bottom reads like a calendar
      ...axis,
      splitLine: { show: false },
      axisTick: { show: false },
      axisLabel: { ...axis.axisLabel, hideOverlap: false },
    },
    visualMap: {
      type: 'continuous',
      min: -HEATMAP_CLIP,
      max: HEATMAP_CLIP,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemHeight: 160,
      itemWidth: 10,
      text: [`≥ +${HEATMAP_CLIP * 100}%`, `≤ −${HEATMAP_CLIP * 100}%`],
      textStyle: { color: c['muted-foreground'] },
      inRange: { color: divergingColors(c) },
    },
    series: [
      {
        type: 'heatmap',
        data: cells,
        // Cell labels take dark or light text from each cell's color (zrender inside-label fill).
        label: {
          show: true,
          fontSize: 10,
          formatter: (p: { value: number[] }) => cellPct(p.value[2]),
        },
        itemStyle: { borderColor: c.card, borderWidth: 1 },
        emphasis: { itemStyle: { borderColor: c.foreground, borderWidth: 1 } },
      },
    ],
  }
}

/** Histogram of returns with the current period's bin filled and a line at its value. */
export function distributionOption(d: Distribution, c: ChartColors): EChartOption {
  const axis = axisStyle(c)
  const current = binIndex(d.bins, d.current)
  const labels = d.counts.map((_, i) => `${formatPct(d.bins[i])} to ${formatPct(d.bins[i + 1])}`)
  const base = mix(c['series-1'], c.card, 0.35)
  return {
    ...baseOption(c),
    grid: { left: 44, right: 12, top: 24, bottom: 40 },
    tooltip: {
      ...baseOption(c).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number; value: number }[]) => {
        const p = params[0]
        if (!p) return ''
        const share = d.count ? p.value / d.count : 0
        return `${labels[p.dataIndex]}<br/><b>${p.value}</b> periods (${formatPct(share, false)})`
      },
    },
    xAxis: {
      type: 'category',
      data: d.counts.map((_, i) => (d.bins[i] + d.bins[i + 1]) / 2),
      name: 'Return',
      nameLocation: 'middle',
      nameGap: 26,
      ...axis,
      splitLine: { show: false },
      axisLabel: { ...axis.axisLabel, formatter: (v: string) => formatPct(Number(v)) },
    },
    yAxis: { type: 'value', name: 'Count', ...axis },
    series: [
      {
        type: 'bar',
        barCategoryGap: '8%',
        data: d.counts.map((n, i) => ({
          value: n,
          itemStyle: { color: i === current ? c['series-2'] : base },
        })),
        ...(current >= 0
          ? {
              markLine: {
                silent: true,
                symbol: 'none',
                lineStyle: { color: c['series-2'], type: 'dashed', width: 1.5 },
                label: { formatter: `Latest ${formatPct(d.current)}`, color: c.foreground },
                data: [{ xAxis: current }],
              },
            }
          : {}),
      },
    ],
  }
}

/** Mean or median return per period, bars colored by sign; the tooltip has all four numbers. */
export function seasonalityBarsOption(
  rows: SummaryRow[],
  labels: string[],
  stat: Stat,
  c: ChartColors,
): EChartOption {
  const axis = axisStyle(c)
  return {
    ...baseOption(c),
    grid: { left: 48, right: 8, top: 12, bottom: 28 },
    tooltip: {
      ...baseOption(c).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0]?.dataIndex ?? 0
        const r = rows[i]
        if (!r) return ''
        return (
          `<b>${labels[i]}</b><br/>Mean ${formatPct(r.mean)} · median ${formatPct(r.median)}` +
          `<br/>${formatPct(r.pct_positive, false)} positive · ${r.count} periods`
        )
      },
    },
    xAxis: {
      type: 'category',
      data: labels,
      ...axis,
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatPct(v) },
    },
    series: [
      {
        type: 'bar',
        data: rows.map((r) => ({ value: r[stat], itemStyle: { color: signColor(c, r[stat]) } })),
      },
    ],
  }
}

export interface Line {
  name: string
  color: string
  points: [string, number | null][] // UTC date, value
  area?: boolean
  width?: number
}

const formatNumber = (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 2 })
// ECharts reads a date string without a zone as local time, so days go in as UTC timestamps.
const utcMs = (date: string) => Date.parse(`${date.slice(0, 10)}T00:00:00Z`)

/** Daily lines on a UTC time axis; values are fractions shown as % unless `percent` is off. */
export function timeSeriesOption({
  lines,
  colors: c,
  percent = true,
  min,
  max,
}: {
  lines: Line[]
  colors: ChartColors
  percent?: boolean
  min?: number
  max?: number
}): EChartOption {
  const axis = axisStyle(c)
  const fmt = percent ? (v: number) => formatPct(v) : formatNumber
  return {
    ...baseOption(c),
    grid: { left: 52, right: 12, top: lines.length > 1 ? 28 : 12, bottom: 28 },
    legend:
      lines.length > 1
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
          .map(
            (p) =>
              `<div style="display:flex;gap:10px;justify-content:space-between">` +
              `<span><span style="color:${p.color}">●</span> ${escapeHtml(p.seriesName)}</span>` +
              `<span style="font-variant-numeric:tabular-nums">${fmt(p.value[1] as number)}</span></div>`,
          )
        const day = new Date(t).toISOString().slice(0, 10)
        return `<div style="margin-bottom:4px">${formatDate(day)}</div>${rows.join('')}`
      },
    },
    // Axis labels in UTC too, so a day never shows as the evening before.
    useUTC: true,
    xAxis: { type: 'time', ...axis, splitLine: { show: false } },
    yAxis: {
      type: 'value',
      min,
      max,
      ...axis,
      axisLabel: {
        ...axis.axisLabel,
        formatter: (v: number) => (percent ? formatPct(v) : formatNumber(v)),
      },
    },
    series: lines.map((l) => ({
      name: l.name,
      type: 'line',
      showSymbol: false,
      sampling: 'lttb',
      data: l.points.map(([d, v]) => [utcMs(d), v]),
      lineStyle: { width: l.width ?? 1.5 },
      itemStyle: { color: l.color },
      areaStyle: l.area ? { opacity: 0.25 } : undefined,
    })),
  }
}
