import type { ReactNode } from 'react'

import { QueryStatus } from '@/components/overview/Panel'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ViewDataLink } from '@/components/ViewDataLink'
import { cn } from '@/lib/utils'

/** A titled chart card (Section 8: title, units, "View data") with its loading and error states. */
export function ChartCard({
  title,
  units,
  data,
  controls,
  query,
  empty,
  className,
  children,
}: {
  title: string
  units?: ReactNode
  data: { table: string; params?: Record<string, string | undefined>; label?: string }[]
  controls?: ReactNode
  query: { isPending: boolean; isError: boolean; refetch: () => unknown }
  /** Shown instead of the chart when loaded but there is nothing to draw. */
  empty?: string | null
  className?: string
  children: ReactNode
}) {
  return (
    <Card size="sm" className={cn('min-w-0 gap-2 px-3 py-2', className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="text-sm font-medium">
          {title}
          {units && <span className="font-normal text-muted-foreground"> · {units}</span>}
        </h2>
        <div className="flex gap-3">
          {data.map((d) => (
            <ViewDataLink key={d.label ?? d.table} {...d} />
          ))}
        </div>
      </div>
      {controls && <div className="flex flex-wrap items-center gap-1.5">{controls}</div>}
      {query.isPending || query.isError ? (
        <div className="py-6">
          <QueryStatus {...query} lines={4} />
        </div>
      ) : empty ? (
        <p className="py-10 text-center text-sm text-muted-foreground">{empty}</p>
      ) : (
        children
      )}
    </Card>
  )
}

/** A one-of-n switch drawn as pressed buttons (shared look with the Charts toolbar). */
export function Segmented<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: readonly (readonly [T, string])[]
  onChange: (value: T) => void
}) {
  return (
    <div className="flex rounded-md border p-0.5" role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <Button
          key={String(v)}
          variant={v === value ? 'secondary' : 'ghost'}
          size="sm"
          aria-pressed={v === value}
          onClick={() => onChange(v)}
          className={cn('h-7 px-2 font-mono text-xs', v === value && 'text-foreground')}
        >
          {text}
        </Button>
      ))}
    </div>
  )
}
