import { useQuery } from '@tanstack/react-query'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getHealth } from '@/lib/api'

export function HealthPage() {
  const { data, isPending, isError } = useQuery({ queryKey: ['health'], queryFn: getHealth })

  return (
    <Card className="mx-auto mt-16 max-w-md">
      <CardHeader>
        <CardTitle>Backend status</CardTitle>
      </CardHeader>
      <CardContent className="font-mono text-sm tabular-nums">
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
