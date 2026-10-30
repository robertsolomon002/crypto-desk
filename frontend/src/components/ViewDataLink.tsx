import { Table2 } from 'lucide-react'
import { Link } from 'react-router'

import { dataLink } from '@/lib/coin'

/** Every chart and card links to the exact rows behind it in the Data tab (Section 1). */
export function ViewDataLink({
  table,
  params,
  label = 'View data',
}: {
  table: string
  params?: Record<string, string | undefined>
  label?: string
}) {
  return (
    <Link
      to={dataLink(table, params)}
      className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
    >
      <Table2 className="size-3" aria-hidden />
      {label}
    </Link>
  )
}
