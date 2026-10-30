import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_SETTINGS,
  loadSettings,
  parseSettings,
  settingsKey,
  useChartSettings,
} from './chart-settings'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('parseSettings', () => {
  it('falls back to defaults for anything malformed', () => {
    expect(parseSettings(null)).toEqual(DEFAULT_SETTINGS)
    expect(parseSettings('nope')).toEqual(DEFAULT_SETTINGS)
    expect(parseSettings({ tf: '1m', log: 'yes', ratio: '<script>' })).toEqual(DEFAULT_SETTINGS)
  })

  it('keeps valid fields, drops unknown keys and fills missing ones', () => {
    const parsed = parseSettings({
      tf: '1w',
      log: false,
      ratio: 'BTC',
      overlays: { sma20: true, bogus: true, levels: 'x' },
      panes: { macd: true },
      extra: 1,
    })
    expect(parsed.tf).toBe('1w')
    expect(parsed.log).toBe(false)
    expect(parsed.ratio).toBe('BTC')
    expect(parsed.overlays.sma20).toBe(true)
    expect(parsed.overlays.levels).toBe(DEFAULT_SETTINGS.overlays.levels)
    expect(parsed.overlays).not.toHaveProperty('bogus')
    expect(parsed.panes).toEqual({ rsi: true, macd: true })
    expect(parsed).not.toHaveProperty('extra')
  })
})

describe('storage', () => {
  it('is per user, survives corrupt JSON and blocked storage', () => {
    expect(settingsKey('user_a')).not.toBe(settingsKey('user_b'))
    localStorage.setItem(settingsKey('user_a'), '{not json')
    expect(loadSettings(settingsKey('user_a'))).toEqual(DEFAULT_SETTINGS)
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(loadSettings(settingsKey('user_a'))).toEqual(DEFAULT_SETTINGS)
  })

  it('saves updates and reloads when the user changes', () => {
    localStorage.setItem(settingsKey('user_b'), JSON.stringify({ ...DEFAULT_SETTINGS, tf: '4h' }))
    const { result, rerender } = renderHook(({ id }) => useChartSettings(id), {
      initialProps: { id: 'user_a' as string | undefined },
    })
    act(() => result.current[1]((s) => ({ ...s, tf: '1w' })))
    expect(result.current[0].tf).toBe('1w')
    expect(JSON.parse(localStorage.getItem(settingsKey('user_a')) ?? '{}').tf).toBe('1w')
    rerender({ id: 'user_b' })
    expect(result.current[0].tf).toBe('4h')
  })
})
