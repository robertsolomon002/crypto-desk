import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { QueryStatus } from '@/components/overview/Panel'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getHealth } from '@/lib/api'
import { formatAgo, formatDate, safeHttpUrl } from '@/lib/format'
import { useMe, useOpsHealth, type HealthReport } from '@/lib/queries'
import { cn } from '@/lib/utils'

// `/health`: the backend's liveness for everyone (works without signing in), and for admins
// the ops view of Stage 8.1 (D53): jobs, data freshness, server-key spend, errors and usage.

const usd = (v: number) =>
  `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const mb = (bytes: number) => `${(bytes / 1024 ** 2).toFixed(1)} MB`
const cell = 'py-1 pr-3 align-top'

function BackendStatus() {
  const { data, isPending, isError } = useQuery({ queryKey: ['health'], queryFn: getHealth })
  return (
    <Card size="sm" className="gap-2 px-4 py-3">
      <CardHeader className="px-0">
        <CardTitle>Backend status</CardTitle>
      </CardHeader>
      <CardContent className="px-0 font-mono text-sm tabular-nums">
        {isPending && <p>Waking up the server…</p>}
        {isError && <p className="text-destructive">Backend unreachable</p>}
        {data && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt className="text-muted-foreground">Status</dt>
            <dd data-testid="health-status">{data.status}</dd>
            <dt className="text-muted-foreground">Version</dt>
            <dd>{data.version}</dd>
            <dt className="text-muted-foreground">Server time</dt>
            <dd>{data.time_utc}</dd>
          </dl>
        )}
      </CardContent>
    </Card>
  )
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Card
      size="sm"
      className="min-w-0 gap-2 px-4 py-3"
      role="region"
      aria-labelledby={`${id}-title`}
    >
      <h2 id={`${id}-title`} className="text-sm font-semibold">
        {title}
      </h2>
      {children}
    </Card>
  )
}

function Meter({
  label,
  value,
  max,
  warnAt,
}: {
  label: string
  value: number
  max: number
  warnAt: number
}) {
  const share = max > 0 ? Math.min(1, value / max) : 0
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-muted"
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
    >
      <div
        className={cn('h-full', value >= warnAt ? 'bg-negative' : 'bg-positive')}
        style={{ width: `${share * 100}%` }}
      />
    </div>
  )
}

function statusClass(status: string | null | undefined) {
  return status === 'success' ? 'text-positive' : status === 'failed' ? 'text-negative' : ''
}

function Jobs({ jobs }: { jobs: HealthReport['jobs'] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mono text-xs tabular-nums">
        <thead className="text-left text-muted-foreground">
          <tr>
            <th className={cell}>Job</th>
            <th className={cell}>Last run</th>
            <th className={cell}>Last success</th>
            <th className={cell}>Runs / failed</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.job} className="border-t" data-testid={`job-${j.job}`}>
              <td className={cell}>
                {j.job}
                {j.overdue && (
                  <Badge variant="destructive" className="ml-2">
                    overdue
                  </Badge>
                )}
              </td>
              <td className={cell}>
                <span className={statusClass(j.last_status)}>{j.last_status ?? 'never ran'}</span>
                {j.last_started_at && (
                  <span className="text-muted-foreground"> {formatAgo(j.last_started_at)}</span>
                )}
                {j.last_seconds != null && (
                  <span className="text-muted-foreground"> · {Math.round(j.last_seconds)} s</span>
                )}
                {j.last_error && j.last_status === 'failed' && (
                  <span
                    className="block max-w-80 truncate text-muted-foreground"
                    title={j.last_error}
                  >
                    {j.last_error}
                  </span>
                )}
              </td>
              <td className={cell}>
                {j.last_success_at ? formatAgo(j.last_success_at) : 'never'}
                <span className="text-muted-foreground"> (max {j.max_age_hours} h)</span>
              </td>
              <td className={cell}>
                {j.runs} / <span className={j.failures ? 'text-negative' : ''}>{j.failures}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Freshness({ rows }: { rows: HealthReport['freshness'] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mono text-xs tabular-nums">
        <tbody>
          {rows.map((f) => (
            <tr key={`${f.source}-${f.detail}`} className="border-b last:border-0">
              <td className={cell}>{f.source}</td>
              <td className={cn(cell, 'text-muted-foreground')}>{f.detail}</td>
              <td className={cn(cell, f.stale && 'text-negative')}>
                {f.last_date ? formatDate(f.last_date) : 'none'}
              </td>
              <td className={cn(cell, 'text-right text-muted-foreground')}>
                {f.age_days != null ? `${f.age_days} d` : ''} / {f.max_age_days} d
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Spend({ s }: { s: HealthReport['spend'] }) {
  return (
    <div className="space-y-2 text-sm">
      <p>
        {s.month}:{' '}
        <span className="font-mono font-semibold" data-testid="ops-spend">
          {usd(s.spent_usd)}
        </span>{' '}
        of <span className="font-mono">{usd(s.cap_usd)}</span>
        <span className="text-muted-foreground"> · pace {usd(s.projected_usd)} by month end</span>
      </p>
      <Meter
        label="Share of the monthly cap used"
        value={s.spent_usd}
        max={s.cap_usd}
        warnAt={s.degrade_at_usd}
      />
      {s.exhausted && (
        <p role="alert" className="text-negative">
          The cap is reached: server-key runs are refused until next month.
        </p>
      )}
      <ul className="space-y-0.5 text-xs">
        {s.degradations.map((d) => (
          <li key={d.step} className={d.active ? 'text-negative' : 'text-muted-foreground'}>
            {d.active ? 'On' : 'Off'}: {d.label}
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        Degradations start at {usd(s.degrade_at_usd)}. By job:{' '}
        {s.by_source.length
          ? s.by_source.map((x) => `${x.source} ${usd(x.cost)}`).join(', ')
          : 'no spend yet'}
      </p>
    </div>
  )
}

function Errors({ e }: { e: HealthReport['errors'] }) {
  return (
    <div className="space-y-2 text-sm">
      <p>
        <span className="font-mono font-semibold" data-testid="ops-errors">
          {e.total}
        </span>{' '}
        in the last {e.window_days} days: {e.job_failures} failed job runs, {e.mco_failures} failed
        MCO videos, {e.app.reduce((n, c) => n + c.count, 0)} API or agent errors.
      </p>
      {e.app.length > 0 && (
        <table className="w-full font-mono text-xs tabular-nums">
          <tbody>
            {e.app.map((c) => (
              <tr key={`${c.where}-${c.kind}`} className="border-b last:border-0">
                <td className={cn(cell, 'max-w-60 truncate')}>{c.where}</td>
                <td className={cell}>{c.kind}</td>
                <td className={cn(cell, 'text-right')}>{c.count}</td>
                <td className={cn(cell, 'text-right text-muted-foreground')}>
                  {formatAgo(c.last_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-xs text-muted-foreground">
        Tracebacks are in the Cloud Run logs and Error Reporting (links below).
      </p>
    </div>
  )
}

function Usage({ u }: { u: HealthReport['usage'] }) {
  return (
    <div className="space-y-3 text-sm">
      <div className="space-y-1">
        <p>
          Database <span className="font-mono">{mb(u.database_bytes)}</span> of{' '}
          <span className="font-mono">{mb(u.storage_limit_bytes)}</span> (Neon Free)
        </p>
        <Meter
          label="Share of Neon's storage used"
          value={u.database_bytes}
          max={u.storage_limit_bytes}
          warnAt={0.8 * u.storage_limit_bytes}
        />
        <p className="text-xs text-muted-foreground">
          Largest: {u.tables.map((t) => `${t.table} ${mb(t.bytes)}`).join(', ')}
        </p>
      </div>
      <ul className="space-y-0.5 text-xs">
        {u.links.map((l) => {
          const href = safeHttpUrl(l.url)
          return (
            <li key={l.url}>
              {href ? (
                <a href={href} target="_blank" rel="noreferrer noopener" className="underline">
                  {l.label}
                </a>
              ) : (
                l.label
              )}
            </li>
          )
        })}
      </ul>
      <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
        {u.free_tier.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </div>
  )
}

function OpsHealth() {
  const health = useOpsHealth(true)
  const r = health.data
  if (!r) return <QueryStatus {...health} lines={6} />
  return (
    <div className="space-y-4">
      <div
        role="status"
        data-testid="ops-overall"
        className={cn(
          'rounded-md border px-4 py-2 text-sm',
          r.ok ? 'border-positive/40 text-positive' : 'border-negative/40 text-negative',
        )}
      >
        {r.ok ? (
          'All jobs on time, every source fresh, budget under the cap.'
        ) : (
          <>
            <p className="font-medium">{r.problems.length} to look at:</p>
            <ul className="list-disc pl-5">
              {r.problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </>
        )}
        <p className="mt-1 text-xs text-muted-foreground">
          Checked {formatAgo(r.generated_at)}. Runbooks: docs/OPS.md.
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section id="jobs" title="Jobs">
          <Jobs jobs={r.jobs} />
        </Section>
        <Section id="freshness" title="Data freshness">
          <Freshness rows={r.freshness} />
        </Section>
        <Section id="spend" title="Server-key LLM spend">
          <Spend s={r.spend} />
        </Section>
        <Section id="errors" title="Errors">
          <Errors e={r.errors} />
        </Section>
        <Section id="usage" title="Free-tier usage">
          <Usage u={r.usage} />
        </Section>
      </div>
    </div>
  )
}

export function HealthPage() {
  const { data: me } = useMe()
  const isAdmin = me?.role === 'admin'
  return (
    <div className={cn('mx-auto space-y-4', isAdmin ? 'max-w-7xl' : 'mt-16 max-w-md')}>
      {isAdmin && <h1 className="text-lg font-semibold">Health</h1>}
      <div className={isAdmin ? 'max-w-md' : ''}>
        <BackendStatus />
      </div>
      {isAdmin && <OpsHealth />}
    </div>
  )
}
