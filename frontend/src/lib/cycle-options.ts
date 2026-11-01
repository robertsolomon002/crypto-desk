import type { EChartOption } from '@/components/charts/EChart'

import type { ChartColors } from './chart-colors'
import {
  ANCHOR_NAME,
  rowsAtDay,
  yValue,
  type AnchorMode,
  type CyclePath,
  type YMode,
  type YoyRow,
} from './cycles-data'
import { axisStyle, baseOption, escapeHtml, mix, SERIES_TOKENS } from './echarts-theme'
import { formatMultiple, formatPct, formatPrice } from './format'

// ECharts options for the Cycles tab: the cycle overlay and the year-over-year overlay.

const formatY = (v: number, y: YMode) => (y === 'multiple' ? formatMultiple(v) : formatPct(v))

/** Past cycles in muted series colors, the current one in the foreground color and thicker. */
export function cycleColor(c: ChartColors, index: number, isCurrent: boolean): string {
  return isCurrent ? c.foreground : c[SERIES_TOKENS[index % SERIES_TOKENS.length]]
}

export function cycleOverlayOption({
  paths,
  current,
  y,
  mode,
  colors: c,
}: {
  paths: CyclePath[]
  current: string | null
  y: YMode
  mode: AnchorMode
  colors: ChartColors
}): EChartOption {
  const axis = axisStyle(c)
  const now = paths.find((p) => p.cycle === current)?.rows.at(-1) ?? null
  const colorOf = new Map(paths.map((p, i) => [p.cycle, cycleColor(c, i, p.cycle === current)]))
  const series: object[] = paths.map((p) => {
    const isCurrent = p.cycle === current
    return {
      name: p.cycle,
      type: 'line',
      showSymbol: false,
      // A multiple of 0 can't sit on a log axis; anchors are positive prices, so this is a guard.
      data: p.rows.map((r) => [r.day, y === 'multiple' ? Math.max(r.multiple, 1e-9) : r.drawdown]),
      lineStyle: { width: isCurrent ? 2.5 : 1.25, opacity: isCurrent ? 1 : 0.55 },
      itemStyle: { color: colorOf.get(p.cycle) },
      z: isCurrent ? 3 : 2,
      emphasis: { focus: 'series', lineStyle: { width: isCurrent ? 3 : 2, opacity: 1 } },
      ...(isCurrent && now
        ? {
            markLine: {
              silent: true,
              symbol: 'none',
              lineStyle: { color: c['muted-foreground'], type: 'dashed', width: 1 },
              label: { formatter: `Today · day ${now.day}`, color: c.foreground, fontSize: 11 },
              data: [{ xAxis: now.day }],
            },
          }
        : {}),
    }
  })
  if (now) {
    series.push({
      name: 'Today',
      type: 'scatter',
      data: [[now.day, yValue(now, y)]],
      symbolSize: 9,
      itemStyle: { color: c.foreground, borderColor: c.card, borderWidth: 2 },
      z: 4,
      tooltip: { show: false },
    })
  }
  return {
    ...baseOption(c),
    grid: { left: 56, right: 20, top: 36, bottom: 44 },
    legend: {
      top: 0,
      data: paths.map((p) => p.cycle),
      textStyle: { color: c['muted-foreground'] },
      inactiveColor: c.border,
    },
    tooltip: {
      ...baseOption(c).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', snap: true, lineStyle: { color: c['muted-foreground'] } },
      formatter: (params: { axisValue: number }[]) => {
        const day = Math.round(Number(params[0]?.axisValue ?? 0))
        const rows = rowsAtDay(paths, day)
        if (!rows.length) return ''
        const lines = rows.map(
          ({ cycle, row }) =>
            `<div style="display:flex;gap:10px;justify-content:space-between">` +
            `<span><span style="color:${colorOf.get(cycle)}">●</span> ${escapeHtml(cycle)}` +
            ` <span style="opacity:.7">${escapeHtml(row.date)}</span></span>` +
            `<span style="font-variant-numeric:tabular-nums">${formatY(yValue(row, y), y)}` +
            ` · $${formatPrice(row.close)}</span></div>`,
        )
        return `<div style="margin-bottom:4px">Day ${day} after the ${ANCHOR_NAME[mode]}</div>${lines.join('')}`
      },
    },
    xAxis: {
      type: 'value',
      min: 0,
      max: 'dataMax',
      name: `Days since ${ANCHOR_NAME[mode]}`,
      nameLocation: 'middle',
      nameGap: 26,
      ...axis,
      splitLine: { show: false },
    },
    yAxis:
      y === 'multiple'
        ? {
            type: 'log',
            ...axis,
            axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatMultiple(v) },
          }
        : {
            type: 'value',
            max: 0,
            ...axis,
            axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatPct(v, false) },
          },
    series,
  }
}

/** Day of year (1 = Jan 1) as "Mar 1", read on a non-leap year so labels stay fixed. */
export function dayLabel(day: number): string {
  const d = new Date(Date.UTC(2023, 0, Math.round(day)))
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

export function yoyOption({
  years,
  colors: c,
}: {
  years: { year: number; rows: YoyRow[] }[]
  colors: ChartColors
}): EChartOption {
  const axis = axisStyle(c)
  const current = years.at(-1)?.year ?? null
  const byYear = new Map(years.map((y) => [y.year, new Map(y.rows.map((r) => [r.day, r]))]))
  // Older years fade toward the background so recent ones read first; the current year is bold.
  const colorOf = (i: number, year: number) =>
    year === current
      ? c.foreground
      : mix(c['series-1'], c.card, 0.65 * (1 - i / Math.max(1, years.length - 1)))
  return {
    ...baseOption(c),
    grid: { left: 56, right: 20, top: 36, bottom: 44 },
    legend: {
      type: 'scroll',
      top: 0,
      data: years.map((y) => String(y.year)),
      textStyle: { color: c['muted-foreground'] },
      pageTextStyle: { color: c['muted-foreground'] },
      inactiveColor: c.border,
    },
    tooltip: {
      ...baseOption(c).tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', snap: true, lineStyle: { color: c['muted-foreground'] } },
      formatter: (params: { axisValue: number }[]) => {
        const day = Math.round(Number(params[0]?.axisValue ?? 0))
        const lines = [...years]
          .reverse()
          .map((y, i) => {
            const row = byYear.get(y.year)?.get(day)
            if (!row) return ''
            const color = colorOf(years.length - 1 - i, y.year)
            return (
              `<div style="display:flex;gap:10px;justify-content:space-between">` +
              `<span><span style="color:${color}">●</span> ${y.year}</span>` +
              `<span style="font-variant-numeric:tabular-nums">${formatMultiple(row.multiple)}` +
              ` · $${formatPrice(row.close)}</span></div>`
            )
          })
          .join('')
        return lines && `<div style="margin-bottom:4px">${escapeHtml(dayLabel(day))}</div>${lines}`
      },
    },
    xAxis: {
      type: 'value',
      min: 1,
      max: 366,
      ...axis,
      splitLine: { show: false },
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => dayLabel(v) },
    },
    yAxis: {
      type: 'log',
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatMultiple(v) },
    },
    series: years.map((y, i) => ({
      name: String(y.year),
      type: 'line',
      showSymbol: false,
      data: y.rows.map((r) => [r.day, Math.max(r.multiple, 1e-9)]),
      lineStyle: { width: y.year === current ? 2.5 : 1.1 },
      itemStyle: { color: colorOf(i, y.year) },
      z: y.year === current ? 3 : 2,
      emphasis: { focus: 'series', lineStyle: { width: 2.5 } },
    })),
  }
}
