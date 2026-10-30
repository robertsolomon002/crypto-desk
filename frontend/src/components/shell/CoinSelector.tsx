import { useSelectedCoin } from '@/lib/coin'
import { useCoins } from '@/lib/queries'

/** Core coins, then the watchlist. A native select: keyboard and phone pickers come for free. */
export function CoinSelector() {
  const [coin, setCoin] = useSelectedCoin()
  const { data } = useCoins()
  const coins = data?.data ?? []
  const core = coins.filter((c) => !c.is_watchlist)
  const watchlist = coins.filter((c) => c.is_watchlist)
  // Keep the selected coin listed while the list loads (or if it is unknown).
  const known = coins.some((c) => c.symbol === coin)
  return (
    <label className="flex items-center gap-1.5 text-sm">
      <span className="sr-only">Coin</span>
      <select
        value={coin}
        onChange={(event) => setCoin(event.target.value)}
        className="h-8 rounded-md border bg-card px-2 font-mono text-sm font-medium"
      >
        {!known && <option value={coin}>{coin}</option>}
        {core.map((c) => (
          <option key={c.symbol} value={c.symbol}>
            {c.symbol}
          </option>
        ))}
        {watchlist.length > 0 && (
          <optgroup label="Watchlist">
            {watchlist.map((c) => (
              <option key={c.symbol} value={c.symbol}>
                {c.symbol}
              </option>
            ))}
          </optgroup>
        )}
      </select>
    </label>
  )
}
