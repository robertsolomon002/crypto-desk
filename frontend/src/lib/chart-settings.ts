import { useCallback, useState } from 'react'

// Charts tab settings, saved per user in localStorage (ROADMAP 3.2). Stored JSON is untrusted:
// unknown keys are dropped and anything malformed falls back to the default, so an old or
// hand-edited value can never break the page. Storage can be missing or throw (private
// windows), so every access is guarded.

export const TIMEFRAMES = ['1d', '1w', '4h'] as const
export type Timeframe = (typeof TIMEFRAMES)[number]

export const OVERLAYS = [
  'sma20',
  'sma50',
  'sma200',
  'ema20',
  'ema50',
  'ema200',
  'band',
  'bb',
  'volume',
  'levels',
  'pivots',
] as const
export type Overlay = (typeof OVERLAYS)[number]

export const PANES = ['rsi', 'macd'] as const
export type Pane = (typeof PANES)[number]

export interface ChartSettings {
  tf: Timeframe
  log: boolean
  /** The denominator coin in ratio mode (the selected coin is the numerator), or null. */
  ratio: string | null
  overlays: Record<Overlay, boolean>
  panes: Record<Pane, boolean>
}

export const DEFAULT_SETTINGS: ChartSettings = {
  tf: '1d',
  log: true,
  ratio: null,
  overlays: {
    sma20: false,
    sma50: true,
    sma200: true,
    ema20: false,
    ema50: false,
    ema200: false,
    band: true,
    bb: false,
    volume: true,
    levels: true,
    pivots: false,
  },
  panes: { rsi: true, macd: false },
}

export const settingsKey = (userId: string | undefined) => `desk.charts.v1.${userId ?? 'anon'}`

function flags<K extends string>(keys: readonly K[], raw: unknown, fallback: Record<K, boolean>) {
  const src = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  return Object.fromEntries(
    keys.map((k) => [k, typeof src[k] === 'boolean' ? src[k] : fallback[k]]),
  ) as Record<K, boolean>
}

/** A valid settings object from anything parsed out of storage. */
export function parseSettings(raw: unknown): ChartSettings {
  const d = DEFAULT_SETTINGS
  if (!raw || typeof raw !== 'object') return d
  const s = raw as Record<string, unknown>
  return {
    tf: TIMEFRAMES.includes(s.tf as Timeframe) ? (s.tf as Timeframe) : d.tf,
    log: typeof s.log === 'boolean' ? s.log : d.log,
    ratio: typeof s.ratio === 'string' && /^[A-Z0-9]{1,15}$/.test(s.ratio) ? s.ratio : null,
    overlays: flags(OVERLAYS, s.overlays, d.overlays),
    panes: flags(PANES, s.panes, d.panes),
  }
}

export function loadSettings(key: string): ChartSettings {
  try {
    const saved = localStorage.getItem(key)
    return saved ? parseSettings(JSON.parse(saved)) : DEFAULT_SETTINGS
  } catch {
    return DEFAULT_SETTINGS
  }
}

export function saveSettings(key: string, settings: ChartSettings): void {
  try {
    localStorage.setItem(key, JSON.stringify(settings))
  } catch {
    // the settings still apply for this visit
  }
}

/** Settings for one user; reloads when the user changes (sign-in finishing after first render). */
export function useChartSettings(
  userId: string | undefined,
): [ChartSettings, (update: (s: ChartSettings) => ChartSettings) => void] {
  const key = settingsKey(userId)
  const [state, setState] = useState(() => ({ key, settings: loadSettings(key) }))
  const current = state.key === key ? state.settings : loadSettings(key)
  if (state.key !== key) setState({ key, settings: current })
  const update = useCallback(
    (fn: (s: ChartSettings) => ChartSettings) =>
      setState((prev) => {
        const next = fn(prev.settings)
        saveSettings(prev.key, next)
        return { key: prev.key, settings: next }
      }),
    [],
  )
  return [current, update]
}
