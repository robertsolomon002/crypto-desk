// Number and time formatting (ROADMAP Section 8): prices with 2 to 4 significant decimals,
// percentages to 1 decimal, local times with a UTC hint. A fixed locale keeps output stable.

const LOCALE = 'en-US'
const DASH = '—'

/** 2 decimals from 1 up; below 1, 4 significant digits (0.1234, 0.00001234). */
export function formatPrice(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return DASH
  if (Math.abs(value) >= 1) {
    return value.toLocaleString(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return value.toLocaleString(LOCALE, { maximumSignificantDigits: 4 })
}

/** A fraction as a percentage with 1 decimal: 0.0123 -> "+1.2%" (signed by default). */
export function formatPct(value: number | null | undefined, signed = true): string {
  if (value == null || !Number.isFinite(value)) return DASH
  const pct = Math.round(value * 1000) / 10
  const text = Math.abs(pct).toLocaleString(LOCALE, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })
  if (pct === 0) return `${text}%`
  return `${pct < 0 ? '−' : signed ? '+' : ''}${text}%`
}

/** A UTC calendar date ("2026-10-27") as "Oct 27, 2026": dates in the API are UTC days. */
export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return DASH
  const date = new Date(`${isoDate.slice(0, 10)}T00:00:00Z`)
  return date.toLocaleDateString(LOCALE, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

/** A UTC instant in the viewer's zone with the UTC time as a hint. */
export function formatDateTime(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return DASH
  const date = new Date(iso)
  const local = date.toLocaleString(LOCALE, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone,
  })
  const utc = date.toLocaleTimeString(LOCALE, {
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: 'UTC',
  })
  return `${local} (${utc} UTC)`
}

/** "3h ago", "2d ago" for headlines. */
export function formatAgo(iso: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60_000))
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

/** Only http(s) links are rendered as links (headline URLs are untrusted, Section 3.6). */
export function safeHttpUrl(url: string): string | null {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : null
  } catch {
    return null
  }
}

// alternative.me's own bands, measured from its full history (3,190 days, 2026-10-30, D39):
// <=25 Extreme Fear, 26-46 Fear, 47-54 Neutral, 55-75 Greed, >=76 Extreme Greed.
export function fngLabel(value: number): string {
  if (value <= 25) return 'Extreme Fear'
  if (value <= 46) return 'Fear'
  if (value <= 54) return 'Neutral'
  if (value <= 75) return 'Greed'
  return 'Extreme Greed'
}
