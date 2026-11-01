import { useMemo, type ReactNode } from 'react'
import { useSearchParams } from 'react-router'

import { ChartCard, Segmented } from '@/components/charts/ChartCard'
import { DualAxisChart } from '@/components/charts/DualAxis'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useChartColors, withAlpha, type ChartColors } from '@/lib/chart-colors'
import { useSelectedCoin } from '@/lib/coin'
import { fngLabel, formatDate, formatPct, formatPrice } from '@/lib/format'
import {
  changeCorrelation,
  FREQ_TEXT,
  MACRO_SPECS,
  NUPL_ZONES,
  nuplZone,
  onchainCoin,
  parseOverlay,
  percentileOf,
  points,
  rollingMean,
  toggleOverlay,
  trimPoints,
  yoyChange,
  type DominanceRow,
  type MacroRow,
  type OnchainRow,
  type Point,
} from '@/lib/onchain-data'
import {
  formatCompact,
  formatFixed,
  formatUsd,
  type Axis,
  type Band,
  type RefLine,
} from '@/lib/onchain-options'
import { ordinal, type Span } from '@/lib/stats-data'
import {
  useDominance,
  useFearGreed,
  useMacro,
  useOhlcv,
  useOnchain,
  type Candle,
} from '@/lib/queries'
import { useUrlState } from '@/lib/url-state'

const SPANS = ['all', '4y', '1y'] as const
const SPAN_OPTIONS = [
  ['all', 'All'],
  ['4y', '4Y'],
  ['1y', '1Y'],
] as const
const M2_VIEWS = ['yoy', 'level'] as const
const M2_OPTIONS = [
  ['yoy', 'YoY change'],
  ['level', 'Level'],
] as const
const MACRO_IDS = Object.keys(MACRO_SPECS)
const NO_BANDS: Band[] = []
const NO_REFS: RefLine[] = []

const fmtRatio = formatFixed(2)
const fmtPctValue = (v: number) => `${formatFixed(2)(v)}%` // FRED rates are already in percent
const fmtM2 = (v: number) => `$${formatFixed(1)(v / 1000)}T` // FRED M2SL is in billions
const fmtShare = (v: number) => formatPct(v, false)
const fmtDominance = (v: number) => `${formatFixed(1)(v)}%`
const fmtEh = (v: number) => `${formatCompact(v)} EH/s`

const analytics = (coin: string) => ({ table: 'analytics', params: { fn: 'onchain', coin } })
const series = (key: string, label?: string) => ({ table: 'series', params: { key }, label })

const closes = (candles: Candle[] | undefined): Point[] =>
  (candles ?? []).map((c) => [c.time.slice(0, 10), c.close])

const last = (pts: Point[]) => {
  for (let i = pts.length - 1; i >= 0; i--) if (pts[i][1] != null) return pts[i]
  return null
}

/** The value one year before the last point (or the nearest earlier one). */
function yearAgo(pts: Point[]): number | null {
  const end = last(pts)
  if (!end) return null
  const target = `${Number(end[0].slice(0, 4)) - 1}${end[0].slice(4)}`
  let found: number | null = null
  for (const [d, v] of pts) {
    if (d > target) break
    if (v != null) found = v
  }
  return found
}

function Explainer({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-muted-foreground">{children}</p>
}

function Readout({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <p className="text-xs text-muted-foreground" data-testid={testId}>
      {children}
    </p>
  )
}

const Num = ({ children }: { children: ReactNode }) => (
  <span className="font-mono text-foreground tabular-nums">{children}</span>
)

/** A panel whose data is not available from the free sources; it says why instead of a chart. */
function Unavailable({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card size="sm" className="min-w-0 gap-2 px-3 py-2" data-testid="panel-unavailable">
      <h2 className="text-sm font-medium">
        {title} <span className="font-normal text-muted-foreground">· not available</span>
      </h2>
      <p className="py-6 text-sm text-muted-foreground">{children}</p>
    </Card>
  )
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="pt-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
      {children}
    </h2>
  )
}

function nuplBands(c: ChartColors): Band[] {
  const tints = [
    withAlpha(c['series-1'], 0.22),
    withAlpha(c['series-1'], 0.1),
    withAlpha(c.grid, 0.0),
    withAlpha(c['series-2'], 0.1),
    withAlpha(c['series-2'], 0.22),
  ]
  return NUPL_ZONES.map((z, i) => ({
    from: Number.isFinite(z.from) ? z.from : undefined,
    to: Number.isFinite(z.to) ? z.to : undefined,
    color: tints[i],
    label: z.label,
  }))
}

// --- On-chain panels ------------------------------------------------------------------------------

function OnchainSection({
  coin,
  span,
  colors,
}: {
  coin: 'BTC' | 'ETH'
  span: Span
  colors: ChartColors
}) {
  const onchainQ = useOnchain(coin)
  const priceQ = useOhlcv(coin, '1d')
  const rows = useMemo(() => (onchainQ.data?.data.result ?? []) as OnchainRow[], [onchainQ.data])

  const mvrv = useMemo(() => points(rows, (r) => r.mvrv), [rows])
  const nupl = useMemo(() => points(rows, (r) => r.nupl), [rows])
  const realized = useMemo(() => points(rows, (r) => r.realized_price), [rows])
  const price = useMemo(() => closes(priceQ.data?.data), [priceQ.data])
  const addresses = useMemo(() => points(rows, (r) => r.active_addresses), [rows])
  const addresses30 = useMemo(() => rollingMean(addresses, 30), [addresses])
  // Coin Metrics gives BTC hash rate in TH/s; 1 EH/s = 1e6 TH/s.
  const hash = useMemo(
    () => points(rows, (r) => (r.hash_rate == null ? null : r.hash_rate / 1e6)),
    [rows],
  )
  const hash30 = useMemo(() => rollingMean(hash, 30), [hash])

  const mvrvAxis = useMemo<Axis>(
    () => ({
      lines: [
        { name: 'MVRV', color: colors['series-1'], width: 1.5, points: trimPoints(mvrv, span) },
      ],
      format: fmtRatio,
      log: true,
    }),
    [mvrv, span, colors],
  )
  const mvrvBands = useMemo<Band[]>(
    () => [
      { to: 1, color: withAlpha(colors['series-3'], 0.18), label: 'Below 1' },
      { from: 3.5, color: withAlpha(colors['series-5'], 0.18), label: 'Above 3.5' },
    ],
    [colors],
  )
  const priceAxis = useMemo<Axis>(
    () => ({
      lines: [
        {
          name: `${coin} price`,
          color: colors.foreground,
          width: 1.5,
          points: trimPoints(price, span),
        },
        {
          name: 'Realized price',
          color: colors['series-2'],
          width: 2,
          points: trimPoints(realized, span),
        },
      ],
      format: formatUsd,
      log: true,
    }),
    [coin, price, realized, span, colors],
  )
  const nuplAxis = useMemo<Axis>(
    () => ({
      lines: [{ name: 'NUPL', color: colors.foreground, points: trimPoints(nupl, span) }],
      format: fmtRatio,
    }),
    [nupl, span, colors],
  )
  const nuplZones = useMemo(() => nuplBands(colors), [colors])
  const addrAxis = useMemo<Axis>(
    () => ({
      lines: [
        {
          name: 'Daily',
          color: withAlpha(colors['series-1'], 0.45),
          width: 1,
          points: trimPoints(addresses, span),
        },
        {
          name: '30-day average',
          color: colors['series-1'],
          width: 2,
          points: trimPoints(addresses30, span),
        },
      ],
      format: formatCompact,
    }),
    [addresses, addresses30, span, colors],
  )
  const hashAxis = useMemo<Axis>(
    () => ({
      lines: [
        {
          name: 'Daily estimate',
          color: withAlpha(colors['series-4'], 0.45),
          width: 1,
          points: trimPoints(hash, span),
        },
        {
          name: '30-day average',
          color: colors['series-4'],
          width: 2,
          points: trimPoints(hash30, span),
        },
      ],
      format: fmtEh,
      log: true,
    }),
    [hash, hash30, span, colors],
  )

  const lastMvrv = last(mvrv)
  const mvrvPct = lastMvrv
    ? percentileOf(
        mvrv.map((p) => p[1] as number),
        lastMvrv[1] as number,
      )
    : null
  const lastNupl = last(nupl)
  const lastRealized = last(realized)
  const priceOnThatDay = lastRealized ? price.find(([d]) => d === lastRealized[0])?.[1] : null
  const lastAddr = last(addresses30)
  const addrYear = yearAgo(addresses30)
  const lastHash = last(hash30)
  const hashYear = yearAgo(hash30)
  const firstDate = mvrv[0]?.[0]
  const empty = (pts: Point[]) => (pts.length ? null : 'No data.')

  return (
    <>
      <div className="grid gap-3 lg:grid-cols-2">
        <ChartCard
          title={`${coin} MVRV`}
          units="market cap ÷ realized cap, log scale"
          data={[analytics(coin), series(`cm:${coin}:CapMVRVCur`, 'Raw series')]}
          query={onchainQ}
          empty={empty(mvrv)}
        >
          {lastMvrv && (
            <Readout testId="mvrv-readout">
              <Num>{fmtRatio(lastMvrv[1] as number)}</Num> on {formatDate(lastMvrv[0])}
              {mvrvPct != null && (
                <>
                  : the <Num>{ordinal(mvrvPct)} percentile</Num> of {coin}&apos;s daily history
                  since {formatDate(firstDate)}
                </>
              )}
              .
            </Readout>
          )}
          <DualAxisChart
            left={mvrvAxis}
            bands={mvrvBands}
            refLines={[{ value: 1 }]}
            colors={colors}
            label={`${coin} MVRV ratio with historical bands`}
            testId="mvrv-chart"
          />
          <Explainer>
            Market value over realized value: what all coins are worth at today&apos;s price against
            the price each one last moved on-chain. Below 1 the average holder is at a loss, which
            has happened near Bitcoin&apos;s cycle bottoms. Bitcoin&apos;s tops from 2011 to 2021
            all came above 3.5; the 2024–25 peak stayed lower, near 2.8. The bands are rules of
            thumb drawn from Bitcoin&apos;s history, not signals.
          </Explainer>
        </ChartCard>

        <ChartCard
          title={`${coin} price vs realized price`}
          units="USD, log scale"
          data={[analytics(coin), { table: 'candles_daily', params: { coin }, label: 'Prices' }]}
          query={onchainQ.isPending || onchainQ.isError ? onchainQ : priceQ}
          empty={empty(realized)}
        >
          {lastRealized && priceOnThatDay != null && (
            <Readout testId="realized-readout">
              On {formatDate(lastRealized[0])} {coin} closed at{' '}
              <Num>${formatPrice(priceOnThatDay)}</Num>,{' '}
              <Num>{formatPct(priceOnThatDay / (lastRealized[1] as number) - 1)}</Num> from its
              realized price of <Num>${formatPrice(lastRealized[1])}</Num>.
            </Readout>
          )}
          <DualAxisChart
            left={priceAxis}
            colors={colors}
            label={`${coin} price and realized price`}
            testId="realized-chart"
          />
          <Explainer>
            Realized price is the average price at which every coin last moved, a rough cost basis
            for the whole network. It is derived from Coin Metrics&apos; free data as market cap ÷
            MVRV ÷ supply. Price below realized price has marked deep bear markets. Price is the
            Coinbase daily close.
          </Explainer>
        </ChartCard>

        <ChartCard
          title={`${coin} NUPL`}
          units="net unrealized profit or loss, share of market cap"
          data={[analytics(coin)]}
          query={onchainQ}
          empty={empty(nupl)}
        >
          {lastNupl && (
            <Readout testId="nupl-readout">
              <Num>{fmtRatio(lastNupl[1] as number)}</Num> on {formatDate(lastNupl[0])}:{' '}
              <Num>{nuplZone(lastNupl[1] as number)}</Num>.
            </Readout>
          )}
          <DualAxisChart
            left={nuplAxis}
            bands={nuplZones}
            refLines={[{ value: 0 }]}
            colors={colors}
            label={`${coin} NUPL with its conventional zones`}
            testId="nupl-chart"
          />
          <Explainer>
            The share of market value that is unrealized profit (1 − 1 ÷ MVRV). Below 0 the network
            as a whole holds at a loss. The zone names are a common convention from Bitcoin cycles.
          </Explainer>
        </ChartCard>

        <ChartCard
          title={`${coin} active addresses`}
          units="unique addresses per day"
          data={[series(`cm:${coin}:AdrActCnt`)]}
          query={onchainQ}
          empty={empty(addresses)}
        >
          {lastAddr && (
            <Readout testId="addresses-readout">
              30-day average <Num>{formatCompact(lastAddr[1] as number)}</Num> on{' '}
              {formatDate(lastAddr[0])}
              {addrYear != null && (
                <>
                  , <Num>{formatPct((lastAddr[1] as number) / addrYear - 1)}</Num> on a year earlier
                </>
              )}
              .
            </Readout>
          )}
          <DualAxisChart
            left={addrAxis}
            colors={colors}
            label={`${coin} daily active addresses and 30-day average`}
            testId="addresses-chart"
          />
          <Explainer>
            Addresses that sent or received coins that day (Coin Metrics AdrActCnt). One person can
            control many addresses, so read the trend, not the level.
          </Explainer>
        </ChartCard>

        {coin === 'BTC' ? (
          <ChartCard
            title="BTC hash rate"
            units="EH/s, log scale"
            data={[series('cm:BTC:HashRate', 'View data (TH/s)')]}
            query={onchainQ}
            empty={empty(hash)}
          >
            {lastHash && (
              <Readout testId="hash-readout">
                30-day average <Num>{fmtEh(lastHash[1] as number)}</Num> on{' '}
                {formatDate(lastHash[0])}
                {hashYear != null && (
                  <>
                    , <Num>{formatPct((lastHash[1] as number) / hashYear - 1)}</Num> on a year
                    earlier
                  </>
                )}
                .
              </Readout>
            )}
            <DualAxisChart
              left={hashAxis}
              colors={colors}
              label="Bitcoin hash rate, daily estimate and 30-day average"
              testId="hash-chart"
            />
            <Explainer>
              The computing power securing Bitcoin, estimated by Coin Metrics from block count and
              difficulty (stored in TH/s; 1 EH/s is a million TH/s). Daily estimates are noisy, so
              the thick line is the 30-day average.
            </Explainer>
          </ChartCard>
        ) : (
          <Unavailable title="ETH hash rate">
            Ethereum moved to proof of stake on 2022-09-15 (the Merge), so it has no hash rate
            since. Coin Metrics&apos; free series stops on 2022-09-14, and the panel is hidden.
          </Unavailable>
        )}
      </div>
    </>
  )
}

// --- Sentiment and dominance ------------------------------------------------------------------------

function SentimentSection({
  span,
  colors,
  btc,
}: {
  span: Span
  colors: ChartColors
  btc: Point[]
}) {
  const fngQ = useFearGreed('2018-01-01')
  const domQ = useDominance()
  const fng = useMemo(() => points(fngQ.data?.data ?? [], (r) => r.value), [fngQ.data])
  const dom = useMemo(() => (domQ.data?.data.rows ?? []) as DominanceRow[], [domQ.data])
  const domBtc = useMemo(() => points(dom, (r) => r.btc), [dom])
  const domEth = useMemo(() => points(dom, (r) => r.eth), [dom])

  const fngTrim = useMemo(() => trimPoints(fng, span), [fng, span])
  const fngAxis = useMemo<Axis>(
    () => ({
      lines: [{ name: 'Fear & Greed', color: colors['series-2'], width: 1, points: fngTrim }],
      format: formatFixed(0),
      min: 0,
      max: 100,
    }),
    [fngTrim, colors],
  )
  const fngBtcAxis = useMemo<Axis>(() => {
    const start = fngTrim[0]?.[0] ?? ''
    return {
      lines: [
        {
          name: 'BTC price',
          color: colors.foreground,
          width: 1.5,
          points: btc.filter(([d]) => d >= start),
        },
      ],
      format: formatUsd,
      log: true,
    }
  }, [btc, fngTrim, colors])
  const fngBands = useMemo<Band[]>(
    () => [
      { from: 0, to: 25, color: withAlpha(colors.negative, 0.14), label: 'Extreme fear' },
      { from: 76, to: 100, color: withAlpha(colors.positive, 0.14), label: 'Extreme greed' },
    ],
    [colors],
  )
  const domAxis = useMemo<Axis>(
    () => ({
      lines: [
        { name: 'BTC dominance', color: colors['series-2'], width: 2, points: domBtc },
        { name: 'ETH dominance', color: colors['series-1'], width: 2, points: domEth },
      ],
      format: fmtDominance,
    }),
    [domBtc, domEth, colors],
  )

  const lastFng = last(fng)
  const fng30 = last(rollingMean(fng, 30))
  const lastDom = last(domBtc)
  const lastEth = last(domEth)

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <ChartCard
        title="Fear & Greed with BTC price"
        units="index 0 to 100 (left), BTC in USD log scale (right)"
        data={[series('fng'), { table: 'candles_daily', params: { coin: 'BTC' }, label: 'Prices' }]}
        query={fngQ}
        empty={fng.length ? null : 'No data.'}
      >
        {lastFng && (
          <Readout testId="fng-readout">
            <Num>{lastFng[1]}</Num> ({fngLabel(lastFng[1] as number)}) on {formatDate(lastFng[0])}
            {fng30 && (
              <>
                ; 30-day average <Num>{formatFixed(0)(fng30[1] as number)}</Num>
              </>
            )}
            .
          </Readout>
        )}
        <DualAxisChart
          left={fngAxis}
          right={fngBtcAxis}
          bands={fngBands}
          colors={colors}
          label="Crypto Fear and Greed index with the Bitcoin price"
          testId="fng-chart"
        />
        <Explainer>
          alternative.me&apos;s daily Crypto Fear &amp; Greed Index, from 0 (extreme fear) to 100
          (extreme greed). The bands use alternative.me&apos;s own classes: 25 and below is extreme
          fear, 76 and above extreme greed.
        </Explainer>
      </ChartCard>

      <ChartCard
        title="BTC dominance"
        units="% of total crypto market cap"
        data={[series('dominance:btc'), series('dominance:eth', 'ETH')]}
        query={domQ}
        empty={domBtc.length ? null : 'No snapshots yet.'}
      >
        {lastDom && (
          <Readout testId="dominance-readout">
            BTC <Num>{fmtDominance(lastDom[1] as number)}</Num>
            {lastEth && (
              <>
                , ETH <Num>{fmtDominance(lastEth[1] as number)}</Num>
              </>
            )}{' '}
            on {formatDate(lastDom[0])}.
          </Readout>
        )}
        <DualAxisChart
          left={domAxis}
          colors={colors}
          label="Bitcoin and Ether dominance, daily snapshots"
          testId="dominance-chart"
        />
        <Explainer>
          Bitcoin&apos;s and Ether&apos;s share of the total crypto market cap, from CoinGecko.
          CoinGecko&apos;s free plan has no dominance history, so the app keeps one snapshot a day
          since {formatDate(domBtc[0]?.[0])} and this chart grows a point each day. The range
          buttons do not apply here.
        </Explainer>
      </ChartCard>
    </div>
  )
}

// --- Macro panels -------------------------------------------------------------------------------------

interface MacroMeta {
  id: string
  label: string
  units: string
  release_lag_days: number
}

function macroFormat(meta: MacroMeta, m2View: (typeof M2_VIEWS)[number]) {
  if (meta.id === 'M2SL') return m2View === 'yoy' ? fmtShare : fmtM2
  return meta.units === 'percent' ? fmtPctValue : fmtRatio
}

function CorrelationReadout({ id, btc, values }: { id: string; btc: Point[]; values: Point[] }) {
  const spec = MACRO_SPECS[id]
  const results = spec.windows.map(([periods, label]) => ({
    label,
    ...changeCorrelation(btc, values, { freq: spec.freq, periods, mode: spec.mode }),
  }))
  return (
    <Readout testId={`corr-${id}`}>
      Correlation with BTC ({FREQ_TEXT[spec.freq]} changes):{' '}
      {results.map((r, i) => (
        <span key={r.label}>
          {i > 0 && ' · '}
          {r.label}{' '}
          <Num>{r.r == null ? '—' : `r = ${r.r >= 0 ? '+' : '−'}${Math.abs(r.r).toFixed(2)}`}</Num>{' '}
          <span className="text-muted-foreground">(n = {r.n})</span>
        </span>
      ))}
    </Readout>
  )
}

function MacroPanel({
  meta,
  rows,
  btc,
  span,
  colors,
  overlay,
  onOverlay,
  query,
  m2View,
  setM2View,
}: {
  meta: MacroMeta
  rows: MacroRow[]
  btc: Point[]
  span: Span
  colors: ChartColors
  overlay: boolean
  onOverlay: () => void
  query: { isPending: boolean; isError: boolean; refetch: () => unknown }
  m2View: (typeof M2_VIEWS)[number]
  setM2View: (v: (typeof M2_VIEWS)[number]) => void
}) {
  const spec = MACRO_SPECS[meta.id]
  const isM2 = meta.id === 'M2SL'
  const values = useMemo(() => points(rows, (r) => r[meta.id]), [rows, meta.id])
  const shown = useMemo(
    () => (isM2 && m2View === 'yoy' ? yoyChange(values) : values),
    [values, isM2, m2View],
  )
  const format = macroFormat(meta, m2View)
  const left = useMemo<Axis>(
    () => ({
      lines: [
        {
          name: isM2 && m2View === 'yoy' ? 'M2 YoY change' : meta.label,
          color: colors['series-1'],
          width: 2,
          points: trimPoints(shown, span),
        },
      ],
      format: macroFormat(meta, m2View),
    }),
    [shown, span, colors, meta, isM2, m2View],
  )
  const right = useMemo<Axis | undefined>(() => {
    if (!overlay) return undefined
    const start = left.lines[0].points[0]?.[0] ?? ''
    return {
      lines: [
        {
          name: 'BTC price',
          color: colors.foreground,
          width: 1,
          points: btc.filter(([d]) => d >= start),
        },
      ],
      format: formatUsd,
      log: true,
    }
  }, [overlay, btc, left, colors])
  const refs = useMemo<RefLine[]>(
    () => (isM2 && m2View === 'yoy' ? [{ value: 0 }] : NO_REFS),
    [isM2, m2View],
  )
  const latest = last(shown)
  const units = isM2
    ? m2View === 'yoy'
      ? '% change on a year earlier'
      : 'USD, seasonally adjusted'
    : meta.units

  return (
    <ChartCard
      title={meta.label}
      units={`${units}${overlay ? ' · BTC price on the right (log)' : ''}`}
      data={[series(`fred:${meta.id}`)]}
      query={query}
      empty={values.length ? null : 'No data.'}
      controls={
        <>
          <Button
            variant={overlay ? 'secondary' : 'outline'}
            size="sm"
            aria-pressed={overlay}
            onClick={onOverlay}
            className="h-7 px-2 text-xs"
          >
            Overlay on BTC
          </Button>
          {isM2 && (
            <Segmented label="M2 view" value={m2View} options={M2_OPTIONS} onChange={setM2View} />
          )}
        </>
      }
    >
      {latest && (
        <Readout>
          <Num>{format(latest[1] as number)}</Num> for {formatDate(latest[0])} (FRED {meta.id}; FRED
          dates each value by its period, and the app treats it as known {meta.release_lag_days}{' '}
          days later).
        </Readout>
      )}
      <CorrelationReadout id={meta.id} btc={btc} values={values} />
      <DualAxisChart
        left={left}
        right={right}
        refLines={refs}
        bands={NO_BANDS}
        colors={colors}
        label={`${meta.label}${overlay ? ' with the Bitcoin price' : ''}`}
        testId={`macro-${meta.id}`}
      />
      <Explainer>
        {spec.explainer} The correlation compares BTC&apos;s {FREQ_TEXT[spec.freq]} log returns with
        this series&apos; {FREQ_TEXT[spec.freq]} {spec.mode === 'log' ? 'log changes' : 'changes'}{' '}
        over the latest windows shown. It describes co-movement, not cause.
      </Explainer>
    </ChartCard>
  )
}

function MacroSection({ span, colors, btc }: { span: Span; colors: ChartColors; btc: Point[] }) {
  const macroQ = useMacro()
  const [params, setParams] = useSearchParams()
  const [m2View, setM2View] = useUrlState('m2', M2_VIEWS, 'yoy')
  const overlay = parseOverlay(params.get('overlay'), MACRO_IDS)
  const rows = useMemo(() => (macroQ.data?.data.rows ?? []) as MacroRow[], [macroQ.data])
  const metas = (macroQ.data?.data.series ?? []).filter((s) => s.id in MACRO_SPECS)

  const setOverlay = (id: string) =>
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev)
        const next = toggleOverlay(parseOverlay(prev.get('overlay'), MACRO_IDS), id, MACRO_IDS)
        if (next.length) out.set('overlay', next.join(','))
        else out.delete('overlay')
        return out
      },
      { replace: true },
    )

  if (macroQ.isPending || macroQ.isError || !metas.length)
    return (
      <ChartCard
        title="Macro"
        data={[{ table: 'series', params: { key: 'fred:DGS10' } }]}
        query={macroQ}
        empty="No FRED series configured."
      >
        {null}
      </ChartCard>
    )
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {metas.map((meta) => (
        <MacroPanel
          key={meta.id}
          meta={meta}
          rows={rows}
          btc={btc}
          span={span}
          colors={colors}
          overlay={overlay.includes(meta.id)}
          onOverlay={() => setOverlay(meta.id)}
          query={macroQ}
          m2View={m2View}
          setM2View={setM2View}
        />
      ))}
    </div>
  )
}

// --- Page ---------------------------------------------------------------------------------------------

export function OnchainPage() {
  const [coin] = useSelectedCoin()
  const oc = onchainCoin(coin)
  const colors = useChartColors()
  const [span, setSpan] = useUrlState<Span>('range', SPANS, 'all')
  const btcQ = useOhlcv('BTC', '1d')
  const btc = useMemo(() => closes(btcQ.data?.data), [btcQ.data])

  return (
    <div className="mx-auto max-w-7xl space-y-3">
      <h1 className="sr-only">On-chain and Macro</h1>
      <div
        className="flex flex-wrap items-center gap-x-3 gap-y-1.5"
        role="toolbar"
        aria-label="Time range"
      >
        <Segmented label="Range" value={span} options={SPAN_OPTIONS} onChange={setSpan} />
        {oc !== coin && (
          <p className="text-xs text-muted-foreground" data-testid="onchain-coin-note">
            Free on-chain data covers BTC and ETH only, so the on-chain panels show BTC.
          </p>
        )}
      </div>

      <SectionTitle>On-chain · {oc} · Coin Metrics community data</SectionTitle>
      <OnchainSection coin={oc} span={span} colors={colors} />

      <SectionTitle>Sentiment and dominance</SectionTitle>
      <SentimentSection span={span} colors={colors} btc={btc} />

      <SectionTitle>Macro · FRED</SectionTitle>
      <MacroSection span={span} colors={colors} btc={btc} />
    </div>
  )
}
