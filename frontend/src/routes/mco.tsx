import { useMemo } from 'react'
import { useSearchParams } from 'react-router'

import { ChartCard, Segmented } from '@/components/charts/ChartCard'
import { EChart } from '@/components/charts/EChart'
import { QueryStatus } from '@/components/overview/Panel'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { useChartColors } from '@/lib/chart-colors'
import { formatDateTime, formatPrice, safeHttpUrl } from '@/lib/format'
import {
  BIAS_TOKEN,
  MCO_CHANNEL,
  SCENARIO_LABEL,
  SCENARIO_TOKEN,
  biasTimelineOption,
  videoCoins,
  type Bias,
} from '@/lib/mco'
import {
  useMcoVideos,
  useMe,
  useOhlcv,
  type McoCoinView,
  type McoScenario,
  type McoVideo,
} from '@/lib/queries'
import { cn } from '@/lib/utils'

// The MCO tab (Stage 6.2): daily summaries of More Crypto Online's public YouTube videos,
// AI-extracted (Decision 6: private, attributed, linked). Every field is untrusted model output
// and is rendered as text only. Scenarios use our colours; his own chart colours are not shown
// because the model reads them unreliably (D49). No wave counts (Decision 7, D49).

const ALL = 'ALL'

function useCoinFilter(): [string, (c: string) => void] {
  const [params, setParams] = useSearchParams()
  const coin = (params.get('mco_coin') ?? ALL).toUpperCase()
  return [
    coin,
    (next) =>
      setParams((prev) => {
        const out = new URLSearchParams(prev)
        if (next === ALL) out.delete('mco_coin')
        else out.set('mco_coin', next)
        return out
      }),
  ]
}

const BIAS_CLASS: Record<Bias, string> = {
  bullish: 'border-positive/50 text-positive',
  bearish: 'border-negative/50 text-negative',
  neutral: 'text-muted-foreground',
}

export function BiasChip({ bias, label }: { bias: Bias; label?: string }) {
  return (
    <Badge variant="outline" className={cn('font-mono', BIAS_CLASS[bias])}>
      {label ? `${label} ` : ''}
      {bias}
    </Badge>
  )
}

function Prices({ values }: { values: number[] }) {
  if (values.length === 0) return <span className="text-muted-foreground">none named</span>
  return (
    <span className="font-mono tabular-nums">
      {values.map((v) => `$${formatPrice(v)}`).join(' · ')}
    </span>
  )
}

function ScenarioBlock({ s }: { s: McoScenario }) {
  return (
    <div
      className="space-y-1 border-l-2 pl-2"
      style={{ borderColor: `var(--${SCENARIO_TOKEN[s.name]})` }}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs font-medium">{SCENARIO_LABEL[s.name]}</span>
        <BiasChip bias={s.bias} />
      </div>
      <p className="text-sm">{s.description}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
        <dt className="text-muted-foreground">Targets</dt>
        <dd>
          <Prices values={s.targets} />
        </dd>
        <dt className="text-muted-foreground">Invalidation</dt>
        <dd>
          {s.invalidation != null ? (
            <Prices values={[s.invalidation]} />
          ) : (
            <span className="text-muted-foreground">none named</span>
          )}
        </dd>
        {s.trigger && (
          <>
            <dt className="text-muted-foreground">Trigger</dt>
            <dd>{s.trigger}</dd>
          </>
        )}
        {s.levels.length > 0 && (
          <>
            <dt className="text-muted-foreground">Levels</dt>
            <dd className="space-x-2">
              {s.levels.map((l) => (
                <span key={`${l.price}-${l.label}`} className="inline-block">
                  <span className="font-mono tabular-nums">${formatPrice(l.price)}</span>{' '}
                  <span className="text-muted-foreground">{l.label}</span>
                </span>
              ))}
            </dd>
          </>
        )}
      </dl>
    </div>
  )
}

function CoinBlock({ view }: { view: McoCoinView }) {
  return (
    <section aria-label={`${view.coin} view`} className="space-y-2 rounded-md border p-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-sm font-semibold">{view.coin}</span>
        <BiasChip bias={view.bias} />
        <span className="text-xs text-muted-foreground">
          {view.timeframe} · {view.extraction_confidence} confidence
        </span>
      </div>
      <p className="text-xs text-muted-foreground">{view.wave_position}</p>
      <div className="grid gap-2 md:grid-cols-2">
        {view.scenarios.map((s) => (
          <ScenarioBlock key={s.name} s={s} />
        ))}
      </div>
      {view.key_levels.length > 0 && (
        <p className="text-xs">
          <span className="text-muted-foreground">Other levels: </span>
          {view.key_levels.map((l, i) => (
            <span key={`${l.price}-${l.label}`}>
              {i > 0 && ' · '}
              <span className="font-mono tabular-nums">${formatPrice(l.price)}</span>{' '}
              <span className="text-muted-foreground">{l.label}</span>
            </span>
          ))}
        </p>
      )}
    </section>
  )
}

function VideoCard({ video, coin }: { video: McoVideo; coin: string }) {
  const href = safeHttpUrl(video.url)
  const coins = coin === ALL ? video.coins : video.coins.filter((c) => c.coin === coin)
  return (
    <Card size="sm" className="gap-2 px-3 py-3" aria-label={`Video: ${video.title}`}>
      <div className="flex gap-3">
        <img
          src={`https://i.ytimg.com/vi/${encodeURIComponent(video.video_id)}/mqdefault.jpg`}
          alt=""
          width={160}
          height={90}
          loading="lazy"
          referrerPolicy="no-referrer"
          className="hidden h-[90px] w-40 shrink-0 rounded-md border object-cover sm:block"
        />
        <div className="min-w-0 space-y-1">
          <h2 className="text-sm leading-snug font-medium">
            {href ? (
              <a href={href} target="_blank" rel="noopener noreferrer" className="hover:underline">
                {video.title}
              </a>
            ) : (
              video.title
            )}
          </h2>
          <p className="text-xs text-muted-foreground">
            More Crypto Online · {formatDateTime(video.published_at)}
            {href && (
              <>
                {' · '}
                <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
                  Watch on YouTube
                </a>
              </>
            )}
          </p>
          <div className="flex flex-wrap gap-1">
            {video.coins.map((c) => (
              <BiasChip key={c.coin} bias={c.bias} label={c.coin} />
            ))}
            {video.low_detail && (
              <Badge variant="outline">low detail: title and description only</Badge>
            )}
          </div>
        </div>
      </div>
      {video.summary && <p className="text-sm">{video.summary}</p>}
      {video.checks.length > 0 && (
        <p role="note" className="text-xs text-negative">
          Check: {video.checks.join('; ')}
        </p>
      )}
      <div className="space-y-2">
        {coins.map((c) => (
          <CoinBlock key={c.coin} view={c} />
        ))}
      </div>
    </Card>
  )
}

function BiasTimeline({ coin, videos }: { coin: string; videos: McoVideo[] }) {
  const colors = useChartColors()
  const ohlcv = useOhlcv(coin, '1d')
  const { data: me } = useMe()
  const closes = useMemo(() => {
    const first = videos.at(-1)?.published_at.slice(0, 10)
    const rows = ohlcv.data?.data ?? []
    const start = first ? new Date(Date.parse(`${first}T00:00:00Z`) - 30 * 86_400_000) : null
    const from = start ? start.toISOString().slice(0, 10) : ''
    return rows
      .map((b) => ({ date: b.time.slice(0, 10), close: b.close }))
      .filter((b) => b.date >= from)
  }, [ohlcv.data, videos])
  const marks = videos.filter((v) => v.coins.some((c) => c.coin === coin)).length
  return (
    <ChartCard
      title={`MCO bias over ${coin} price`}
      units="USD, log · one marker per video, coloured by his bias"
      data={me?.role === 'admin' ? [{ table: 'mco_extracts', label: 'View data' }] : []}
      query={ohlcv}
      empty={marks === 0 ? `No summarized videos discuss ${coin} yet.` : null}
    >
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground" aria-hidden>
        {(['bullish', 'bearish', 'neutral'] as const).map((b) => (
          <span key={b} className="flex items-center gap-1">
            <span
              className="inline-block size-2.5 rounded-full"
              style={{ background: colors[BIAS_TOKEN[b]] }}
            />
            {b}
          </span>
        ))}
      </div>
      <EChart
        option={biasTimelineOption(colors, coin, closes, videos)}
        label={`MCO bias markers over the ${coin} daily close`}
        className="h-64"
        testId="mco-timeline"
      />
    </ChartCard>
  )
}

export function McoPage() {
  const [coin, setCoin] = useCoinFilter()
  const all = useMcoVideos(null, 60)
  const videos = all.data?.data ?? []
  const coins = videoCoins(videos)
  const shown = coin === ALL ? videos : videos.filter((v) => v.coins.some((c) => c.coin === coin))
  const timelineCoin = coin === ALL ? (coins[0] ?? 'BTC') : coin

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-base font-semibold">MCO</h1>
        <Segmented
          label="Coin"
          value={coins.includes(coin) || coin === ALL ? coin : ALL}
          options={[[ALL, 'All'], ...coins.map((c) => [c, c] as const)]}
          onChange={setCoin}
        />
      </div>
      <p
        role="note"
        className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground"
      >
        AI-extracted from{' '}
        <a href={MCO_CHANNEL} target="_blank" rel="noopener noreferrer" className="underline">
          More Crypto Online
        </a>
        &apos;s free public YouTube videos. It may be imperfect: always check the video. Private to
        this desk; not financial advice.
      </p>
      {all.isPending || all.isError ? (
        <QueryStatus {...all} lines={6} />
      ) : videos.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No videos summarized yet. The MCO job runs daily at 06:30 UTC.
        </p>
      ) : (
        <>
          <BiasTimeline coin={timelineCoin} videos={videos} />
          <div className="space-y-3" aria-label="MCO videos">
            {shown.map((v) => (
              <VideoCard key={v.video_id} video={v} coin={coin} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
