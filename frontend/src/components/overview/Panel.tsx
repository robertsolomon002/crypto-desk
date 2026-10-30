import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

/** A titled Overview card with its "View data" link in the header. */
export function Panel({
  title,
  action,
  children,
  className,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <Card size="sm" className={className}>
      <CardHeader className="flex items-center justify-between gap-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

/** Loading and error states shared by the Overview cards. */
export function QueryStatus({
  isPending,
  isError,
  refetch,
  lines = 3,
}: {
  isPending: boolean
  isError: boolean
  refetch: () => unknown
  lines?: number
}) {
  if (isError) {
    return (
      <div role="alert" className="flex items-center justify-between gap-2 text-sm">
        <span className="text-muted-foreground">Couldn&apos;t load this.</span>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    )
  }
  if (isPending) {
    return (
      <div className="space-y-2" aria-busy="true" aria-label="Loading">
        {Array.from({ length: lines }, (_, i) => (
          <Skeleton key={i} className="h-4 w-full" />
        ))}
      </div>
    )
  }
  return null
}
