import type { Tab } from '@/lib/tabs'

/** Tabs that later substages build. */
export function PlaceholderPage({ tab }: { tab: Tab }) {
  return (
    <section className="mx-auto my-12 max-w-md space-y-2 text-center">
      <h1 className="text-lg font-semibold">{tab.label}</h1>
      <p className="text-sm text-muted-foreground">Coming in Stage {tab.stage}.</p>
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
