import { useSearchParams } from 'react-router'

import type { Tab } from '@/lib/tabs'

/** Tabs that later substages build. The Data placeholder already accepts "View data" links. */
export function PlaceholderPage({ tab }: { tab: Tab }) {
  const [params] = useSearchParams()
  const table = tab.path === '/data' ? params.get('table') : null
  return (
    <section className="mx-auto my-12 max-w-md space-y-2 text-center">
      <h1 className="text-lg font-semibold">{tab.label}</h1>
      <p className="text-sm text-muted-foreground">Coming in Stage {tab.stage}.</p>
      {table && (
        <p className="text-sm">
          You asked for table <code className="font-mono">{table}</code>
          {params.get('coin') && (
            <>
              {' '}
              for <code className="font-mono">{params.get('coin')}</code>
            </>
          )}
          . The Data tab will open it here.
        </p>
      )}
    </section>
  )
}

export function NotFoundPage() {
  return (
    <section className="mx-auto my-12 max-w-md text-center">
      <h1 className="text-lg font-semibold">Page not found</h1>
      <p className="text-sm text-muted-foreground">Pick a tab above.</p>
    </section>
  )
}
