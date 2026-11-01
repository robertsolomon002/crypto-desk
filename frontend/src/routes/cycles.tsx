import { useMemo } from 'react'

import { ChartCard, Segmented } from '@/components/charts/ChartCard'
import { CycleOverlay } from '@/components/charts/CycleOverlay'
import { YoyOverlay } from '@/components/charts/YoyOverlay'
import { useChartColors } from '@/lib/chart-colors'
import { cycleColor } from '@/lib/cycle-options'
import { useSelectedCoin } from '@/lib/coin'
import {
  ANCHOR_NAME,
  groupPaths,
  groupYears,
  roiColumns,
  type AnchorMode,
  type DayN,
  type PathRow,
  type RoiRow,
  type YMode,
  type YoyRow,
} from '@/lib/cycles-data'
import { formatDate, formatMultiple, formatPct, formatPrice } from '@/lib/format'
import { ApiError, useCycleDayN, useCyclePaths, useRoiSinceBottom, useYoy } from '@/lib/queries'
import { useUrlState } from '@/lib/url-state'
import { cn } from '@/lib/utils'

const ANCHORS = ['halving', 'bottom', 'top'] as const
const Y_MODES = ['multiple', 'drawdown'] as const
const VIEWS = ['cycles', 'yoy'] as const

const ANCHOR_OPTIONS = [
  ['halving', 'Halving'],
  ['bottom', 'Bottom'],
  ['top', 'Top'],
] as const
const Y_OPTIONS = [
  ['multiple', '× anchor (log)'],
  ['drawdown', '% from ATH'],
] as const
const VIEW_OPTIONS = [
  ['cycles', 'Cycles'],
  ['yoy', 'Year over year'],
] as const

const analytics = (fn: string, coin: string, extra: Record<string, string> = {}) => ({
  table: 'analytics',
  params: { fn, coin, ...extra },
})

const is404 = (error: unknown) => error instanceof ApiError && error.status === 404

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th className={cn('px-2 py-1 text-right font-medium text-muted-foreground', className)}>
      {children}
    </th>
  )
}
function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn('px-2 py-1 text-right', className)}>{children}</td>
}

function DayNTable({ data, mode }: { data: DayN; mode: AnchorMode }) {
  const colors = useChartColors()
  const ordered = [...data.table].sort((a, b) => a.cycle.localeCompare(b.cycle))
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] font-mono text-xs whitespace-nowrap tabular-nums">
        <caption className="sr-only">
          Every cycle at day {data.day} after the {ANCHOR_NAME[mode]}
        </caption>
        <thead>
          <tr className="border-b">
            <Th className="text-left">Cycle</Th>
            <Th>Anchor</Th>
            <Th>Anchor price</Th>
            <Th>Date at day N</Th>
            <Th>Close</Th>
            <Th>× anchor</Th>
            <Th>From cycle ATH</Th>
            <Th>Max ×</Th>
            <Th>Top on day</Th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((row, i) => {
            const current = row.cycle === data.current_cycle
            return (
              <tr
                key={row.cycle}
                className={cn('border-b last:border-0', current && 'bg-muted/50 font-semibold')}
              >
                <Td className="text-left">
                  <span aria-hidden style={{ color: cycleColor(colors, i, current) }}>
                    ●{' '}
                  </span>
                  {row.cycle}
                  {current && <span className="font-normal text-muted-foreground"> (now)</span>}
                </Td>
                <Td>{row.anchor_date}</Td>
                <Td>{formatPrice(row.anchor_price)}</Td>
                <Td>
                  {row.date}
                  {!row.reached_day_n && (
                    <span className="block font-normal text-muted-foreground">
                      ended on day {row.day}
                    </span>
                  )}
                </Td>
                <Td>{formatPrice(row.close)}</Td>
                <Td>{formatMultiple(row.multiple)}</Td>
                <Td className={row.drawdown < 0 ? 'text-negative' : undefined}>
                  {formatPct(row.drawdown)}
                </Td>
                <Td>{formatMultiple(row.max_multiple)}</Td>
                <Td>{row.top_day ?? '—'}</Td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function RoiTable({ rows, currentDay }: { rows: RoiRow[]; currentDay: number | null }) {
  const columns = roiColumns(rows)
  const ordered = [...rows].sort((a, b) => a.cycle.localeCompare(b.cycle))
  const current = ordered.at(-1)?.cycle
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] font-mono text-xs whitespace-nowrap tabular-nums">
        <caption className="sr-only">Return since each cycle bottom</caption>
        <thead>
          <tr className="border-b">
            <Th className="text-left">Cycle</Th>
            <Th>Bottom</Th>
            <Th>Bottom price</Th>
            {columns.map((c) => (
              <Th key={c.key}>
                Day {c.day}
                {c.day === currentDay && ' (now)'}
              </Th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ordered.map((row) => (
            <tr
              key={row.cycle}
              className={cn(
                'border-b last:border-0',
                row.cycle === current && 'bg-muted/50 font-semibold',
              )}
            >
              <Td className="text-left">{row.cycle}</Td>
              <Td>{row.bottom_date}</Td>
              <Td>{formatPrice(row.bottom_price)}</Td>
              {columns.map((c) => {
                const v = row[c.key]
                return (
                  <Td
                    key={c.key}
                    className={v == null ? 'text-muted-foreground' : v < 0 ? 'text-negative' : ''}
                  >
                    <span title={v == null ? undefined : formatMultiple(1 + v)}>
                      {formatPct(v)}
                    </span>
                  </Td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function CyclesPage() {
  const [coin] = useSelectedCoin()
  const colors = useChartColors()
  const [anchor, setAnchor] = useUrlState<AnchorMode>('anchor', ANCHORS, 'halving')
  const [y, setY] = useUrlState<YMode>('y', Y_MODES, 'multiple')
  const [view, setView] = useUrlState('view', VIEWS, 'cycles')

  const pathsQ = useCyclePaths(coin, anchor, view === 'cycles')
  const dayNQ = useCycleDayN(coin, anchor, view === 'cycles')
  const roiQ = useRoiSinceBottom(coin)
  const yoyQ = useYoy(coin, view === 'yoy')

  const paths = useMemo(
    () => groupPaths((pathsQ.data?.data.result ?? []) as PathRow[]),
    [pathsQ.data],
  )
  const dayN = dayNQ.data?.data.result as DayN | undefined
  const current = dayN?.current_cycle ?? paths.at(-1)?.cycle ?? null
  const years = useMemo(() => groupYears((yoyQ.data?.data.result ?? []) as YoyRow[]), [yoyQ.data])
  const roi = (roiQ.data?.data.result ?? []) as RoiRow[]
  const now = dayN?.table.find((r) => r.cycle === dayN.current_cycle)

  // Cycles exist only for coins with full cycles in `config/cycles.yaml` (BTC and ETH).
  if (is404(pathsQ.error) || is404(roiQ.error)) {
    return (
      <section className="mx-auto my-12 max-w-md space-y-2 text-center">
        <h1 className="text-lg font-semibold">Cycles</h1>
        <p className="text-sm text-muted-foreground">
          Cycle comparisons cover BTC and ETH: {coin} has no complete cycle in the data yet. Pick
          BTC or ETH in the coin selector.
        </p>
      </section>
    )
  }

  return (
    <div className="mx-auto max-w-7xl space-y-3">
      <h1 className="sr-only">Cycles</h1>
      <div className="flex flex-wrap items-center gap-1.5" role="toolbar" aria-label="Cycle view">
        <Segmented label="View" value={view} options={VIEW_OPTIONS} onChange={setView} />
        {view === 'cycles' && (
          <>
            <Segmented
              label="Align by"
              value={anchor}
              options={ANCHOR_OPTIONS}
              onChange={setAnchor}
            />
            <Segmented label="Y axis" value={y} options={Y_OPTIONS} onChange={setY} />
          </>
        )}
      </div>

      {view === 'cycles' ? (
        <>
          <ChartCard
            title={`${coin} cycles aligned by ${ANCHOR_NAME[anchor]}`}
            units={y === 'multiple' ? '× anchor price, log scale' : '% below the cycle ATH close'}
            data={[analytics('cycles_paths', coin, { mode: anchor })]}
            query={pathsQ}
            empty={paths.length ? null : 'No cycles for this selection.'}
          >
            {now && (
              <p className="text-xs text-muted-foreground" data-testid="cycle-now">
                Today is day <span className="font-mono text-foreground">{now.day}</span> after the{' '}
                {formatDate(now.anchor_date)} {ANCHOR_NAME[anchor]}:{' '}
                <span className="font-mono text-foreground">{formatMultiple(now.multiple)}</span>{' '}
                the anchor price,{' '}
                <span className="font-mono text-foreground">{formatPct(now.drawdown)}</span> from
                the cycle ATH.
              </p>
            )}
            <CycleOverlay paths={paths} current={current} y={y} mode={anchor} colors={colors} />
          </ChartCard>
          <ChartCard
            title={`Day ${dayN?.day ?? 'N'} of the current cycle`}
            units={`every cycle on the same day after its ${ANCHOR_NAME[anchor]}`}
            data={[analytics('cycles_day_n', coin, { mode: anchor })]}
            query={dayNQ}
            empty={dayN?.table.length ? null : 'No cycles for this selection.'}
          >
            {dayN && <DayNTable data={dayN} mode={anchor} />}
          </ChartCard>
        </>
      ) : (
        <ChartCard
          title={`${coin} year over year`}
          units="× the year's first close, log scale"
          data={[analytics('yoy', coin)]}
          query={yoyQ}
          empty={years.length ? null : 'No yearly data.'}
        >
          <YoyOverlay years={years} colors={colors} />
        </ChartCard>
      )}

      <ChartCard
        title="Return since the cycle bottom"
        units="% at fixed days after each bottom; hover for the multiple"
        data={[analytics('roi_since_bottom', coin)]}
        query={roiQ}
        empty={roi.length ? null : 'No cycle bottoms yet.'}
      >
        <RoiTable rows={roi} currentDay={roiColumns(roi).at(-1)?.day ?? null} />
      </ChartCard>
    </div>
  )
}
