import { useSearchParams } from 'react-router'

// The selected coin lives in the URL (`?coin=ETH`) so it survives tab switches, reloads and
// shared links. Tab links carry the current search string along.

export const DEFAULT_COIN = 'BTC'

export function useSelectedCoin(): [string, (coin: string) => void] {
  const [params, setParams] = useSearchParams()
  const coin = (params.get('coin') ?? DEFAULT_COIN).toUpperCase()
  return [
    coin,
    (next) =>
      setParams((prev) => {
        const out = new URLSearchParams(prev)
        out.set('coin', next.toUpperCase())
        return out
      }),
  ]
}

/** A "View data" deep link to the Data tab (Stage 3.4 reads the same parameters). */
export function dataLink(table: string, params: Record<string, string | undefined> = {}): string {
  const query = new URLSearchParams({ table })
  for (const [key, value] of Object.entries(params)) if (value) query.set(key, value)
  return `/data?${query.toString()}`
}
