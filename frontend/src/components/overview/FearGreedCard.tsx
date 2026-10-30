import { useState } from 'react'

import { ViewDataLink } from '@/components/ViewDataLink'
import { fngLabel, formatDate } from '@/lib/format'
import { useFearGreed, type SeriesPoint } from '@/lib/queries'

import { Panel, QueryStatus } from './Panel'

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10)
}

/** Semicircle gauge: 0 at the left, 100 at the right. */
function Gauge({ value }: { value: number }) {
  const angle = Math.PI * (1 - value / 100)
  const x = 50 + 38 * Math.cos(angle)
  const y = 50 - 38 * Math.sin(angle)
  return (
    <svg viewBox="0 0 100 56" className="w-40" aria-hidden>
      <path
        d="M 8 50 A 42 42 0 0 1 92 50"
        fill="none"
        stroke="var(--grid)"
        strokeWidth="8"
        strokeLinecap="round"
      />
      <path
        d="M 8 50 A 42 42 0 0 1 92 50"
        fill="none"
        stroke="var(--primary)"
        strokeWidth="8"
        strokeLinecap="round"
        pathLength={100}
        strokeDasharray={`${value} 100`}
      />
      <line x1="50" y1="50" x2={x} y2={y} stroke="var(--foreground)" strokeWidth="2" />
      <circle cx="50" cy="50" r="3" fill="var(--foreground)" />
    </svg>
  )
}

function Sparkline({ points }: { points: SeriesPoint[] }) {
  const values = points.map((p) => p.value).filter((v): v is number => v != null)
  if (values.length < 2) return null
  const coords = values
    .map((v, i) => `${(i / (values.length - 1)) * 100},${30 - (v / 100) * 30}`)
    .join(' ')
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="h-8 w-full" aria-hidden>
      <polyline
        points={coords}
        fill="none"
        stroke="var(--series-1)"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

export function FearGreedCard() {
  const [start] = useState(() => isoDaysAgo(30))
  const { data, isPending, isError, refetch } = useFearGreed(start)
  const points = data?.data ?? []
  const last = points.at(-1)
  return (
    <Panel title="Fear & Greed" action={<ViewDataLink table="series" params={{ key: 'fng' }} />}>
      <QueryStatus isPending={isPending} isError={isError} refetch={refetch} />
      {data && !last?.value && <p className="text-sm text-muted-foreground">No data yet.</p>}
      {last?.value != null && (
        <div className="flex flex-col items-center gap-1" data-testid="fng">
          <Gauge value={last.value} />
          <div className="font-mono text-2xl font-semibold tabular-nums">{last.value}</div>
          <div className="text-sm">{fngLabel(last.value)}</div>
          <div className="w-full">
            <Sparkline points={points} />
            <p className="text-center text-xs text-muted-foreground">
              Last 30 days · {formatDate(last.date)} · alternative.me
            </p>
          </div>
        </div>
      )}
    </Panel>
  )
}
