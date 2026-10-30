import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { ViewDataLink } from '@/components/ViewDataLink'
import { useSelectedCoin } from '@/lib/coin'
import { formatDate, formatPct, formatPrice } from '@/lib/format'
import type { CoinCard } from '@/lib/queries'
import { cn } from '@/lib/utils'

const REGIMES: Record<string, string> = {
  uptrend: 'Uptrend',
  downtrend: 'Downtrend',
  range: 'Range',
  'high-vol': 'High volatility',
  insufficient_data: 'Not enough data',
}

/** A change with sign and arrow, so color is never the only cue. */
export function Change({ value, label }: { value: number | null; label: string }) {
  const tone = value == null || value === 0 ? '' : value > 0 ? 'text-positive' : 'text-negative'
  const arrow = value == null || value === 0 ? '' : value > 0 ? '▲' : '▼'
  return (
    <div className="flex flex-col">
      <span className="text-[11px] text-muted-foreground uppercase">{label}</span>
      <span className={cn('font-mono text-sm tabular-nums', tone)}>
        {arrow && (
          <span aria-hidden className="mr-0.5 text-[10px]">
            {arrow}
          </span>
        )}
        {formatPct(value)}
      </span>
    </div>
  )
}

function CoinCardView({ card, selected }: { card: CoinCard; selected: boolean }) {
  const [, setCoin] = useSelectedCoin()
  return (
    <Card
      size="sm"
      data-testid={`coin-card-${card.symbol}`}
      aria-current={selected ? 'true' : undefined}
      className={cn('gap-3 px-3', selected && 'ring-2 ring-primary')}
    >
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={() => setCoin(card.symbol)}
          className="text-left"
          aria-label={`Select ${card.name}`}
        >
          <span className="font-mono text-base font-semibold">{card.symbol}</span>{' '}
          <span className="text-xs text-muted-foreground">{card.name}</span>
        </button>
        <div className="flex gap-1">
          {card.is_watchlist && <Badge variant="outline">Watchlist</Badge>}
          <Badge variant="secondary">{REGIMES[card.regime] ?? card.regime}</Badge>
        </div>
      </div>
      <div>
        <div className="font-mono text-2xl font-semibold tabular-nums">
          ${formatPrice(card.close)}
        </div>
        <div className="text-xs text-muted-foreground">Close {formatDate(card.date)} (UTC)</div>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Change label="1d" value={card.change_1d} />
        <Change label="7d" value={card.change_7d} />
        <Change label="30d" value={card.change_30d} />
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted-foreground">From ATH</dt>
        <dd className="font-mono tabular-nums">
          {formatPct(card.ath_distance)}{' '}
          <span className="text-muted-foreground">
            (${formatPrice(card.ath)}, {formatDate(card.ath_date)})
          </span>
        </dd>
        <dt className="text-muted-foreground">Signal</dt>
        <dd className="text-muted-foreground">Arrives with Signals (v1.3)</dd>
        <dt className="text-muted-foreground">MCO bias</dt>
        <dd className="text-muted-foreground">Arrives with MCO (v1.2)</dd>
      </dl>
      <ViewDataLink table="candles_daily" params={{ coin: card.symbol }} />
    </Card>
  )
}

export function CoinCards({ cards }: { cards: CoinCard[] }) {
  const [coin] = useSelectedCoin()
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {cards.map((card) => (
        <CoinCardView key={card.symbol} card={card} selected={card.symbol === coin} />
      ))}
    </div>
  )
}
