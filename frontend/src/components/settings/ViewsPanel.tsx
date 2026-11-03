import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { QueryStatus } from '@/components/overview/Panel'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { formatDate, formatPrice } from '@/lib/format'
import { parseLevels } from '@/lib/mco'
import { apiAction, useCoins, useViews, type ManualViewIn } from '@/lib/queries'
import { cn } from '@/lib/utils'

// Settings → Outside views (admin, Stage 6.2): Rob's manual views from any analyst. They sit
// next to MCO's extracts in `/api/views`, the agent's `get_external_views` tool and the desk's
// context analyst.

const input = 'h-8 rounded-md border bg-card px-2 font-mono text-sm'

function ErrorText({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="text-sm text-negative">
      {error instanceof Error ? error.message : 'Something went wrong.'}
    </p>
  )
}

export function ViewsPanel() {
  const client = useQueryClient()
  const coins = useCoins()
  const views = useViews(null, 50)
  const [source, setSource] = useState('')
  const [coin, setCoin] = useState('BTC')
  const [bias, setBias] = useState<ManualViewIn['bias']>('neutral')
  const [levels, setLevels] = useState('')
  const [invalidation, setInvalidation] = useState('')
  const [url, setUrl] = useState('')
  const parsed = parseLevels(levels)
  const inval = invalidation.trim() ? Number(invalidation.replace(/,/g, '')) : null
  const valid =
    source.trim() !== '' &&
    parsed !== null &&
    (inval === null || (Number.isFinite(inval) && inval > 0))
  const refresh = () => void client.invalidateQueries({ queryKey: ['views'] })

  const adding = useMutation({
    mutationFn: () =>
      apiAction(
        api.POST('/api/admin/views', {
          body: {
            source: source.trim(),
            coin,
            bias,
            levels: parsed ?? [],
            invalidation: inval,
            url: url.trim() || null,
          },
        }),
      ),
    onSuccess: () => {
      setLevels('')
      setInvalidation('')
      setUrl('')
      refresh()
    },
  })
  const removing = useMutation({
    mutationFn: (id: number) =>
      apiAction(api.DELETE('/api/admin/views/{view_id}', { params: { path: { view_id: id } } })),
    onSuccess: refresh,
  })
  const manual = (views.data?.data ?? []).filter((v) => v.kind === 'manual')

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (valid) adding.mutate()
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Add a view from any analyst. It is shown to the agent and the desk as an outside view right
        away, next to MCO&apos;s. Levels: one per line, price then label (for example{' '}
        <span className="font-mono">70000 breakout</span>).
      </p>
      <form
        className="grid max-w-xl gap-2 sm:grid-cols-2"
        aria-label="Add a view"
        onSubmit={onSubmit}
      >
        <label className="space-y-1 text-xs text-muted-foreground">
          Source
          <input
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="Analyst or channel"
            maxLength={64}
            className={cn(input, 'block w-full font-sans')}
          />
        </label>
        <label className="space-y-1 text-xs text-muted-foreground">
          Coin
          <select
            value={coin}
            onChange={(e) => setCoin(e.target.value)}
            className={cn(input, 'block w-full')}
          >
            {(coins.data?.data ?? []).map((c) => (
              <option key={c.symbol} value={c.symbol}>
                {c.symbol}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs text-muted-foreground">
          Bias
          <select
            value={bias}
            onChange={(e) => setBias(e.target.value as ManualViewIn['bias'])}
            className={cn(input, 'block w-full')}
          >
            <option value="bullish">bullish</option>
            <option value="bearish">bearish</option>
            <option value="neutral">neutral</option>
          </select>
        </label>
        <label className="space-y-1 text-xs text-muted-foreground">
          Invalidation (optional)
          <input
            value={invalidation}
            onChange={(e) => setInvalidation(e.target.value)}
            inputMode="decimal"
            placeholder="61000"
            className={cn(input, 'block w-full')}
          />
        </label>
        <label className="space-y-1 text-xs text-muted-foreground sm:col-span-2">
          Levels (optional)
          <textarea
            value={levels}
            onChange={(e) => setLevels(e.target.value)}
            rows={3}
            placeholder={'70000 breakout\n58000 support'}
            className={cn(input, 'block h-auto w-full py-1')}
          />
        </label>
        <label className="space-y-1 text-xs text-muted-foreground sm:col-span-2">
          Link (optional)
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            type="url"
            placeholder="https://…"
            className={cn(input, 'block w-full font-sans')}
          />
        </label>
        <div className="flex items-center gap-2 sm:col-span-2">
          <Button size="sm" type="submit" disabled={!valid || adding.isPending}>
            {adding.isPending ? 'Saving…' : 'Add view'}
          </Button>
          {parsed === null && (
            <span className="text-xs text-negative">
              Each level line needs a price and a label.
            </span>
          )}
        </div>
      </form>
      <ErrorText error={adding.error} />
      <QueryStatus {...views} lines={2} />
      {manual.length > 0 && (
        <ul className="divide-y rounded-md border text-sm" aria-label="Manual views">
          {manual.map((v) => (
            <li key={v.id} className="flex items-center justify-between gap-2 px-3 py-2">
              <span className="min-w-0">
                <span className="block truncate">
                  {v.source} · <span className="font-mono">{v.coin}</span> · {v.bias}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatDate(v.published_at.slice(0, 10))}
                  {v.levels.length > 0 && ` · ${v.levels.length} levels`}
                  {v.invalidation != null && ` · invalidation $${formatPrice(v.invalidation)}`}
                </span>
              </span>
              <Button
                size="sm"
                variant="ghost"
                disabled={removing.isPending}
                aria-label={`Delete the ${v.source} view on ${v.coin}`}
                onClick={() => removing.mutate(Number(v.id.split(':')[1]))}
              >
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
      {views.isSuccess && manual.length === 0 && (
        <p className="text-sm text-muted-foreground">No manual views yet.</p>
      )}
      <ErrorText error={removing.error} />
    </div>
  )
}
