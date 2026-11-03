import type { EChartOption } from '@/components/charts/EChart'
import type { LevelLine } from '@/components/charts/CandleChart'

import type { ChartColors, ColorToken } from './chart-colors'
import { axisStyle, baseOption, escapeHtml } from './echarts-theme'
import { formatDate, formatPrice } from './format'
import type { McoCoinView, McoScenario, McoVideo } from './queries'

// MCO tab and chart helpers (Stage 6.2). Everything in an extract is AI-extracted, untrusted
// text: it is rendered as text only. Scenarios use our own colours (primary series-1,
// alternative series-4), never the colour he draws them in, which the model reads unreliably
// (D49), so that field is not shown.

export const MCO_CHANNEL = 'https://www.youtube.com/@MoreCryptoOnline'
export const SCENARIO_TOKEN: Record<McoScenario['name'], ColorToken> = {
  primary: 'series-1',
  alternative: 'series-4',
}
export const SCENARIO_LABEL: Record<McoScenario['name'], string> = {
  primary: 'Primary',
  alternative: 'Alternative',
}

export type Bias = McoCoinView['bias']
export const BIAS_TOKEN: Record<Bias, ColorToken> = {
  bullish: 'positive',
  bearish: 'negative',
  neutral: 'muted-foreground',
}

/** The view of `coin` in a video, if the video discusses it. */
export function coinView(video: McoVideo, coin: string): McoCoinView | undefined {
  return video.coins.find((c) => c.coin === coin)
}

/** Coins any of the videos discuss, core coins first, then alphabetically. */
export function videoCoins(videos: McoVideo[], core: readonly string[] = ['BTC', 'ETH', 'SOL']) {
  const all = new Set(videos.flatMap((v) => v.coins.map((c) => c.coin)))
  const rest = [...all].filter((c) => !core.includes(c)).sort()
  return [...core.filter((c) => all.has(c)), ...rest]
}

/** "Nov 2" in UTC, for short chart labels. */
export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

const truncate = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

/**
 * Price lines for the Charts tab from one video's view of a coin: each scenario's levels,
 * targets and invalidation in that scenario's colour, plus the shared levels (muted) when the
 * primary is shown. The same price within a group is drawn once; targets win over levels.
 */
export function mcoLines(
  video: McoVideo,
  coin: string,
  show: { primary: boolean; alternative: boolean },
): LevelLine[] {
  const view = coinView(video, coin)
  if (!view) return []
  const date = shortDate(video.published_at)
  const out: LevelLine[] = []
  const add = (group: Map<number, LevelLine>, value: number, what: string, line: LevelLine) => {
    if (!(value > 0)) return
    const prev = group.get(value)
    if (prev && !what.startsWith('target') && !what.startsWith('invalidation')) return
    group.set(value, line)
  }
  for (const s of view.scenarios) {
    if (!show[s.name]) continue
    const tag = s.name === 'primary' ? 'MCO P' : 'MCO Alt'
    const color = SCENARIO_TOKEN[s.name]
    const group = new Map<number, LevelLine>()
    const line = (value: number, what: string, style: LevelLine['style'] = 'dashed') => ({
      value,
      label: truncate(`${tag} ${what} · ${date}`, 34),
      color,
      style,
    })
    for (const l of s.levels) add(group, l.price, l.label, line(l.price, truncate(l.label, 16)))
    for (const t of s.targets) add(group, t, 'target', line(t, 'target', 'solid'))
    if (s.invalidation != null)
      add(group, s.invalidation, 'invalidation', line(s.invalidation, 'invalidation', 'dotted'))
    out.push(...group.values())
  }
  if (show.primary) {
    const taken = new Set(out.map((l) => l.value))
    for (const l of view.key_levels) {
      if (taken.has(l.price) || !(l.price > 0)) continue
      taken.add(l.price)
      out.push({
        value: l.price,
        label: truncate(`MCO ${truncate(l.label, 16)} · ${date}`, 34),
        color: 'muted-foreground',
        style: 'dotted',
      })
    }
  }
  return out
}

export interface ClosePoint {
  date: string // YYYY-MM-DD (UTC)
  close: number
}

const utcMs = (date: string) => Date.parse(`${date.slice(0, 10)}T00:00:00Z`)

/** The close on `day` or the last close before it (videos come out before the day closes). */
export function closeOn(closes: ClosePoint[], day: string): number | null {
  let lo = 0
  let hi = closes.length - 1
  let found: number | null = null
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (closes[mid].date <= day) {
      found = closes[mid].close
      lo = mid + 1
    } else hi = mid - 1
  }
  return found
}

/** One marker per video that discusses `coin`, coloured by his bias, over the daily close. */
export function biasTimelineOption(
  c: ChartColors,
  coin: string,
  closes: ClosePoint[],
  videos: McoVideo[],
): EChartOption {
  const axis = axisStyle(c)
  const marks: {
    value: [number, number]
    bias: Bias
    title: string
    confidence: string
    itemStyle: { color: string }
  }[] = []
  for (const v of videos) {
    const view = coinView(v, coin)
    if (!view) continue
    const day = v.published_at.slice(0, 10)
    const close = closeOn(closes, day)
    if (close == null) continue
    marks.push({
      value: [utcMs(day), close],
      bias: view.bias,
      title: v.title,
      confidence: view.extraction_confidence,
      itemStyle: { color: c[BIAS_TOKEN[view.bias]] },
    })
  }
  return {
    ...baseOption(c),
    grid: { left: 56, right: 16, top: 16, bottom: 28 },
    useUTC: true,
    tooltip: {
      ...baseOption(c).tooltip,
      trigger: 'item',
      formatter: (p: { seriesName: string; data: unknown }) => {
        if (p.seriesName !== 'MCO bias') {
          const [t, y] = (p.data as [number, number]) ?? [0, 0]
          return `${formatDate(new Date(t).toISOString().slice(0, 10))} (UTC)<br/>Close $${escapeHtml(formatPrice(y))}`
        }
        const m = p.data as (typeof marks)[number]
        const day = formatDate(new Date(m.value[0]).toISOString().slice(0, 10))
        return (
          `<div style="max-width:260px;white-space:normal">${escapeHtml(day)} (UTC) · ` +
          `<b>${escapeHtml(m.bias)}</b> (${escapeHtml(m.confidence)} confidence)<br/>` +
          `${escapeHtml(m.title)}</div>`
        )
      },
    },
    xAxis: { type: 'time', ...axis, splitLine: { show: false } },
    yAxis: {
      type: 'log',
      scale: true,
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => `$${formatPrice(v)}` },
    },
    series: [
      {
        name: `${coin} close`,
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 1.25, color: c['series-2'] },
        itemStyle: { color: c['series-2'] },
        data: closes.map((p) => [utcMs(p.date), p.close]),
      },
      {
        name: 'MCO bias',
        type: 'scatter',
        symbolSize: 10,
        z: 3,
        data: marks,
      },
    ],
  }
}

/** "70000 breakout" per line -> levels; null when a non-empty line doesn't parse. */
export function parseLevels(text: string): { price: number; label: string }[] | null {
  const out: { price: number; label: string }[] = []
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const m = /^\$?([\d,]*\.?\d+)\s+(.{1,64})$/.exec(line)
    if (!m) return null
    const price = Number(m[1].replace(/,/g, ''))
    if (!(price > 0)) return null
    out.push({ price, label: m[2].trim() })
  }
  return out
}
