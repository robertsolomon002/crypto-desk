// Chart indicators computed in the browser (D40), a port of
// backend/src/desk/analytics/indicators.py so they work on any bar series (1D, 1W, 4H, ratio).
// Causal like the backend: a value at bar t uses closes up to t only, and warm-up bars are NaN
// rather than partial-window values. `indicators.test.ts` checks parity against a fixture the
// backend generates.

export type Series = Float64Array

const DAY = 86_400
const WEEK = 7 * DAY

function nans(n: number): Series {
  return new Float64Array(n).fill(NaN)
}

export function sma(close: ArrayLike<number>, n: number): Series {
  const out = nans(close.length)
  let sum = 0
  for (let i = 0; i < close.length; i++) {
    sum += close[i]
    if (i >= n) sum -= close[i - n]
    if (i >= n - 1) out[i] = sum / n
  }
  return out
}

/** Recursive EMA (alpha = 2 / (n + 1)) seeded with the first non-NaN value, like pandas
 * `ewm(span=n, adjust=False, min_periods=n)`: NaN until n values have been seen. */
export function ema(x: ArrayLike<number>, n: number): Series {
  const out = nans(x.length)
  const alpha = 2 / (n + 1)
  let value = NaN
  let seen = 0
  for (let i = 0; i < x.length; i++) {
    const v = x[i]
    if (Number.isNaN(v)) continue
    value = seen === 0 ? v : (1 - alpha) * value + alpha * v
    seen++
    if (seen >= n) out[i] = value
  }
  return out
}

/** Middle band SMA(n), bands at ±k population standard deviations (ddof=0). */
export function bollinger(close: ArrayLike<number>, n = 20, k = 2) {
  const mid = sma(close, n)
  const upper = nans(close.length)
  const lower = nans(close.length)
  for (let i = n - 1; i < close.length; i++) {
    let ss = 0
    for (let j = i - n + 1; j <= i; j++) ss += (close[j] - mid[i]) ** 2
    const sd = Math.sqrt(ss / n)
    upper[i] = mid[i] + k * sd
    lower[i] = mid[i] - k * sd
  }
  return { mid, upper, lower }
}

/** Wilder's RSI: the first average is the mean of the first n changes, then
 * avg_t = (avg_{t-1} * (n - 1) + x_t) / n. 100 when there are no losses, 50 when flat. */
export function rsi(close: ArrayLike<number>, n = 14): Series {
  const out = nans(close.length)
  if (close.length <= n) return out
  let avgG = 0
  let avgL = 0
  for (let i = 1; i <= n; i++) {
    const d = close[i] - close[i - 1]
    avgG += Math.max(d, 0)
    avgL += Math.max(-d, 0)
  }
  avgG /= n
  avgL /= n
  for (let i = n; i < close.length; i++) {
    if (i > n) {
      const d = close[i] - close[i - 1]
      avgG = (avgG * (n - 1) + Math.max(d, 0)) / n
      avgL = (avgL * (n - 1) + Math.max(-d, 0)) / n
    }
    out[i] = avgL === 0 ? (avgG === 0 ? 50 : 100) : 100 - 100 / (1 + avgG / avgL)
  }
  return out
}

export function macd(close: ArrayLike<number>, fast = 12, slow = 26, signal = 9) {
  const f = ema(close, fast)
  const s = ema(close, slow)
  const line = f.map((v, i) => v - s[i])
  const sig = ema(line, signal)
  const hist = line.map((v, i) => v - sig[i])
  return { line, signal: sig, hist }
}

/** Monday 00:00 UTC of the week holding `t` (seconds). */
function weekStart(t: number): number {
  const day = Math.floor(t / DAY)
  const weekday = (day + 3) % 7 // 1970-01-01 was a Thursday; Monday = 0
  return (day - weekday) * DAY
}

/** 20-week SMA and 21-week EMA of complete weekly closes, mapped onto the bars (any timeframe
 * below weekly). A week's value becomes known when the week closes, so it applies from the
 * next Monday on. Weeks not fully covered by the bars, at either end, are dropped. */
export function weeklyBand(times: ArrayLike<number>, close: ArrayLike<number>, barSeconds = DAY) {
  const n = times.length
  const weeks: number[] = []
  const weekClose: number[] = []
  for (let i = 0; i < n; i++) {
    const w = weekStart(times[i])
    if (weeks.length && weeks[weeks.length - 1] === w) weekClose[weekClose.length - 1] = close[i]
    else {
      weeks.push(w)
      weekClose.push(close[i])
    }
  }
  const first = n ? times[0] : 0
  const end = n ? times[n - 1] + barSeconds : 0
  const keep = weeks.map((w) => w >= first && w + WEEK <= end)
  const kw = weeks.filter((_, i) => keep[i])
  const kc = weekClose.filter((_, i) => keep[i])
  const s = sma(kc, 20)
  const e = ema(kc, 21)
  const sma20w = nans(n)
  const ema21w = nans(n)
  let j = -1 // the last complete week whose value applies (its Monday + 7 days <= bar time)
  for (let i = 0; i < n; i++) {
    while (j + 1 < kw.length && kw[j + 1] + WEEK <= times[i]) j++
    if (j >= 0) {
      sma20w[i] = s[j]
      ema21w[i] = e[j]
    }
  }
  return { sma20w, ema21w }
}
