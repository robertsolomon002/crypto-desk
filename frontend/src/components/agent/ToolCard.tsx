import { CheckCircle2, Database, Loader2, Wrench, XCircle } from 'lucide-react'
import { Link } from 'react-router'

import { describeArgs, previewAsOf, snapshotLink, toolLabel, type ToolCall } from '@/lib/agent'

/** One agent tool call: what ran, on what, and a "View data" link to its exact snapshot. */
export function ToolCard({ call }: { call: ToolCall }) {
  const asOf = call.preview ? previewAsOf(call.preview) : null
  return (
    <div
      className="rounded-md border bg-muted/30 px-2.5 py-1.5 text-xs"
      data-testid="tool-card"
      aria-label={`Tool call: ${toolLabel(call.name)}`}
    >
      <div className="flex items-center gap-1.5">
        {call.ok === null ? (
          <Loader2 className="size-3.5 animate-spin text-muted-foreground" aria-label="Running" />
        ) : call.ok ? (
          <CheckCircle2 className="size-3.5 text-positive" aria-label="Done" />
        ) : (
          <XCircle className="size-3.5 text-negative" aria-label="Failed" />
        )}
        <Wrench className="size-3 text-muted-foreground" aria-hidden />
        <span className="font-medium">{toolLabel(call.name)}</span>
        <span className="font-mono text-muted-foreground">{call.name}</span>
        {call.snapshotId !== null && (
          <Link
            to={snapshotLink(call.snapshotId)}
            className="ml-auto inline-flex shrink-0 items-center gap-1 text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            <Database className="size-3" aria-hidden /> View data
          </Link>
        )}
      </div>
      {(call.args || asOf) && (
        <p className="mt-0.5 text-muted-foreground">
          {call.args ? describeArgs(call.args) : `as of ${asOf}`}
        </p>
      )}
      {call.preview && (
        <p className="mt-0.5 line-clamp-2 font-mono break-all text-muted-foreground/80">
          {call.preview}
        </p>
      )}
    </div>
  )
}
