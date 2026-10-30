import { ViewDataLink } from '@/components/ViewDataLink'
import { formatAgo, safeHttpUrl } from '@/lib/format'
import { useNews } from '@/lib/queries'

import { Panel, QueryStatus } from './Panel'

const LIMIT = 8

// Headlines are untrusted (Section 3.6): React renders them as text, never HTML, and only
// http(s) URLs become links.
export function HeadlinesCard() {
  const { data, isPending, isError, refetch } = useNews(LIMIT)
  const items = data?.data ?? []
  return (
    <Panel title="Top headlines" action={<ViewDataLink table="news" />}>
      <QueryStatus isPending={isPending} isError={isError} refetch={refetch} lines={5} />
      {data && items.length === 0 && (
        <p className="text-sm text-muted-foreground">No headlines yet.</p>
      )}
      <ul className="divide-y" data-testid="headlines">
        {items.map((item) => {
          const href = safeHttpUrl(item.url)
          return (
            <li key={item.url} className="py-1.5 first:pt-0 last:pb-0">
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm hover:underline"
                >
                  {item.title}
                </a>
              ) : (
                <span className="text-sm">{item.title}</span>
              )}
              <div className="text-xs text-muted-foreground">
                {item.source} · {formatAgo(item.published_at)}
                {item.coins.length > 0 && <> · {item.coins.join(', ')}</>}
              </div>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}
