import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { QueryStatus } from '@/components/overview/Panel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { formatDate, formatDateTime } from '@/lib/format'
import {
  apiAction,
  useInvites,
  useUsage,
  useUsers,
  useWatchlist,
  type Eligibility,
} from '@/lib/queries'
import { cn } from '@/lib/utils'

const input = 'h-8 rounded-md border bg-card px-2 font-mono text-sm'
const usd = (v: number) =>
  `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`

function ErrorText({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="text-sm text-negative">
      {error instanceof Error ? error.message : 'Something went wrong.'}
    </p>
  )
}

// --- Watchlist ----------------------------------------------------------------------------------

export function WatchlistPanel() {
  const client = useQueryClient()
  const list = useWatchlist(true)
  const [symbol, setSymbol] = useState('')
  const [name, setName] = useState('')
  const [check, setCheck] = useState<Eligibility | null>(null)
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['admin', 'watchlist'] })
    void client.invalidateQueries({ queryKey: ['coins'] })
    void client.invalidateQueries({ queryKey: ['overview'] })
  }
  const checking = useMutation({
    mutationFn: (s: string) =>
      apiAction(
        api.GET('/api/admin/watchlist/check/{symbol}', { params: { path: { symbol: s } } }),
      ),
    onSuccess: (result) => {
      setCheck(result)
      if (result.name && !name) setName(result.name)
    },
  })
  const adding = useMutation({
    mutationFn: () =>
      apiAction(api.POST('/api/admin/watchlist', { body: { symbol, name, aliases: [] } })),
    onSuccess: () => {
      setSymbol('')
      setName('')
      setCheck(null)
      refresh()
    },
  })
  const removing = useMutation({
    mutationFn: (s: string) =>
      apiAction(api.DELETE('/api/admin/watchlist/{symbol}', { params: { path: { symbol: s } } })),
    onSuccess: refresh,
  })

  const onCheck = (e: FormEvent) => {
    e.preventDefault()
    adding.reset()
    if (/^[A-Z0-9]{2,10}$/.test(symbol)) checking.mutate(symbol)
  }
  const rows = list.data ?? []

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Up to 10 extra coins beside BTC, ETH and SOL. A coin needs a Coinbase USD market and at
        least a year of history. The next daily job (00:20 UTC) loads its candles.
      </p>
      <QueryStatus {...list} lines={2} />
      {rows.length > 0 ? (
        <ul className="divide-y rounded-md border text-sm" aria-label="Watchlist">
          {rows.map((c) => (
            <li key={c.symbol} className="flex items-center justify-between gap-2 px-3 py-2">
              <span>
                <span className="font-mono font-medium">{c.symbol}</span>{' '}
                <span className="text-muted-foreground">{c.name}</span>
                <span className="block text-xs text-muted-foreground">
                  added {formatDate(c.added_at)}
                </span>
              </span>
              <Button
                size="sm"
                variant="ghost"
                disabled={removing.isPending}
                onClick={() => removing.mutate(c.symbol)}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        list.isSuccess && <p className="text-sm text-muted-foreground">The watchlist is empty.</p>
      )}
      <ErrorText error={removing.error} />

      <form
        onSubmit={onCheck}
        className="flex flex-wrap items-center gap-2"
        aria-label="Add a coin"
      >
        <label className="sr-only" htmlFor="watch-symbol">
          Symbol
        </label>
        <input
          id="watch-symbol"
          placeholder="Symbol, e.g. LINK"
          value={symbol}
          maxLength={10}
          onChange={(e) => {
            setSymbol(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))
            setCheck(null)
            setName('')
          }}
          className={cn(input, 'w-40')}
        />
        <Button
          size="sm"
          variant="outline"
          type="submit"
          disabled={symbol.length < 2 || checking.isPending}
        >
          {checking.isPending ? 'Checking…' : 'Check'}
        </Button>
      </form>
      <ErrorText error={checking.error} />
      {check && (
        <div className="space-y-2 rounded-md border p-3 text-sm" data-testid="eligibility">
          {check.eligible ? (
            <>
              <p className="text-positive">
                {check.market} is on Coinbase with at least a year of history.
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <label htmlFor="watch-name" className="text-xs text-muted-foreground">
                  Name
                </label>
                <input
                  id="watch-name"
                  value={name}
                  maxLength={64}
                  onChange={(e) => setName(e.target.value)}
                  className={cn(input, 'w-48 font-sans')}
                />
                <Button
                  size="sm"
                  disabled={!name.trim() || adding.isPending}
                  onClick={() => adding.mutate()}
                >
                  Add {check.symbol}
                </Button>
              </div>
            </>
          ) : (
            <ul className="list-disc pl-5 text-negative">
              {check.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <ErrorText error={adding.error} />
    </div>
  )
}

// --- Invites ------------------------------------------------------------------------------------

export function InvitesPanel() {
  const client = useQueryClient()
  const invites = useInvites(true)
  const [email, setEmail] = useState('')
  const refresh = () => void client.invalidateQueries({ queryKey: ['admin', 'invites'] })
  const sending = useMutation({
    mutationFn: () =>
      apiAction(
        api.POST('/api/admin/invites', {
          body: { email: email.trim(), redirect_url: window.location.origin },
        }),
      ),
    onSuccess: () => {
      setEmail('')
      refresh()
    },
  })
  const revoking = useMutation({
    mutationFn: (id: string) =>
      apiAction(
        api.DELETE('/api/admin/invites/{invite_id}', { params: { path: { invite_id: id } } }),
      ),
    onSuccess: refresh,
  })
  const rows = [...(invites.data ?? [])].sort((a, b) =>
    (b.created_at ?? '').localeCompare(a.created_at ?? ''),
  )

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Clerk emails an invitation link. Only invited people can sign up. Once they sign in they are
        members; send them <span className="font-mono">docs/FRIENDS_SETUP.md</span>.
      </p>
      <form
        className="flex flex-wrap items-center gap-2"
        aria-label="Invite someone"
        onSubmit={(e) => {
          e.preventDefault()
          if (email.includes('@')) sending.mutate()
        }}
      >
        <label htmlFor="invite-email" className="sr-only">
          Email
        </label>
        <input
          id="invite-email"
          type="email"
          placeholder="friend@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={cn(input, 'w-64 font-sans')}
        />
        <Button size="sm" type="submit" disabled={!email.includes('@') || sending.isPending}>
          {sending.isPending ? 'Sending…' : 'Send invite'}
        </Button>
      </form>
      <ErrorText error={sending.error} />
      {sending.isSuccess && (
        <p role="status" className="text-sm text-positive">
          Invitation sent.
        </p>
      )}
      <QueryStatus {...invites} lines={2} />
      {rows.length > 0 && (
        <ul className="divide-y rounded-md border text-sm" aria-label="Invitations">
          {rows.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-2 px-3 py-2">
              <span className="min-w-0">
                <span className="block truncate">{i.email_address}</span>
                <span className="text-xs text-muted-foreground">
                  {i.created_at ? `sent ${formatDate(i.created_at)}` : ''}
                </span>
              </span>
              <span className="flex items-center gap-2">
                <Badge variant={i.status === 'accepted' ? 'default' : 'outline'}>{i.status}</Badge>
                {i.status === 'pending' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={revoking.isPending}
                    onClick={() => revoking.mutate(i.id)}
                  >
                    Revoke
                  </Button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {invites.isSuccess && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">No invitations yet.</p>
      )}
      <ErrorText error={revoking.error} />
    </div>
  )
}

// --- Users --------------------------------------------------------------------------------------

export function UsersPanel({ me }: { me: string }) {
  const client = useQueryClient()
  const users = useUsers(true)
  const updating = useMutation({
    mutationFn: ({ id, role }: { id: number; role: 'admin' | 'member' }) =>
      apiAction(
        api.PATCH('/api/admin/users/{user_id}', {
          params: { path: { user_id: id } },
          body: { role },
        }),
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['admin'] }),
  })
  return (
    <div className="space-y-2">
      <QueryStatus {...users} lines={2} />
      {users.data && (
        <ul className="divide-y rounded-md border text-sm" aria-label="Users">
          {users.data.map((u) => (
            <li key={u.id} className="flex items-center justify-between gap-2 px-3 py-2">
              <span className="min-w-0">
                <span className="block truncate font-mono text-xs">
                  {u.clerk_id}
                  {u.clerk_id === me && (
                    <span className="font-sans text-muted-foreground"> (you)</span>
                  )}
                </span>
                <span className="text-xs text-muted-foreground">
                  joined {formatDate(u.created_at)}
                </span>
              </span>
              <select
                aria-label={`Role for ${u.clerk_id}`}
                value={u.role}
                disabled={updating.isPending}
                onChange={(e) =>
                  updating.mutate({ id: u.id, role: e.target.value as 'admin' | 'member' })
                }
                className="h-7 rounded-md border bg-card px-1 text-xs"
              >
                <option value="member">member</option>
                <option value="admin">admin</option>
              </select>
            </li>
          ))}
        </ul>
      )}
      <ErrorText error={updating.error} />
    </div>
  )
}

// --- Usage --------------------------------------------------------------------------------------

export function UsagePanel() {
  const usage = useUsage(true)
  const u = usage.data
  if (!u) return <QueryStatus {...usage} lines={4} />
  const share = u.cap_usd > 0 ? Math.min(1, u.spend_usd / u.cap_usd) : 0
  return (
    <div className="space-y-4 text-sm">
      <div className="space-y-1">
        <p>
          Server-key spend in {u.month}:{' '}
          <span className="font-mono font-semibold" data-testid="spend">
            {usd(u.spend_usd)}
          </span>{' '}
          of the <span className="font-mono">{usd(u.cap_usd)}</span> monthly cap
        </p>
        <div
          className="h-2 w-full max-w-md overflow-hidden rounded-full bg-muted"
          role="meter"
          aria-label="Share of the monthly cap used"
          aria-valuemin={0}
          aria-valuemax={u.cap_usd}
          aria-valuenow={u.spend_usd}
        >
          <div
            className={cn('h-full', share >= 0.8 ? 'bg-negative' : 'bg-positive')}
            style={{ width: `${share * 100}%` }}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Friends&apos; own keys cost you nothing and aren&apos;t counted here.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {(
          [
            ['By job', u.by_source],
            ['By model', u.by_model],
          ] as const
        ).map(([title, lines]) => (
          <div key={title}>
            <h4 className="mb-1 text-xs font-medium text-muted-foreground">{title}</h4>
            {lines.length === 0 ? (
              <p className="text-xs text-muted-foreground">No spend this month.</p>
            ) : (
              <table className="w-full font-mono text-xs tabular-nums">
                <tbody>
                  {lines.map((l) => (
                    <tr key={l.key} className="border-b last:border-0">
                      <td className="py-1">{l.key}</td>
                      <td className="py-1 text-right">{usd(l.cost)}</td>
                      <td className="py-1 text-right text-muted-foreground">
                        {(l.tokens_in + l.tokens_out).toLocaleString('en-US')} tok
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </div>
      <div>
        <h4 className="mb-1 text-xs font-medium text-muted-foreground">
          Agent messages this month
        </h4>
        <table className="w-full font-mono text-xs tabular-nums">
          <tbody>
            {u.users.map((x) => (
              <tr key={x.user_id} className="border-b last:border-0">
                <td className="max-w-60 truncate py-1">{x.clerk_id}</td>
                <td className="py-1 text-muted-foreground">{x.role}</td>
                <td className="py-1 text-right">{x.messages}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>
        <h4 className="mb-1 text-xs font-medium text-muted-foreground">Latest job runs</h4>
        {u.jobs.length === 0 ? (
          <p className="text-xs text-muted-foreground">No runs yet.</p>
        ) : (
          <ul className="space-y-1 text-xs">
            {u.jobs.map((j, i) => (
              <li key={i}>
                <span className="font-mono">{j.job}</span>{' '}
                <span
                  className={
                    j.status === 'success'
                      ? 'text-positive'
                      : j.status === 'failed'
                        ? 'text-negative'
                        : ''
                  }
                >
                  {j.status}
                </span>{' '}
                <span className="text-muted-foreground">{formatDateTime(j.started_at)}</span>
                {j.error && <span className="block truncate text-muted-foreground">{j.error}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
