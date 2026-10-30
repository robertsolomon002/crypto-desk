import { Badge } from '@/components/ui/badge'
import { ViewDataLink } from '@/components/ViewDataLink'
import { formatDate, formatDateTime, safeHttpUrl } from '@/lib/format'
import { useCalendar, type MacroEvent } from '@/lib/queries'

import { Panel, QueryStatus } from './Panel'

const DAYS_AHEAD = 7

function when(event: MacroEvent): string {
  if (!event.time_utc) return `${formatDate(event.date)} (UTC date)`
  return formatDateTime(`${event.date}T${event.time_utc}Z`)
}

export function MacroEventsCard() {
  const { data, isPending, isError, refetch } = useCalendar(DAYS_AHEAD)
  const events = data?.data ?? []
  return (
    <Panel title="Macro this week" action={<ViewDataLink table="calendar_events" />}>
      <QueryStatus isPending={isPending} isError={isError} refetch={refetch} lines={2} />
      {data && events.length === 0 && (
        <p className="text-sm text-muted-foreground">No FOMC or CPI events in the next 7 days.</p>
      )}
      <ul className="space-y-2" data-testid="macro-events">
        {events.map((event) => {
          const href = event.source_url ? safeHttpUrl(event.source_url) : null
          return (
            <li key={`${event.date}-${event.kind}-${event.title}`} className="text-sm">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="uppercase">
                  {event.kind}
                </Badge>
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline"
                  >
                    {event.title}
                  </a>
                ) : (
                  <span>{event.title}</span>
                )}
              </div>
              <div className="text-xs text-muted-foreground tabular-nums">{when(event)}</div>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}
