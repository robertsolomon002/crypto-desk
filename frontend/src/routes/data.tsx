import { ArrowDown, ArrowUp, ChevronLeft, Download, X } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'

import { Segmented } from '@/components/charts/ChartCard'
import { TimeSeriesChart } from '@/components/charts/TimeSeries'
import { QueryStatus } from '@/components/overview/Panel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { describeArgs, toolLabel, useSnapshot } from '@/lib/agent'
import { useChartColors } from '@/lib/chart-colors'
import {
  ANALYTICS,
  buildFilters,
  cellText,
  coinColumn,
  dateColumn,
  isNumeric,
  RESERVED,
  resultView,
  snapshotView,
  toCsv,
  type ColumnInfo,
  type Row,
} from '@/lib/data-view'
import { formatDate, formatDateTime } from '@/lib/format'
import {
  exportTable,
  useAnalyticsResult,
  useCoins,
  useTablePage,
  useTables,
  type TableInfo,
} from '@/lib/queries'
import { cn } from '@/lib/utils'

const PAGE_SIZES = [50, 100, 500] as const
const PREVIEW_ROWS = 500

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const stamp = () => new Date().toISOString().slice(0, 10).replace(/-/g, '')

/** The view's URL parameters, with setters that keep everything else (the coin included). */
function useViewParams() {
  const [params, setParams] = useSearchParams()
  const set = (changes: Record<string, string | null>, resetPage = true) =>
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev)
        for (const [k, v] of Object.entries(changes)) {
          if (v === null || v === '') out.delete(k)
          else out.set(k, v)
        }
        if (resetPage && !('page' in changes)) out.delete('page')
        return out
      },
      { replace: true },
    )
  return [params, set] as const
}

function freshness(value: string | null | undefined) {
  if (!value) return '—'
  return value.length > 10 ? formatDateTime(value) : formatDate(value)
}

// --- Catalog -------------------------------------------------------------------------------------

function Catalog({ tables, coin }: { tables: TableInfo[]; coin: string }) {
  const [params] = useSearchParams()
  const link = (extra: Record<string, string>) => {
    const out = new URLSearchParams()
    if (params.get('coin')) out.set('coin', params.get('coin') as string)
    for (const [k, v] of Object.entries(extra)) out.set(k, v)
    return `/data?${out.toString()}`
  }
  return (
    <div className="space-y-4">
      <section aria-labelledby="tables-heading" className="space-y-2">
        <h2 id="tables-heading" className="text-sm font-medium">
          Tables
        </h2>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {tables.map((t) => (
            <Link
              key={t.name}
              to={link({ table: t.name })}
              className="rounded-lg border bg-card p-3 text-sm hover:border-foreground/40"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono font-medium">{t.name}</span>
                {t.visibility !== 'member' && (
                  <Badge variant="outline">{t.visibility === 'own' ? 'yours' : 'admin'}</Badge>
                )}
              </div>
              <p className="mt-1 text-muted-foreground">{t.description}</p>
              <p className="mt-2 font-mono text-xs text-muted-foreground tabular-nums">
                {t.rows.toLocaleString('en-US')} rows · updated {freshness(t.last_updated)}
              </p>
            </Link>
          ))}
        </div>
      </section>
      <section aria-labelledby="analytics-heading" className="space-y-2">
        <h2 id="analytics-heading" className="text-sm font-medium">
          Computed analytics <span className="font-normal text-muted-foreground">· for {coin}</span>
        </h2>
        <p className="text-xs text-muted-foreground">
          The numbers behind the Cycles and Stats charts, computed from the candles on request.
        </p>
        <ul className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
          {ANALYTICS.map((a) => (
            <li key={a.fn}>
              <Link
                to={link({ table: 'analytics', fn: a.fn })}
                className="block rounded-md px-2 py-1 text-sm hover:bg-muted"
              >
                <span className="font-mono text-xs">{a.fn}</span>
                <span className="block text-muted-foreground">{a.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

// --- Shared table -------------------------------------------------------------------------------

function DataGrid({
  columns,
  rows,
  sort,
  desc,
  onSort,
  numeric,
}: {
  columns: string[]
  rows: Row[]
  sort: string | null
  desc: boolean
  onSort?: (column: string) => void
  numeric: Set<string>
}) {
  return (
    <div className="overflow-x-auto rounded-md border">
      <table
        className="w-full font-mono text-xs whitespace-nowrap tabular-nums"
        data-testid="data-grid"
      >
        <thead className="bg-muted/50">
          <tr>
            {columns.map((c) => {
              const active = sort === c
              return (
                <th
                  key={c}
                  scope="col"
                  aria-sort={active ? (desc ? 'descending' : 'ascending') : undefined}
                  className={cn(
                    'px-2 py-1.5 font-medium',
                    numeric.has(c) ? 'text-right' : 'text-left',
                  )}
                >
                  {onSort ? (
                    <button
                      type="button"
                      onClick={() => onSort(c)}
                      className="inline-flex items-center gap-1 hover:text-foreground"
                    >
                      {c}
                      {active &&
                        (desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
                    </button>
                  ) : (
                    c
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t">
              {columns.map((c) => {
                const text = cellText(r[c])
                return (
                  <td
                    key={c}
                    title={text.length > 60 ? text : undefined}
                    className={cn(
                      'max-w-80 truncate px-2 py-1',
                      numeric.has(c) && 'text-right',
                      text === '' && 'text-muted-foreground',
                    )}
                  >
                    {text === '' ? '—' : text}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <p className="p-6 text-center text-sm text-muted-foreground">No rows match.</p>
      )}
    </div>
  )
}

function Pager({
  page,
  pageSize,
  total,
  onPage,
  onSize,
}: {
  page: number
  pageSize: number
  total: number
  onPage: (page: number) => void
  onSize: (size: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1
  const last = Math.min(total, page * pageSize)
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
      <span className="tabular-nums" data-testid="pager-status">
        Rows {first.toLocaleString('en-US')}–{last.toLocaleString('en-US')} of{' '}
        {total.toLocaleString('en-US')}
      </span>
      <div className="flex items-center gap-1.5">
        <label className="flex items-center gap-1">
          Per page
          <select
            value={pageSize}
            onChange={(e) => onSize(Number(e.target.value))}
            className="h-7 rounded-md border bg-card px-1 font-mono text-foreground"
          >
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <Button
          variant="outline"
          size="sm"
          className="h-7"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Previous
        </Button>
        <span className="tabular-nums">
          {page} / {pages}
        </span>
        <Button
          variant="outline"
          size="sm"
          className="h-7"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex items-center gap-1 text-xs text-muted-foreground">
      {label}
      {children}
    </label>
  )
}

const inputClass = 'h-7 rounded-md border bg-card px-1.5 font-mono text-xs text-foreground'

function CoinFilter({
  value,
  onChange,
}: {
  value: string | null
  onChange: (coin: string | null) => void
}) {
  const { data } = useCoins()
  return (
    <Field label="Coin">
      <select
        aria-label="Coin filter"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        className={inputClass}
      >
        <option value="">All coins</option>
        {(data?.data ?? []).map((c) => (
          <option key={c.symbol} value={c.symbol}>
            {c.symbol}
          </option>
        ))}
      </select>
    </Field>
  )
}

function PreviewPicker({
  columns,
  value,
  onChange,
}: {
  columns: string[]
  value: string | null
  onChange: (column: string | null) => void
}) {
  if (columns.length === 0) return null
  return (
    <Field label="Chart">
      <select
        aria-label="Chart a column"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        className={inputClass}
      >
        <option value="">off</option>
        {columns.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    </Field>
  )
}

function Preview({ rows, x, y, note }: { rows: Row[]; x: string; y: string; note: string }) {
  const colors = useChartColors()
  const lines = useMemo(
    () => [
      {
        name: y,
        color: colors['series-1'],
        points: rows
          .filter((r) => typeof r[x] === 'string')
          .map(
            (r) =>
              [r[x] as string, typeof r[y] === 'number' ? (r[y] as number) : null] as [
                string,
                number | null,
              ],
          )
          .sort((a, b) => (a[0] < b[0] ? -1 : 1)),
      },
    ],
    [rows, x, y, colors],
  )
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">
        {y} by {x} · {note}
      </p>
      <TimeSeriesChart
        lines={lines}
        colors={colors}
        percent={false}
        label={`${y} over ${x}`}
        testId="data-preview"
      />
    </div>
  )
}

// --- A stored table -----------------------------------------------------------------------------

function TableView({ info }: { info: TableInfo }) {
  const [params, set] = useViewParams()
  const columns = info.columns as ColumnInfo[]
  const coinCol = coinColumn(columns)
  const dateCol = dateColumn(columns)
  const coin =
    coinCol && !params.get('allcoins') ? (params.get('coin')?.toUpperCase() ?? null) : null
  const from = params.get('from')
  const to = params.get('to')
  const extra = [...params.entries()].filter(
    ([k]) => !RESERVED.has(k) && columns.some((c) => c.name === k),
  )
  const filters = buildFilters(columns, { coin, from, to, extra })
  const sort = params.get('sort')
  const desc = params.get('desc') !== '0'
  const page = Math.max(1, Number(params.get('page')) || 1)
  const pageSize = PAGE_SIZES.find((s) => s === Number(params.get('size'))) ?? 100
  const pageQ = useTablePage(info.name, { filters, order: sort, desc, page, pageSize })

  const numericCols = columns.filter(isNumeric).map((c) => c.name)
  const previewCol = numericCols.includes(params.get('preview') ?? '')
    ? params.get('preview')
    : null
  const previewQ = useTablePage(
    info.name,
    { filters, order: dateCol?.name ?? null, desc: true, page: 1, pageSize: PREVIEW_ROWS },
    previewCol !== null && dateCol !== null,
  )
  const [exporting, setExporting] = useState<string | null>(null)

  const onExport = async () => {
    setExporting('Exporting…')
    try {
      download(
        await exportTable(info.name, { filters, order: sort, desc }),
        `${info.name}_${stamp()}.csv`,
      )
      setExporting(null)
    } catch {
      setExporting('Export failed. Try again.')
    }
  }

  const data = pageQ.data?.data
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="font-mono text-sm font-medium">{info.name}</h2>
          <p className="text-xs text-muted-foreground">
            {info.description} · {info.rows.toLocaleString('en-US')} rows · updated{' '}
            {freshness(info.last_updated)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {exporting && (
            <span role="status" className="text-xs text-muted-foreground">
              {exporting}
            </span>
          )}
          <Button variant="outline" size="sm" className="h-7 gap-1" onClick={onExport}>
            <Download className="size-3" aria-hidden /> Export CSV
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Filters">
        {coinCol && (
          <CoinFilter
            value={coin}
            onChange={(c) => set(c ? { coin: c, allcoins: null } : { allcoins: '1' })}
          />
        )}
        {dateCol && (
          <>
            <Field label="From">
              <input
                type="date"
                aria-label="From date"
                value={from ?? ''}
                onChange={(e) => set({ from: e.target.value })}
                className={inputClass}
              />
            </Field>
            <Field label="To">
              <input
                type="date"
                aria-label="To date"
                value={to ?? ''}
                onChange={(e) => set({ to: e.target.value })}
                className={inputClass}
              />
            </Field>
          </>
        )}
        {extra.map(([k, v]) => (
          <Badge key={k} variant="secondary" className="gap-1 font-mono">
            {k} = {v}
            <button
              type="button"
              aria-label={`Remove filter ${k}`}
              onClick={() => set({ [k]: null })}
            >
              <X className="size-3" />
            </button>
          </Badge>
        ))}
        {dateCol && (
          <PreviewPicker
            columns={numericCols}
            value={previewCol}
            onChange={(c) => set({ preview: c }, false)}
          />
        )}
      </div>

      {previewCol && dateCol && (
        <Card size="sm" className="px-3 py-2">
          {previewQ.isPending || previewQ.isError ? (
            <QueryStatus {...previewQ} lines={3} />
          ) : (
            <Preview
              rows={previewQ.data?.data.rows ?? []}
              x={dateCol.name}
              y={previewCol}
              note={`newest ${PREVIEW_ROWS} rows with these filters`}
            />
          )}
        </Card>
      )}

      {pageQ.isPending || pageQ.isError ? (
        <QueryStatus {...pageQ} lines={6} />
      ) : (
        data && (
          <>
            <DataGrid
              columns={data.columns}
              rows={data.rows}
              sort={sort}
              desc={desc}
              numeric={new Set(numericCols)}
              onSort={(c) => set({ sort: c, desc: sort === c && desc ? '0' : null })}
            />
            <Pager
              page={page}
              pageSize={pageSize}
              total={data.total}
              onPage={(p) => set({ page: p > 1 ? String(p) : null }, false)}
              onSize={(s) => set({ size: s === 100 ? null : String(s) })}
            />
          </>
        )
      )}
    </div>
  )
}

// --- A computed analytics result ----------------------------------------------------------------

function AnalyticsView({ fn }: { fn: string }) {
  const [params, set] = useViewParams()
  const def = ANALYTICS.find((a) => a.fn === fn)
  const coin = (params.get('coin') ?? 'BTC').toUpperCase()
  const fnParams: Record<string, string | undefined> = {}
  for (const [k, options] of Object.entries(def?.params ?? {}))
    fnParams[k] = options.includes(params.get(k) ?? '') ? (params.get(k) as string) : options[0]
  const q = useAnalyticsResult(def ? fn : null, coin, fnParams)
  const view = useMemo(() => resultView(q.data?.data.result), [q.data])
  const partName = view.parts.some((p) => p.name === params.get('part'))
    ? params.get('part')
    : (view.parts[0]?.name ?? null)
  const part = view.parts.find((p) => p.name === partName) ?? null

  const [sort, setSort] = useState<{ column: string; desc: boolean } | null>(null)
  const page = Math.max(1, Number(params.get('page')) || 1)
  const pageSize = PAGE_SIZES.find((s) => s === Number(params.get('size'))) ?? 100
  const numeric = useMemo(
    () =>
      new Set(
        (part?.columns ?? []).filter((c) => part?.rows.some((r) => typeof r[c] === 'number')),
      ),
    [part],
  )
  const sorted = useMemo(() => {
    if (!part || !sort) return part?.rows ?? []
    const dir = sort.desc ? -1 : 1
    return [...part.rows].sort((a, b) => {
      const x = a[sort.column]
      const y = b[sort.column]
      if (x == null) return 1
      if (y == null) return -1
      return (x < y ? -1 : x > y ? 1 : 0) * dir
    })
  }, [part, sort])
  const previewCol = numeric.has(params.get('preview') ?? '') ? params.get('preview') : null
  const hasDate = part?.columns.includes('date') ?? false

  if (!def) {
    return <p className="text-sm text-muted-foreground">Unknown analytics result “{fn}”.</p>
  }
  const notAvailable =
    q.error && 'status' in q.error && (q.error as { status: number }).status === 404

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="font-mono text-sm font-medium">
            {fn} <span className="font-sans font-normal text-muted-foreground">· {coin}</span>
          </h2>
          <p className="text-xs text-muted-foreground">
            {def.label} · computed from the candles
            {q.data && ` up to ${formatDate(q.data.as_of)}`}
          </p>
        </div>
        {part && (
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1"
            onClick={() =>
              download(
                new Blob([toCsv(part.columns, sorted)], { type: 'text/csv;charset=utf-8' }),
                `${fn}_${coin}${view.parts.length > 1 ? `_${part.name}` : ''}_${stamp()}.csv`,
              )
            }
          >
            <Download className="size-3" aria-hidden /> Export CSV
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Options">
        <CoinFilter value={coin} onChange={(c) => c && set({ coin: c })} />
        {Object.entries(def.params ?? {}).map(([k, options]) => (
          <Segmented
            key={k}
            label={k}
            value={fnParams[k] as string}
            options={options.map((o) => [o, o] as const)}
            onChange={(v) => set({ [k]: v })}
          />
        ))}
        {view.parts.length > 1 && (
          <Segmented
            label="Part"
            value={partName as string}
            options={view.parts.map((p) => [p.name, p.name] as const)}
            onChange={(v) => set({ part: v })}
          />
        )}
        {hasDate && (
          <PreviewPicker
            columns={[...numeric]}
            value={previewCol}
            onChange={(c) => set({ preview: c }, false)}
          />
        )}
      </div>

      {notAvailable ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          {fn} isn't available for {coin}. Cycle results cover BTC and ETH.
        </p>
      ) : q.isPending || q.isError ? (
        <QueryStatus {...q} lines={6} />
      ) : (
        <>
          {view.values.length > 0 && (
            <dl
              className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs"
              data-testid="result-values"
            >
              {view.values.map(([k, v]) => (
                <div key={k} className="flex gap-1">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd>{cellText(v) || '—'}</dd>
                </div>
              ))}
            </dl>
          )}
          {previewCol && hasDate && part && (
            <Card size="sm" className="px-3 py-2">
              <Preview
                rows={part.rows}
                x="date"
                y={previewCol}
                note={`${part.rows.length.toLocaleString('en-US')} rows`}
              />
            </Card>
          )}
          {part ? (
            <>
              <DataGrid
                columns={part.columns}
                rows={sorted.slice((page - 1) * pageSize, page * pageSize)}
                sort={sort?.column ?? null}
                desc={sort?.desc ?? false}
                numeric={numeric}
                onSort={(c) =>
                  setSort((s) => ({ column: c, desc: s?.column === c ? !s.desc : false }))
                }
              />
              <Pager
                page={page}
                pageSize={pageSize}
                total={sorted.length}
                onPage={(p) => set({ page: p > 1 ? String(p) : null }, false)}
                onSize={(s) => set({ size: s === 100 ? null : String(s) })}
              />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">This result has no rows.</p>
          )}
        </>
      )}
    </div>
  )
}

// --- An agent tool call's snapshot (Stage 5.2) ---------------------------------------------------

function SnapshotView({ id }: { id: number }) {
  const [params, set] = useViewParams()
  const q = useSnapshot(id)
  const result = useMemo(() => (q.data ? snapshotView(q.data.result) : null), [q.data])
  const parts = result?.view.parts ?? []
  const partName = parts.some((p) => p.name === params.get('part'))
    ? params.get('part')
    : (parts[0]?.name ?? null)
  const part = parts.find((p) => p.name === partName) ?? null
  const numeric = useMemo(
    () =>
      new Set(
        (part?.columns ?? []).filter((c) => part?.rows.some((r) => typeof r[c] === 'number')),
      ),
    [part],
  )
  const page = Math.max(1, Number(params.get('page')) || 1)
  const pageSize = PAGE_SIZES.find((s) => s === Number(params.get('size'))) ?? 100
  const previewCol = numeric.has(params.get('preview') ?? '') ? params.get('preview') : null
  const xCol = part?.columns.find((c) => c === 'date' || c === 'time') ?? null

  if (q.isPending || q.isError) {
    const missing = q.error && 'status' in q.error && (q.error as { status: number }).status === 404
    return missing ? (
      <p className="text-sm text-muted-foreground">
        Snapshot #{id} isn't one you can open (it may have been deleted with its conversation).
      </p>
    ) : (
      <QueryStatus {...q} lines={6} />
    )
  }
  const snap = q.data
  const args = Object.keys(snap.args).length ? describeArgs(snap.args) : 'no arguments'
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium">
            {toolLabel(snap.tool)}{' '}
            <span className="font-mono text-muted-foreground">{snap.tool}</span>
          </h2>
          <p className="text-xs text-muted-foreground">
            Agent snapshot #{snap.id} · {args} · data as of {formatDate(result?.asOf)} · called{' '}
            {formatDateTime(snap.created_at)}
          </p>
          {result && result.sources.length > 0 && (
            <p className="text-xs text-muted-foreground">Sources: {result.sources.join('; ')}</p>
          )}
        </div>
        {part && (
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1"
            onClick={() =>
              download(
                new Blob([toCsv(part.columns, part.rows)], { type: 'text/csv;charset=utf-8' }),
                `snapshot_${snap.id}_${snap.tool}${parts.length > 1 ? `_${part.name}` : ''}.csv`,
              )
            }
          >
            <Download className="size-3" aria-hidden /> Export CSV
          </Button>
        )}
      </div>

      {result?.error && (
        <p role="alert" className="text-sm text-negative">
          The tool returned an error: {result.error}
        </p>
      )}

      {(parts.length > 1 || (xCol && numeric.size > 0)) && (
        <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label="Options">
          {parts.length > 1 && (
            <Segmented
              label="Part"
              value={partName as string}
              options={parts.map((p) => [p.name, p.name] as const)}
              onChange={(v) => set({ part: v })}
            />
          )}
          {xCol && (
            <PreviewPicker
              columns={[...numeric]}
              value={previewCol}
              onChange={(c) => set({ preview: c }, false)}
            />
          )}
        </div>
      )}

      {result && result.view.values.length > 0 && (
        <dl
          className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs"
          data-testid="result-values"
        >
          {result.view.values.map(([k, v]) => (
            <div key={k} className="flex gap-1">
              <dt className="text-muted-foreground">{k}</dt>
              <dd>{cellText(v) || '—'}</dd>
            </div>
          ))}
        </dl>
      )}
      {previewCol && xCol && part && (
        <Card size="sm" className="px-3 py-2">
          <Preview
            rows={part.rows}
            x={xCol}
            y={previewCol}
            note={`${part.rows.length.toLocaleString('en-US')} rows the agent saw`}
          />
        </Card>
      )}
      {part ? (
        <>
          <DataGrid
            columns={part.columns}
            rows={part.rows.slice((page - 1) * pageSize, page * pageSize)}
            sort={null}
            desc={false}
            numeric={numeric}
          />
          <Pager
            page={page}
            pageSize={pageSize}
            total={part.rows.length}
            onPage={(p) => set({ page: p > 1 ? String(p) : null }, false)}
            onSize={(s) => set({ size: s === 100 ? null : String(s) })}
          />
        </>
      ) : (
        !result?.error &&
        result?.view.values.length === 0 && (
          <p className="text-sm text-muted-foreground">This result has no rows.</p>
        )
      )}
      <p className="text-xs text-muted-foreground">
        Exactly what the agent received, saved when it made the call.{' '}
        {snap.conversation_id !== null && (
          <Link to={`/agent?c=${snap.conversation_id}`} className="underline">
            Back to the conversation
          </Link>
        )}
      </p>
    </div>
  )
}

// --- Page ---------------------------------------------------------------------------------------

export function DataPage() {
  const [params] = useSearchParams()
  const tablesQ = useTables()
  const table = params.get('table')
  const fn = params.get('fn')
  const snapshot = Number(params.get('snapshot')) || null
  const coin = (params.get('coin') ?? 'BTC').toUpperCase()
  const tables = tablesQ.data?.data ?? []
  const info = tables.find((t) => t.name === table)
  const back = new URLSearchParams()
  if (params.get('coin')) back.set('coin', params.get('coin') as string)

  return (
    <div className="mx-auto max-w-7xl space-y-3">
      <div className="flex items-center gap-2">
        {(table || snapshot) && (
          <Link
            to={`/data${back.size ? `?${back}` : ''}`}
            className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground"
          >
            <ChevronLeft className="size-3" aria-hidden /> All data
          </Link>
        )}
        <h1 className={cn('text-sm font-semibold', (table || snapshot) && 'sr-only')}>Data</h1>
      </div>
      {snapshot ? (
        <SnapshotView key={snapshot} id={snapshot} />
      ) : table === 'analytics' && fn ? (
        <AnalyticsView fn={fn} />
      ) : tablesQ.isPending || tablesQ.isError ? (
        <QueryStatus {...tablesQ} lines={6} />
      ) : table && !info ? (
        <p className="text-sm text-muted-foreground">
          There's no table “{table}” you can open. Pick one from{' '}
          <Link to="/data" className="underline">
            the list
          </Link>
          .
        </p>
      ) : info ? (
        <TableView key={info.name} info={info} />
      ) : (
        <Catalog tables={tables} coin={coin} />
      )}
    </div>
  )
}
