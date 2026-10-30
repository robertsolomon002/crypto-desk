import { useEffect, useState } from 'react'

// Lightweight Charts parses colors itself and only understands sRGB strings, while the theme
// tokens are oklch (index.css). Each token is resolved to `rgb(...)` through a 1x1 canvas, and
// re-resolved when the theme class on <html> changes.

const TOKENS = [
  'background',
  'card',
  'foreground',
  'muted-foreground',
  'border',
  'grid',
  'positive',
  'negative',
  'series-1',
  'series-2',
  'series-3',
  'series-4',
  'series-5',
] as const
export type ColorToken = (typeof TOKENS)[number]
export type ChartColors = Record<ColorToken, string>

// Used where there is no canvas (jsdom) or a token is missing.
const FALLBACK: ChartColors = {
  background: '#16181d',
  card: '#1d2026',
  foreground: '#e8eaee',
  'muted-foreground': '#a3a8b0',
  border: '#33373f',
  grid: '#2a2e35',
  positive: '#1a9e85',
  negative: '#e0592a',
  'series-1': '#0072b2',
  'series-2': '#e69f00',
  'series-3': '#009e73',
  'series-4': '#cc79a7',
  'series-5': '#d55e00',
}

function toRgb(ctx: CanvasRenderingContext2D, color: string): string | null {
  ctx.clearRect(0, 0, 1, 1)
  ctx.fillStyle = '#000'
  ctx.fillStyle = color // ignored if the browser can't parse it
  ctx.fillRect(0, 0, 1, 1)
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
  if (a === 0) return null
  // Translucent tokens (the dark theme's border and grid) keep their alpha.
  return a === 255 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`
}

export function readChartColors(): ChartColors {
  if (/jsdom/.test(navigator.userAgent)) return FALLBACK // unit tests: no canvas
  let ctx: CanvasRenderingContext2D | null
  try {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 1
    ctx = canvas.getContext('2d', { willReadFrequently: true })
  } catch {
    ctx = null
  }
  if (!ctx) return FALLBACK
  const style = getComputedStyle(document.documentElement)
  const out = { ...FALLBACK }
  for (const token of TOKENS) {
    const raw = style.getPropertyValue(`--${token}`).trim()
    const rgb = raw ? toRgb(ctx, raw) : null
    if (rgb) out[token] = rgb
  }
  return out
}

/** A resolved color with its alpha multiplied by `alpha`, for translucent volume bars. */
export function withAlpha(rgb: string, alpha: number): string {
  const m = /rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)/.exec(rgb)
  if (m) return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${+(Number(m[4] ?? 1) * alpha).toFixed(3)})`
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(rgb)
  if (hex)
    return `rgba(${hex
      .slice(1)
      .map((h) => parseInt(h, 16))
      .join(', ')}, ${alpha})`
  return rgb
}

/** The chart palette, updated when the theme toggles. */
export function useChartColors(): ChartColors {
  const [colors, setColors] = useState(readChartColors)
  useEffect(() => {
    const observer = new MutationObserver(() => setColors(readChartColors()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])
  return colors
}
