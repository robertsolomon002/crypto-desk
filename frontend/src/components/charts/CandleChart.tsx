import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  PriceScaleMode,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesType,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { memo, useEffect, useMemo, useRef } from 'react'

import type { Bar, IndicatorLine } from '@/lib/chart-data'
import { withAlpha, type ChartColors } from '@/lib/chart-colors'

// One Lightweight Charts instance per mount. Series are synced by id on every change, so
// toggling an indicator adds or removes one series instead of rebuilding the chart, and data is
// only re-sent when it changes. Pane 0 is price (candles, volume, overlays, levels, pivots);
// RSI and MACD get their own panes below it, which share the time scale and crosshair.
// The TradingView attribution logo stays on (`attributionLogo`, required by the license).

export interface LevelLine {
  label: string
  value: number
}

export interface PivotMark {
  time: number
  kind: 'high' | 'low'
  confirmed: boolean
}

export interface CandleChartProps {
  bars: Bar[]
  mode: 'candles' | 'line'
  lines: IndicatorLine[]
  levels: LevelLine[]
  pivots: PivotMark[]
  showVolume: boolean
  log: boolean
  intraday: boolean
  colors: ChartColors
  /** Changing it re-frames the view on the last `initialBars` bars (new coin, timeframe, ratio). */
  frameKey: string
  initialBars: number
  onHover: (index: number | null) => void
  onRange: (from: number, to: number) => void
}

type SeriesDef = typeof CandlestickSeries | typeof LineSeries | typeof HistogramSeries

interface Spec {
  id: string
  pane: number
  def: SeriesDef
  options: Record<string, unknown>
  data: object[]
  priceScale?: { id: string; top: number; bottom: number }
}

interface Live {
  api: ISeriesApi<SeriesType>
  pane: number
  def: SeriesDef
  data: object[]
  options: string
}

const ts = (t: number) => t as UTCTimestamp

function lineData(bars: Bar[], values: ArrayLike<number>) {
  const out: { time: UTCTimestamp; value: number }[] = []
  for (let i = 0; i < bars.length; i++) {
    if (Number.isFinite(values[i])) out.push({ time: ts(bars[i].time), value: values[i] })
  }
  return out
}

/** Decimals that show about 4 significant digits below 1 (ratios, small coins, MACD) and 2
 * from 1 up, matching `formatPrice`. The default (2) would flatten an ETH/BTC ratio. */
function priceFormat(values: Iterable<number>) {
  let max = 0
  for (const v of values) if (Number.isFinite(v)) max = Math.max(max, Math.abs(v))
  const precision = max >= 1 || max === 0 ? 2 : Math.min(10, 3 - Math.floor(Math.log10(max)))
  return { type: 'price' as const, precision, minMove: 10 ** -precision }
}

function buildSpecs(p: CandleChartProps): Spec[] {
  const { bars, colors: c } = p
  const specs: Spec[] = []
  const pricePf = priceFormat(bars.map((b) => b.close))
  const macdPf = priceFormat(
    p.lines.filter((l) => l.pane === 'macd').flatMap((l) => Array.from(l.values)),
  )
  const formatFor = (pane: IndicatorLine['pane']) =>
    pane === 'price'
      ? pricePf
      : pane === 'macd'
        ? macdPf
        : { type: 'price' as const, precision: 1, minMove: 0.1 }
  const hasRsi = p.lines.some((l) => l.pane === 'rsi')
  const paneOf = { price: 0, rsi: 1, macd: hasRsi ? 2 : 1 } // panes stay contiguous

  if (p.showVolume && p.mode === 'candles') {
    specs.push({
      id: 'volume',
      pane: 0,
      def: HistogramSeries,
      options: {
        priceScaleId: 'volume',
        priceFormat: { type: 'volume' },
        lastValueVisible: false,
        priceLineVisible: false,
      },
      priceScale: { id: 'volume', top: 0.82, bottom: 0 },
      data: bars
        .filter((b) => b.volume !== null && b.open !== null)
        .map((b) => ({
          time: ts(b.time),
          value: b.volume as number,
          color: withAlpha(b.close >= (b.open as number) ? c.positive : c.negative, 0.35),
        })),
    })
  }

  if (p.mode === 'candles') {
    const firstFull = bars.findIndex((b) => b.open !== null && b.high !== null && b.low !== null)
    if (firstFull !== 0) {
      // Close-only backfill (BTC before 2015-07-20, D31) as a line up to the first full candle.
      const upto = firstFull === -1 ? bars.length : firstFull + 1
      specs.push({
        id: 'backfill',
        pane: 0,
        def: LineSeries,
        options: {
          color: c['muted-foreground'],
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          crosshairMarkerVisible: false,
          priceFormat: pricePf,
        },
        data: bars.slice(0, upto).map((b) => ({ time: ts(b.time), value: b.close })),
      })
    }
    specs.push({
      id: 'main-candles',
      pane: 0,
      def: CandlestickSeries,
      options: {
        upColor: c.positive,
        downColor: c.negative,
        borderUpColor: c.positive,
        borderDownColor: c.negative,
        wickUpColor: c.positive,
        wickDownColor: c.negative,
        priceFormat: pricePf,
      },
      data: bars
        .filter((b) => b.open !== null && b.high !== null && b.low !== null)
        .map((b) => ({ time: ts(b.time), open: b.open, high: b.high, low: b.low, close: b.close })),
    })
  } else {
    specs.push({
      id: 'main-line',
      pane: 0,
      def: LineSeries,
      options: { color: c.foreground, lineWidth: 2, priceFormat: pricePf },
      data: bars.map((b) => ({ time: ts(b.time), value: b.close })),
    })
  }

  for (const line of p.lines) {
    const pane = paneOf[line.pane]
    if (line.style === 'histogram') {
      const data = []
      for (let i = 0; i < bars.length; i++) {
        const v = line.values[i]
        if (Number.isFinite(v)) {
          data.push({
            time: ts(bars[i].time),
            value: v,
            color: withAlpha(v >= 0 ? c.positive : c.negative, 0.6),
          })
        }
      }
      specs.push({
        id: line.id,
        pane,
        def: HistogramSeries,
        options: { priceLineVisible: false, lastValueVisible: false, priceFormat: macdPf },
        data,
      })
      continue
    }
    const color =
      line.color === 'muted' || line.color === 'macd-hist' ? c['muted-foreground'] : c[line.color]
    specs.push({
      id: line.id,
      pane,
      def: LineSeries,
      options: {
        color,
        lineWidth: 1,
        lineStyle: line.style === 'dashed' ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
        title: '',
        priceFormat: formatFor(line.pane),
      },
      data: lineData(bars, line.values),
    })
  }
  return specs
}

function CandleChartImpl(props: CandleChartProps) {
  const container = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const live = useRef(new Map<string, Live>())
  const priceLines = useRef<{ series: ISeriesApi<SeriesType>; lines: IPriceLine[] }[]>([])
  const markers = useRef<{
    series: ISeriesApi<SeriesType>
    plugin: ISeriesMarkersPluginApi<Time>
  } | null>(null)
  const timeIndex = useRef(new Map<number, number>())
  const callbacks = useRef({ onHover: props.onHover, onRange: props.onRange })
  const framed = useRef<string | null>(null)

  useEffect(() => {
    callbacks.current = { onHover: props.onHover, onRange: props.onRange }
  })

  // Create once.
  useEffect(() => {
    const el = container.current
    if (!el) return
    const api = createChart(el, {
      autoSize: true,
      crosshair: { mode: CrosshairMode.Normal },
      layout: { attributionLogo: true, fontFamily: 'Geist Variable, sans-serif', fontSize: 11 },
      rightPriceScale: { minimumWidth: 64 },
      timeScale: { rightOffset: 5, minBarSpacing: 0.05 },
    })
    chart.current = api
    const seriesMap = live.current
    api.subscribeCrosshairMove((param) => {
      const idx =
        param.time === undefined ? null : (timeIndex.current.get(param.time as number) ?? null)
      callbacks.current.onHover(idx)
    })
    api.timeScale().subscribeVisibleTimeRangeChange((range) => {
      if (range) callbacks.current.onRange(range.from as number, range.to as number)
    })
    return () => {
      api.remove()
      chart.current = null
      seriesMap.clear()
      priceLines.current = []
      markers.current = null
      framed.current = null
    }
  }, [])

  // Theme and scale options.
  const { colors: c, log, intraday } = props
  useEffect(() => {
    const api = chart.current
    if (!api) return
    api.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: c.card },
        textColor: c['muted-foreground'],
        panes: {
          separatorColor: c.border,
          separatorHoverColor: withAlpha(c['muted-foreground'], 0.3),
        },
      },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border, timeVisible: intraday, secondsVisible: false },
      crosshair: {
        vertLine: { labelBackgroundColor: c.border },
        horzLine: { labelBackgroundColor: c.border },
      },
    })
  }, [c, intraday])

  const specs = useMemo(() => buildSpecs(props), [props])

  // Sync series, panes, levels and markers.
  useEffect(() => {
    const api = chart.current
    if (!api) return
    const map = live.current
    const wanted = new Map(specs.map((s) => [s.id, s]))
    for (const [id, s] of map) {
      const w = wanted.get(id)
      if (!w || w.pane !== s.pane || w.def !== s.def) {
        api.removeSeries(s.api)
        map.delete(id)
      }
    }
    for (const spec of specs) {
      let s = map.get(spec.id)
      const options = JSON.stringify(spec.options)
      if (!s) {
        const seriesApi = api.addSeries(spec.def as typeof LineSeries, spec.options, spec.pane)
        s = {
          api: seriesApi as ISeriesApi<SeriesType>,
          pane: spec.pane,
          def: spec.def,
          data: [],
          options,
        }
        map.set(spec.id, s)
        if (spec.priceScale) {
          api.priceScale(spec.priceScale.id, spec.pane).applyOptions({
            scaleMargins: { top: spec.priceScale.top, bottom: spec.priceScale.bottom },
          })
        }
      } else if (s.options !== options) {
        s.api.applyOptions(spec.options)
        s.options = options
      }
      if (s.data !== spec.data) {
        s.api.setData(spec.data as never)
        s.data = spec.data
      }
    }

    const panes = api.panes()
    panes.forEach((pane, i) => {
      pane.setStretchFactor(i === 0 ? 3 : 1)
      // A new pane copies pane 0's scale options, so RSI and MACD are set back to linear.
      if (i > 0) {
        pane.priceScale('right').applyOptions({
          mode: PriceScaleMode.Normal,
          scaleMargins: { top: 0.1, bottom: 0.1 },
        })
      }
    })
    api.priceScale('right', 0).applyOptions({
      mode: log ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
      scaleMargins: {
        top: 0.08,
        bottom: props.showVolume && props.mode === 'candles' ? 0.2 : 0.08,
      },
    })

    // Price lines: key levels on the main series, 30/70 guides on RSI.
    for (const { series, lines } of priceLines.current) {
      if ([...map.values()].some((s) => s.api === series))
        lines.forEach((l) => series.removePriceLine(l))
    }
    priceLines.current = []
    const main = map.get('main-candles') ?? map.get('main-line')
    if (main) {
      const lines = props.levels.map((l) =>
        main.api.createPriceLine({
          price: l.value,
          color: c['series-2'],
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: l.label,
        }),
      )
      priceLines.current.push({ series: main.api, lines })
    }
    const rsiSeries = map.get('rsi14')
    if (rsiSeries) {
      const guides = [30, 70].map((price) =>
        rsiSeries.api.createPriceLine({
          price,
          color: c['muted-foreground'],
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: false,
          title: '',
        }),
      )
      priceLines.current.push({ series: rsiSeries.api, lines: guides })
    }

    // Pivot markers live on the main series; a new main series needs a new plugin.
    const pivotMarkers = props.pivots.map((p) => ({
      time: ts(p.time),
      position: p.kind === 'high' ? ('aboveBar' as const) : ('belowBar' as const),
      shape: p.kind === 'high' ? ('arrowDown' as const) : ('arrowUp' as const),
      color: p.kind === 'high' ? c.negative : c.positive,
      text: p.confirmed ? '' : '?',
      size: 0.6,
    }))
    if (markers.current && markers.current.series !== main?.api) {
      if ([...map.values()].some((s) => s.api === markers.current?.series))
        markers.current.plugin.detach()
      markers.current = null
    }
    if (main) {
      if (markers.current) markers.current.plugin.setMarkers(pivotMarkers)
      else
        markers.current = { series: main.api, plugin: createSeriesMarkers(main.api, pivotMarkers) }
    }

    timeIndex.current = new Map(props.bars.map((b, i) => [b.time, i]))

    if (framed.current !== props.frameKey && props.bars.length) {
      framed.current = props.frameKey
      const n = props.bars.length
      api
        .timeScale()
        .setVisibleLogicalRange({ from: Math.max(0, n - props.initialBars), to: n + 4 })
    }
  }, [specs, props, c, log])

  return <div ref={container} className="size-full" data-testid="candle-chart" />
}

export const CandleChart = memo(CandleChartImpl)
