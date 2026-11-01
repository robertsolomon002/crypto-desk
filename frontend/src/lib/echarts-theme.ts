import { format } from 'echarts/core'

import type { ChartColors } from './chart-colors'

// Shared ECharts styling from the theme tokens (resolved to sRGB by `useChartColors`), so the
// Cycles and Stats charts match the Lightweight Charts look in both themes.

const FONT = 'Geist Variable, ui-sans-serif, system-ui, sans-serif'

export const SERIES_TOKENS = ['series-1', 'series-2', 'series-3', 'series-4', 'series-5'] as const

export function baseOption(c: ChartColors) {
  return {
    animation: false,
    backgroundColor: 'transparent',
    textStyle: { fontFamily: FONT, color: c['muted-foreground'], fontSize: 11 },
    aria: { enabled: true },
    tooltip: {
      backgroundColor: c.card,
      borderColor: c.border,
      textStyle: { color: c.foreground, fontSize: 12, fontFamily: FONT },
      confine: true,
    },
  }
}

export function axisStyle(c: ChartColors) {
  return {
    axisLine: { lineStyle: { color: c.border } },
    axisTick: { lineStyle: { color: c.border } },
    axisLabel: { color: c['muted-foreground'], hideOverlap: true },
    splitLine: { lineStyle: { color: c.grid } },
    nameTextStyle: { color: c['muted-foreground'] },
  }
}

function rgbOf(color: string): [number, number, number] | null {
  const m = /rgba?\((\d+), (\d+), (\d+)/.exec(color)
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])]
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color)
  return hex ? [parseInt(hex[1], 16), parseInt(hex[2], 16), parseInt(hex[3], 16)] : null
}

/** `a` blended toward `b` by `t` (0 = a, 1 = b), as an opaque color. */
export function mix(a: string, b: string, t: number): string {
  const x = rgbOf(a)
  const y = rgbOf(b)
  if (!x || !y) return a
  const [r, g, bl] = x.map((v, i) => Math.round(v + (y[i] - v) * t))
  return `rgb(${r}, ${g}, ${bl})`
}

/**
 * Diverging colors for returns: negative, neutral (the card), positive. Opaque, so ECharts'
 * inside-label contrast (it picks dark or light text from the fill's luminance) sees the real
 * cell color.
 */
export function divergingColors(c: ChartColors): string[] {
  return [
    c.negative,
    mix(c.negative, c.card, 0.6),
    c.card,
    mix(c.positive, c.card, 0.6),
    c.positive,
  ]
}

export const signColor = (c: ChartColors, v: number | null | undefined) =>
  v == null ? c['muted-foreground'] : v < 0 ? c.negative : c.positive

/** HTML-escaped text for tooltip formatters (ECharts tooltips are HTML). */
export const escapeHtml = format.encodeHTML
