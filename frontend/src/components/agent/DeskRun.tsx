import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Database,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { ToolCard } from '@/components/agent/ToolCard'
import { QueryStatus } from '@/components/overview/Panel'
import { Badge } from '@/components/ui/badge'
import { snapshotLink, useSnapshot } from '@/lib/agent'
import {
  deskFromState,
  findingIds,
  NODE_LABELS,
  stanceLabel,
  type DeskNode,
  type DeskRunState,
  type DeskView,
  type NodeStatus,
  type NodeView,
} from '@/lib/desk'
import { formatDate, formatPrice } from '@/lib/format'
import { cn } from '@/lib/utils'

// One "Ask the desk" run (Stage 5.3): the analysts' reports, the bull and bear debate, and the
// head's signal with the validator's verdict, in graph order. Model text is shown as plain text.

function StatusIcon({ status }: { status: NodeStatus }) {
  switch (status) {
    case 'running':
      return (
        <Loader2 className="size-3.5 animate-spin text-muted-foreground" aria-label="Running" />
      )
    case 'done':
      return <CheckCircle2 className="size-3.5 text-positive" aria-label="Done" />
    case 'unavailable':
      return <AlertTriangle className="size-3.5 text-negative" aria-label="Unavailable" />
    case 'failed':
      return <XCircle className="size-3.5 text-negative" aria-label="Failed" />
    default:
      return <Circle className="size-3.5 text-muted-foreground/50" aria-label="Waiting" />
  }
}

function Cite({ id, known }: { id: string; known: boolean }) {
  return (
    <span
      className={cn(
        'rounded border px-1 font-mono text-[10px] leading-4',
        known ? 'text-muted-foreground' : 'border-negative/50 text-negative line-through',
      )}
      title={known ? `Finding ${id}` : `${id} isn't in any report`}
    >
      {id}
    </span>
  )
}

function NodeCard({
  node,
  view,
  children,
}: {
  node: DeskNode
  view: NodeView
  children?: ReactNode
}) {
  const tokens = view.usage ? view.usage.tokens_in + view.usage.tokens_out : 0
  return (
    <div
      className="min-w-0 space-y-1.5 rounded-lg border bg-card px-3 py-2"
      data-testid={`desk-node-${node}`}
      data-status={view.status}
    >
      <div className="flex items-center gap-1.5 text-xs">
        <StatusIcon status={view.status} />
        <span className="font-medium">{NODE_LABELS[node]}</span>
        {view.runs > 1 && (
          <Badge variant="outline" className="h-4 px-1 text-[10px]">
            retried
          </Badge>
        )}
        {tokens > 0 && (
          <span className="ml-auto font-mono text-[11px] text-muted-foreground tabular-nums">
            {tokens.toLocaleString('en-US')} tok
          </span>
        )}
      </div>
      {view.status === 'waiting' && <p className="text-xs text-muted-foreground">Waiting…</p>}
      {view.status === 'running' && !children && (
        <p className="text-xs text-muted-foreground">Working…</p>
      )}
      {view.status === 'failed' && view.error && (
        <p className="text-xs text-negative">{view.error}</p>
      )}
      {children}
    </div>
  )
}

function ReportBody({ view }: { view: NodeView }) {
  const r = view.report
  return (
    <>
      {view.tools.length > 0 && (
        <div className="space-y-1">
          {view.tools.map((t) => (
            <ToolCard key={t.callId} call={t} />
          ))}
        </div>
      )}
      {r?.status === 'unavailable' && (
        <p className="text-xs text-negative">
          Report unavailable{r.note ? `: ${r.note}` : ''}. The desk went on without it.
        </p>
      )}
      {r?.status === 'done' && (
        <>
          <p className="text-sm">{r.summary}</p>
          <ul className="space-y-0.5 text-xs">
            {r.findings.map((f) => (
              <li key={f.id} className="flex gap-1.5">
                <Cite id={f.id} known />
                <span className="min-w-0">
                  {f.claim}
                  {f.value && <span className="text-muted-foreground"> · {f.value}</span>}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}

function CaseBody({ view, ids }: { view: NodeView; ids: Set<string> }) {
  if (!view.case) return null
  return (
    <ol className="list-decimal space-y-1 pl-4 text-xs">
      {view.case.points.map((p, i) => (
        <li key={i}>
          {p.text}{' '}
          <span className="inline-flex flex-wrap gap-0.5 align-middle">
            {p.cites.map((c) => (
              <Cite key={c} id={c} known={ids.has(c) && !(p.unknown_cites ?? []).includes(c)} />
            ))}
          </span>
        </li>
      ))}
    </ol>
  )
}

function Level({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="font-mono text-sm tabular-nums">{value}</dd>
    </div>
  )
}

function SignalCard({ view, ids }: { view: DeskView; ids: Set<string> }) {
  const head = view.nodes.head
  const s = view.signal
  const v = view.validation
  const finished = v !== null && (v.ok || v.attempts >= 2)
  return (
    <div
      className="space-y-2 rounded-lg border bg-card px-3 py-2.5"
      data-testid="desk-signal"
      aria-label="Desk signal"
    >
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <StatusIcon status={finished ? 'done' : head.status} />
        <span className="font-medium">{NODE_LABELS.head}</span>
        {head.runs > 1 && (
          <Badge variant="outline" className="h-4 px-1 text-[10px]">
            retried
          </Badge>
        )}
        {v && (
          <span
            className={cn(
              'ml-auto inline-flex items-center gap-1',
              v.ok ? 'text-positive' : 'text-negative',
            )}
            data-testid="desk-validation"
          >
            {v.ok ? (
              <ShieldCheck className="size-3.5" aria-hidden />
            ) : (
              <ShieldAlert className="size-3.5" aria-hidden />
            )}
            {v.ok
              ? v.attempts > 1
                ? 'Validator: passed after one retry'
                : 'Validator: passed'
              : finished
                ? 'Validator: rejected'
                : 'Validator: sent back to the head'}
          </span>
        )}
      </div>
      {head.status === 'waiting' && <p className="text-xs text-muted-foreground">Waiting…</p>}
      {head.status === 'failed' && head.error && (
        <p className="text-xs text-negative">{head.error}</p>
      )}
      {s ? (
        <>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span
              className={cn(
                'text-base font-semibold',
                s.stance === 'lean_long' ? 'text-positive' : 'text-foreground',
              )}
            >
              {stanceLabel(s.stance)} {view.coin}
            </span>
            <span className="font-mono text-sm tabular-nums">
              confidence {s.confidence.toFixed(2)}
            </span>
            <span className="text-xs text-muted-foreground">7-day view</span>
          </div>
          {(s.entry_low != null || s.invalidation != null || s.target != null) && (
            <dl className="grid grid-cols-3 gap-2">
              <Level
                label="Entry zone"
                value={
                  s.entry_low != null && s.entry_high != null
                    ? `${formatPrice(s.entry_low)}–${formatPrice(s.entry_high)}`
                    : '—'
                }
              />
              <Level label="Invalidation" value={formatPrice(s.invalidation)} />
              <Level label="Target" value={formatPrice(s.target)} />
            </dl>
          )}
          <p className="text-sm">{s.rationale}</p>
          {s.cites.length > 0 && (
            <p className="flex flex-wrap items-center gap-0.5 text-[11px] text-muted-foreground">
              Rests on:{' '}
              {s.cites.map((c) => (
                <Cite key={c} id={c} known={ids.has(c)} />
              ))}
            </p>
          )}
        </>
      ) : (
        finished && <p className="text-xs text-negative">The head returned no usable signal.</p>
      )}
      {v && !v.ok && v.errors.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-4 text-xs text-negative">
          {v.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Stage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        {title}
      </h3>
      {children}
    </div>
  )
}

export function DeskRunView({ view, title }: { view: DeskView; title?: string }) {
  const ids = findingIds(view)
  const d = view.done
  return (
    <section className="space-y-3" aria-label={`Desk run on ${view.coin}`} data-testid="desk-run">
      <p className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground">
          {title ?? `Ask the desk · ${view.coin}`}
        </span>
        {view.model && <> · {view.model}</>}
        {view.referenceClose != null && (
          <>
            {' '}
            · last close {formatPrice(view.referenceClose)} ({formatDate(view.referenceDate)})
          </>
        )}
        {view.asOf && <> · as of {view.asOf}</>}
      </p>
      <Stage title="Analysts">
        <div className="grid gap-2 md:grid-cols-2">
          {(['technical', 'context'] as const).map((n) => (
            <NodeCard key={n} node={n} view={view.nodes[n]}>
              {(view.nodes[n].report || view.nodes[n].tools.length > 0) && (
                <ReportBody view={view.nodes[n]} />
              )}
            </NodeCard>
          ))}
        </div>
      </Stage>
      <Stage title="Debate (advocacy, not evidence)">
        <div className="grid gap-2 md:grid-cols-2">
          {(['bull_open', 'bear_open', 'bull_rebut', 'bear_rebut'] as const).map((n) => (
            <NodeCard key={n} node={n} view={view.nodes[n]}>
              {view.nodes[n].case && <CaseBody view={view.nodes[n]} ids={ids} />}
            </NodeCard>
          ))}
        </div>
      </Stage>
      <Stage title="Signal">
        <SignalCard view={view} ids={ids} />
      </Stage>
      {view.error && (
        <p role="alert" className="flex items-start gap-1.5 text-sm text-negative">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {view.error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-1.5 text-[11px] text-muted-foreground">
        {d && (
          <span className="font-mono tabular-nums">
            {d.model_calls} model calls · {d.tool_calls} tool calls ·{' '}
            {(d.tokens_in + d.tokens_out).toLocaleString('en-US')} tokens
            {d.cost_usd != null && ` · $${d.cost_usd.toFixed(4)}`}
          </span>
        )}
        {view.snapshotId !== null && (
          <Link
            to={snapshotLink(view.snapshotId)}
            className="inline-flex items-center gap-1 underline underline-offset-2"
          >
            <Database className="size-3" aria-hidden /> View the full run
          </Link>
        )}
        <span>Not financial advice.</span>
      </div>
    </section>
  )
}

/** A desk run from history, loaded from its `desk_run` snapshot. */
export function DeskFromSnapshot({ id }: { id: number }) {
  const q = useSnapshot(id)
  if (q.isPending || q.isError) return <QueryStatus {...q} lines={6} />
  return <DeskRunView view={deskFromState(q.data.result as DeskRunState, id)} />
}
