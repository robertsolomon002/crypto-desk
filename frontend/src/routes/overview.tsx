import { CoinCards } from '@/components/overview/CoinCards'
import { FearGreedCard } from '@/components/overview/FearGreedCard'
import { FreshnessStrip } from '@/components/overview/FreshnessStrip'
import { HeadlinesCard } from '@/components/overview/HeadlinesCard'
import { MacroEventsCard } from '@/components/overview/MacroEventsCard'
import { QueryStatus } from '@/components/overview/Panel'
import { useOverview } from '@/lib/queries'

export function OverviewPage() {
  const { data, isPending, isError, refetch } = useOverview()
  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <h1 className="sr-only">Overview</h1>
      {data && <FreshnessStrip items={data.data.freshness} job={data.data.daily_job} />}
      <QueryStatus isPending={isPending} isError={isError} refetch={refetch} lines={4} />
      {data && <CoinCards cards={data.data.coins} />}
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,2fr)]">
        <FearGreedCard />
        <MacroEventsCard />
        <HeadlinesCard />
      </div>
    </div>
  )
}
