import { useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router'

import { DeskRunView } from '@/components/agent/DeskRun'
import { Markdown } from '@/components/agent/Markdown'
import { ChartCard, Segmented } from '@/components/charts/ChartCard'
import { EChart } from '@/components/charts/EChart'
import { QueryStatus } from '@/components/overview/Panel'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { ViewDataLink } from '@/components/ViewDataLink'
import { useChartColors } from '@/lib/chart-colors'
import { deskFromState, type DeskRunState } from '@/lib/desk'
import { formatDate, formatDateTime, formatPct, formatPrice } from '@/lib/format'
import {
  ApiError,
  useScorecard,
  useSignalDebate,
  useSignalHistory,
  useSignalWeek,
  useSignalWeeks,
  type BriefView,
  type ScoreStats,
  type SignalOut,
  type SignalSource,
  type SignalWeek,
} from '@/lib/queries'
import {
  METRIC_LABEL,
  SOURCES,
  SOURCE_LABEL,
  SOURCE_NOTE,
  brierText,
  confidencePct,
  cumulativeOption,
  earlyDays,
  metricUnits,
  outcomeText,
  rateText,
  signalCoins,
  signalGrid,
  signalSources,
  stanceLabel,
  type CumulativeMetric,
} from '@/lib/signals'
import { cn } from '@/lib/utils'

// The Signals tab (Stage 7.2, D52): the weekly brief, the week's signals per source and coin,
// the desk's debate behind each desk signal, the scorecard and the history. Briefs, rationales
// and debates are model output, rendered as text (sanitized Markdown for the brief's fallback).

const ALL = 'ALL'

function useParam(name: string, fallback: string): [string, (v: string) => void] {
  const [params, setParams] = useSearchParams()
  return [
    params.get(name) ?? fallback,
    (next) =>
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev)
          if (next === fallback) out.delete(name)
          else out.set(name, next)
          return out
        },
        { replace: true },
      ),
  ]
}

function Section({
  title,
  units,
  data,
  controls,
  children,
}: {
  title: string
  units?: ReactNode
  data?: { table: string; params?: Record<string, string | undefined> }
  controls?: ReactNode
  children: ReactNode
}) {
  return (
    <Card size="sm" className="min-w-0 gap-2 px-3 py-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="text-sm font-medium">
          {title}
          {units && <span className="font-normal text-muted-foreground"> · {units}</span>}
        </h2>
        {data && <ViewDataLink {...data} />}
      </div>
      {controls && <div className="flex flex-wrap items-center gap-1.5">{controls}</div>}
      {children}
    </Card>
  )
}

function StanceChip({ s }: { s: SignalOut }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        'font-mono',
        s.stance === 'lean_long' ? 'border-positive/50 text-positive' : 'text-muted-foreground',
      )}
    >
      {stanceLabel(s.stance)} {confidencePct(s.confidence)}
    </Badge>
  )
}

function Levels({ s }: { s: SignalOut }) {
  const parts: string[] = []
  if (s.entry_low != null && s.entry_high != null)
    parts.push(`entry ${formatPrice(s.entry_low)}–${formatPrice(s.entry_high)}`)
  if (s.invalidation != null) parts.push(`inval ${formatPrice(s.invalidation)}`)
  if (s.target != null) parts.push(`target ${formatPrice(s.target)}`)
  if (parts.length === 0) return null
  return (
    <div className="font-mono text-[11px] text-muted-foreground tabular-nums">
      {parts.join(' · ')}
    </div>
  )
}

function Outcome({ s }: { s: SignalOut }) {
  const o = s.outcome
  return (
    <div
      className={cn(
        'text-[11px]',
        !o && 'text-muted-foreground',
        o?.direction_hit === true && 'text-positive',
        o?.direction_hit === false && 'text-negative',
      )}
    >
      {outcomeText(s)}
    </div>
  )
}

// --- Brief -----------------------------------------------------------------------------------

function BriefBody({ brief }: { brief: BriefView }) {
  if (brief.summary.length === 0) return <Markdown text={brief.content} />
  return (
    <div className="space-y-3">
      <ul className="list-disc space-y-0.5 pl-5 text-sm">
        {brief.summary.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
      <div className="grid gap-2 lg:grid-cols-3">
        {brief.coins.map((c) => (
          <section
            key={c.coin}
            aria-label={`${c.coin} brief`}
            className="space-y-1.5 rounded-md border p-2"
          >
            <h3 className="font-mono text-sm font-semibold">{c.coin}</h3>
            <p className="text-sm">{c.setup}</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              <dt className="text-positive">Bull case</dt>
              <dd>{c.bull_case}</dd>
              <dt className="text-negative">Bear case</dt>
              <dd>{c.bear_case}</dd>
              <dt className="text-muted-foreground">What would change it</dt>
              <dd>{c.what_would_change}</dd>
              <dt className="text-muted-foreground">Levels</dt>
              <dd className="space-x-2">
                {c.levels_to_watch.map((l) => (
                  <span key={`${l.price}-${l.label}`} className="inline-block">
                    <span className="font-mono tabular-nums">${formatPrice(l.price)}</span>{' '}
                    <span className="text-muted-foreground">{l.label}</span>
                  </span>
                ))}
              </dd>
            </dl>
          </section>
        ))}
      </div>
    </div>
  )
}

function Brief({ week }: { week: SignalWeek }) {
  const b = week.brief
  return (
    <Section
      title={`Weekly brief · week of ${formatDate(week.week)}`}
      units={b ? `${b.model} · written ${formatDateTime(b.created_at)}` : undefined}
      data={b ? { table: 'briefs' } : undefined}
    >
      {week.withheld ? (
        <p role="note" className="text-sm text-muted-foreground">
          {week.withheld}
        </p>
      ) : b ? (
        <BriefBody brief={b} />
      ) : (
        <p className="text-sm text-muted-foreground">No brief for this week.</p>
      )}
    </Section>
  )
}

// --- This week's signals ---------------------------------------------------------------------

function SignalsTable({ week }: { week: SignalWeek }) {
  const coins = signalCoins(week.signals)
  const sources = signalSources(week.signals)
  const grid = signalGrid(week.signals)
  const resolved = week.signals.some((s) => s.outcome)
  return (
    <Section
      title="Signals"
      units={
        resolved
          ? `week of ${formatDate(week.week)}, resolved`
          : `week of ${formatDate(week.week)} · scored from ${formatDate(week.resolves_on)}`
      }
      data={{ table: 'signals' }}
    >
      <div className="overflow-x-auto">
        <table
          className="w-full min-w-[640px] text-left text-sm"
          aria-label="Signals by coin and source"
        >
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              <th className="py-1 pr-3 font-medium">Coin</th>
              {sources.map((src) => (
                <th key={src} className="py-1 pr-3 font-medium" title={SOURCE_NOTE[src]}>
                  {SOURCE_LABEL[src]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {coins.map((coin) => (
              <tr key={coin} className="border-b align-top last:border-0">
                <th scope="row" className="py-1.5 pr-3 font-mono font-semibold">
                  {coin}
                </th>
                {sources.map((src) => {
                  const s = grid.get(coin)?.get(src)
                  return (
                    <td key={src} className="space-y-0.5 py-1.5 pr-3">
                      {s ? (
                        <>
                          <StanceChip s={s} />
                          <Levels s={s} />
                          <Outcome s={s} />
                        </>
                      ) : (
                        <span className="text-xs text-muted-foreground">none</span>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Confidence is the chance the stance is right; flat means no long, never a short. Each week
        runs Monday to Sunday (UTC) from the Sunday close.
      </p>
    </Section>
  )
}

// --- Desk debates ----------------------------------------------------------------------------

function Debate({ s }: { s: SignalOut }) {
  const [open, setOpen] = useState(false)
  const q = useSignalDebate(s.id, open)
  return (
    <details
      className="rounded-md border px-2 py-1.5"
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer text-sm">
        <span className="font-mono font-semibold">{s.coin}</span>{' '}
        <span className="text-muted-foreground">
          desk debate · {stanceLabel(s.stance)} {confidencePct(s.confidence)}
        </span>
      </summary>
      {s.rationale && <p className="mt-1.5 text-sm">{s.rationale}</p>}
      {open && (
        <div className="mt-2">
          {q.isPending || q.isError ? (
            <QueryStatus {...q} lines={6} />
          ) : (
            <DeskRunView
              title={`Weekly desk · ${s.coin} · week of ${formatDate(s.week)}`}
              view={{ ...deskFromState(q.data.data as DeskRunState, 0), snapshotId: null }}
            />
          )}
        </div>
      )}
    </details>
  )
}

function Debates({ week }: { week: SignalWeek }) {
  const desk = week.signals.filter((s) => s.source === 'desk')
  if (desk.length === 0 || week.withheld) return null
  return (
    <Section title="Desk debates" units="analysts, bull and bear, the head's call">
      <div className="space-y-1.5">
        {desk.map((s) =>
          s.has_debate ? (
            <Debate key={s.id} s={s} />
          ) : (
            <p key={s.id} className="text-xs text-muted-foreground">
              {s.coin}: no saved run for this signal.
            </p>
          ),
        )}
      </div>
    </Section>
  )
}

// --- Scorecard -------------------------------------------------------------------------------

function StatsRow({
  label,
  note,
  st,
  weeks,
}: {
  label: string
  note?: string
  st: ScoreStats
  weeks: number
}) {
  const early = earlyDays(st, weeks)
  return (
    <tr className="border-b align-top last:border-0">
      <th scope="row" className="py-1.5 pr-3 font-medium" title={note}>
        {label}
        {early && (
          <Badge
            variant="outline"
            className="ml-1.5 align-middle text-[10px] text-muted-foreground"
          >
            {early}
          </Badge>
        )}
      </th>
      <td className="py-1.5 pr-3 font-mono tabular-nums">{st.signals}</td>
      <td className="py-1.5 pr-3 font-mono tabular-nums">
        {rateText(st.hit_rate, st.hits, st.signals)}
      </td>
      <td className="py-1.5 pr-3 font-mono tabular-nums">{brierText(st.brier)}</td>
      <td className="py-1.5 pr-3 font-mono tabular-nums">
        {rateText(st.target_first_rate, st.target_first, st.with_levels)}
      </td>
      <td className="py-1.5 pr-3 font-mono tabular-nums">{st.long_weeks}</td>
      <td
        className={cn(
          'py-1.5 pr-3 font-mono tabular-nums',
          st.paper_return > 0 && 'text-positive',
          st.paper_return < 0 && 'text-negative',
        )}
      >
        {formatPct(st.paper_return)}
      </td>
    </tr>
  )
}

function ScorecardSection() {
  const q = useScorecard()
  const colors = useChartColors()
  const [coin, setCoin] = useParam('score_coin', ALL)
  const [metric, setMetric] = useParam('score_metric', 'paper_return')
  const card = q.data?.data
  const coins = useMemo(
    () => [...new Set((card?.sources ?? []).flatMap((s) => s.coins.map((c) => c.coin)))].sort(),
    [card],
  )
  const m = (Object.keys(METRIC_LABEL) as CumulativeMetric[]).includes(metric as CumulativeMetric)
    ? (metric as CumulativeMetric)
    : 'paper_return'
  const weeks = card?.weeks.length ?? 0
  const rows =
    card?.sources.flatMap((s) => {
      const st = coin === ALL ? s.stats : s.coins.find((c) => c.coin === coin)?.stats
      return st ? [{ source: s.source, st }] : []
    }) ?? []
  return (
    <>
      <Section
        title="Scorecard"
        units={
          card
            ? `signal v${card.version} · ${weeks} resolved week${weeks === 1 ? '' : 's'}`
            : undefined
        }
        data={{ table: 'signal_outcomes' }}
        controls={
          coins.length > 0 && (
            <Segmented
              label="Scorecard coin"
              value={coins.includes(coin) ? coin : ALL}
              options={[[ALL, 'All'], ...coins.map((c) => [c, c] as const)]}
              onChange={setCoin}
            />
          )
        }
      >
        {q.isPending || q.isError ? (
          <QueryStatus {...q} lines={4} />
        ) : rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Nothing scored yet. A week is scored once its seven daily candles have closed.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table
                className="w-full min-w-[640px] text-left text-sm"
                aria-label="Scorecard by source"
              >
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th className="py-1 pr-3 font-medium">Source</th>
                    <th className="py-1 pr-3 font-medium">Signals</th>
                    <th className="py-1 pr-3 font-medium">Hit rate</th>
                    <th
                      className="py-1 pr-3 font-medium"
                      title="Lower is better; the coin flip scores 0.25"
                    >
                      Brier
                    </th>
                    <th className="py-1 pr-3 font-medium" title="Of signals with both levels">
                      Target first
                    </th>
                    <th className="py-1 pr-3 font-medium">Long weeks</th>
                    <th className="py-1 pr-3 font-medium">Paper P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ source, st }) => (
                    <StatsRow
                      key={source}
                      label={SOURCE_LABEL[source]}
                      note={SOURCE_NOTE[source]}
                      st={st}
                      weeks={card?.early_weeks ?? 12}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Hit: a long week closed higher, or a flat week didn&apos;t. Target first: the target
              was touched before the invalidation; a day touching both counts as invalidation. Paper
              P&amp;L: long weeks only, bought at the Sunday close, sold at the level hit first or
              the next Sunday close, {formatPct(card?.paper_cost_per_side ?? 0.002, false)} cost per
              side; flat weeks earn 0. Hypothetical, not a track record. Under{' '}
              {card?.early_weeks ?? 12} weeks the numbers say little.
            </p>
          </>
        )}
      </Section>
      {card && card.sources.length > 0 && (
        <ChartCard
          title={`${METRIC_LABEL[m]} by source`}
          units={metricUnits(m)}
          data={[{ table: 'signal_outcomes' }]}
          query={q}
          controls={
            <Segmented
              label="Metric"
              value={m}
              options={(Object.keys(METRIC_LABEL) as CumulativeMetric[]).map(
                (k) => [k, METRIC_LABEL[k]] as const,
              )}
              onChange={setMetric}
            />
          }
        >
          <EChart
            option={cumulativeOption(colors, card.sources, m)}
            label={`${METRIC_LABEL[m]} by source, cumulative by week`}
            className="h-64"
            testId="signals-cumulative"
          />
        </ChartCard>
      )}
    </>
  )
}

// --- History ---------------------------------------------------------------------------------

function History() {
  const [coin, setCoin] = useParam('hist_coin', ALL)
  const [source, setSource] = useParam('hist_source', ALL)
  const src = (SOURCES as string[]).includes(source) ? (source as SignalSource) : null
  const q = useSignalHistory(coin === ALL ? null : coin, src)
  const weeks = useSignalWeeks()
  const rows = q.data?.data ?? []
  const coins = useMemo(() => signalCoins(q.data?.data ?? []), [q.data])
  return (
    <Section
      title="History"
      units="every signal, newest week first"
      data={{ table: 'signals', params: { coin: coin === ALL ? undefined : coin } }}
      controls={
        <>
          <Segmented
            label="History source"
            value={src ?? ALL}
            options={[[ALL, 'All'], ...SOURCES.map((s) => [s, SOURCE_LABEL[s]] as const)]}
            onChange={setSource}
          />
          {(coins.length > 1 || coin !== ALL) && (
            <Segmented
              label="History coin"
              value={coin}
              options={[
                [ALL, 'All'],
                ...[...new Set([...coins, ...(coin === ALL ? [] : [coin])])].map(
                  (c) => [c, c] as const,
                ),
              ]}
              onChange={setCoin}
            />
          )}
        </>
      }
    >
      {q.isPending || q.isError ? (
        <QueryStatus {...q} lines={4} />
      ) : rows.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted-foreground">No signals match.</p>
      ) : (
        <div className="max-h-96 overflow-auto">
          <table className="w-full min-w-[640px] text-left text-sm" aria-label="Signal history">
            <thead className="sticky top-0 bg-card">
              <tr className="border-b text-xs text-muted-foreground">
                <th className="py-1 pr-3 font-medium">Week</th>
                <th className="py-1 pr-3 font-medium">Coin</th>
                <th className="py-1 pr-3 font-medium">Source</th>
                <th className="py-1 pr-3 font-medium">Signal</th>
                <th className="py-1 pr-3 font-medium">Outcome</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className="border-b align-top last:border-0">
                  <td className="py-1 pr-3 font-mono text-xs tabular-nums">{s.week}</td>
                  <td className="py-1 pr-3 font-mono">{s.coin}</td>
                  <td className="py-1 pr-3 text-xs">{SOURCE_LABEL[s.source]}</td>
                  <td className="py-1 pr-3">
                    <StanceChip s={s} />
                    <Levels s={s} />
                  </td>
                  <td className="py-1 pr-3">
                    <Outcome s={s} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {weeks.data && (
        <p className="text-[11px] text-muted-foreground">
          {weeks.data.data.weeks.length} week{weeks.data.data.weeks.length === 1 ? '' : 's'} of
          signal v{weeks.data.data.version}. Rows are append-only and hash-chained: history is never
          edited.
        </p>
      )}
    </Section>
  )
}

// --- Page ------------------------------------------------------------------------------------

function WeekPicker({ value, onChange }: { value: string | null; onChange: (w: string) => void }) {
  const weeks = useSignalWeeks()
  const list = weeks.data?.data.weeks ?? []
  if (list.length < 2) return null
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
      Week
      <select
        className="h-7 rounded-md border bg-background px-1.5 font-mono text-xs text-foreground"
        value={value ?? list[0].week}
        onChange={(e) => onChange(e.target.value)}
      >
        {list.map((w) => (
          <option key={w.week} value={w.week}>
            {w.week}
            {w.resolved > 0 ? ' (scored)' : ''}
          </option>
        ))}
      </select>
    </label>
  )
}

export function SignalsPage() {
  const [weekParam, setWeek] = useParam('week', '')
  const week = /^\d{4}-\d{2}-\d{2}$/.test(weekParam) ? weekParam : null
  const q = useSignalWeek(week)
  const none = q.error instanceof ApiError && q.error.status === 404 && week === null
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-base font-semibold">Signals</h1>
        <WeekPicker value={week} onChange={setWeek} />
      </div>
      <p
        role="note"
        className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground"
      >
        One-week views per coin from the multi-agent desk, compared with a coin flip, a trend rule
        and MCO&apos;s AI-extracted bias. Model output can be wrong. Not financial advice: no
        trading, and paper P&amp;L is hypothetical.
      </p>
      {none ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No signals yet. The weekly job runs every Monday at 00:15 UTC (Sunday evening in Toronto).
        </p>
      ) : q.isPending || q.isError ? (
        <QueryStatus {...q} lines={6} />
      ) : (
        <>
          <Brief week={q.data.data} />
          <SignalsTable week={q.data.data} />
          <Debates week={q.data.data} />
        </>
      )}
      <ScorecardSection />
      {!none && <History />}
    </div>
  )
}
