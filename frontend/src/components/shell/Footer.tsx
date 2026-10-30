export function Footer() {
  return (
    <footer className="space-y-1 border-t px-4 py-3 text-xs text-muted-foreground">
      <p>
        <strong className="font-medium text-foreground">Not financial advice.</strong> For
        information only. No trading, no exchange keys, no orders.
      </p>
      <p>
        Data: Coinbase (prices), Coin Metrics Community (BTC history before 2015, on-chain),
        alternative.me (Fear &amp; Greed), FRED (macro), CoinGecko (dominance), and the CoinDesk,
        Cointelegraph, Decrypt and The Block RSS feeds (headlines). Times are shown in your local
        zone; data dates are UTC.
      </p>
    </footer>
  )
}
