import { describe, expect, it } from 'vitest'

import {
  fngLabel,
  formatAgo,
  formatDate,
  formatDateTime,
  formatPct,
  formatPrice,
  safeHttpUrl,
} from './format'

describe('format', () => {
  it('formats prices with 2 decimals, or 4 significant digits below 1', () => {
    expect(formatPrice(90123.456)).toBe('90,123.46')
    expect(formatPrice(14.3)).toBe('14.30')
    expect(formatPrice(0.123456)).toBe('0.1235')
    expect(formatPrice(0.0000123456)).toBe('0.00001235')
    expect(formatPrice(null)).toBe('—')
  })

  it('formats percentages to 1 decimal with a sign', () => {
    expect(formatPct(0.0123)).toBe('+1.2%')
    expect(formatPct(-0.2857)).toBe('−28.6%')
    expect(formatPct(0.00001)).toBe('0.0%')
    expect(formatPct(0.5, false)).toBe('50.0%')
    expect(formatPct(undefined)).toBe('—')
  })

  it('shows UTC dates as dates and instants in local time with a UTC hint', () => {
    expect(formatDate('2026-10-27')).toBe('Oct 27, 2026')
    expect(formatDateTime('2026-11-04T19:00:00Z', 'America/Toronto')).toBe(
      'Nov 4, 14:00 (19:00 UTC)',
    )
  })

  it('formats ages', () => {
    const now = new Date('2026-10-30T12:00:00Z')
    expect(formatAgo('2026-10-30T11:15:00Z', now)).toBe('45m ago')
    expect(formatAgo('2026-10-29T12:00:00Z', now)).toBe('24h ago')
    expect(formatAgo('2026-10-25T12:00:00Z', now)).toBe('5d ago')
  })

  it('only lets http(s) URLs through', () => {
    expect(safeHttpUrl('https://example.com/a')).toBe('https://example.com/a')
    expect(safeHttpUrl('javascript:alert(1)')).toBeNull()
    expect(safeHttpUrl('data:text/html,x')).toBeNull()
    expect(safeHttpUrl('not a url')).toBeNull()
  })

  it('uses the alternative.me Fear & Greed bands', () => {
    expect([25, 26, 46, 47, 54, 55, 75, 76].map(fngLabel)).toEqual([
      'Extreme Fear',
      'Fear',
      'Fear',
      'Neutral',
      'Neutral',
      'Greed',
      'Greed',
      'Extreme Greed',
    ])
  })
})
