import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Link } from 'react-router'

import { dataLink } from '@/lib/coin'
import { formatDate, formatDateTime } from '@/lib/format'
import type { Freshness, JobStatus } from '@/lib/queries'
import { cn } from '@/lib/utils'

/** The last date of each source and the daily job; stale ones get a warning icon and text. */
export function FreshnessStrip({
  items,
  job,
}: {
  items: Freshness[]
  job: JobStatus | null | undefined
}) {
  const jobFailed = job != null && job.status === 'failed'
  return (
    <section aria-label="Data freshness" data-testid="freshness">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {items.map((item) => (
          <li key={item.source}>
            <Link
              to={dataLink(item.table)}
              title={`View ${item.table} in the Data tab`}
              className={cn(
                'inline-flex items-center gap-1 hover:underline',
                item.stale ? 'text-warning' : 'text-muted-foreground',
              )}
            >
              {item.stale ? (
                <AlertTriangle className="size-3" aria-hidden />
              ) : (
                <CheckCircle2 className="size-3 text-positive" aria-hidden />
              )}
              <span>{item.source}</span>
              <span className="tabular-nums">{formatDate(item.last_date)}</span>
              {item.stale && <span>(stale)</span>}
            </Link>
          </li>
        ))}
        {job && (
          <li
            className={cn(
              'inline-flex items-center gap-1',
              jobFailed ? 'text-warning' : 'text-muted-foreground',
            )}
          >
            {jobFailed ? (
              <AlertTriangle className="size-3" aria-hidden />
            ) : (
              <CheckCircle2 className="size-3 text-positive" aria-hidden />
            )}
            Daily job {job.status} · {formatDateTime(job.ended_at ?? job.started_at)}
          </li>
        )}
      </ul>
    </section>
  )
}
