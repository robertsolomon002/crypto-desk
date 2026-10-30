import { QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, useState, type ReactElement } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router'

import { ErrorBoundary } from '@/components/shell/ErrorBoundary'
import { Shell } from '@/components/shell/Shell'
import { Skeleton } from '@/components/ui/skeleton'
import { AuthRoot } from '@/lib/auth'
import { createQueryClient, useMe } from '@/lib/queries'
import { TABS, visibleTabs } from '@/lib/tabs'
import { HealthPage } from '@/routes/health'
import { OverviewPage } from '@/routes/overview'
import { NotFoundPage, PlaceholderPage } from '@/routes/placeholder'

// The chart libraries load only with the tabs that use them, keeping the first load small.
const ChartsPage = lazy(() => import('@/routes/charts').then((m) => ({ default: m.ChartsPage })))

function TabPage({ label, children }: { label: string; children: ReactElement }) {
  return (
    <ErrorBoundary label={label}>
      <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-7xl" />}>{children}</Suspense>
    </ErrorBoundary>
  )
}

// Tabs that have their page built; the rest show a placeholder naming their substage.
const BUILT: Record<string, ReactElement> = {
  '/charts': (
    <TabPage label="The Charts tab">
      <ChartsPage />
    </TabPage>
  ),
}

function AppRoutes() {
  const { data: me } = useMe()
  const visible = new Set(visibleTabs(me?.features).map((tab) => tab.path))
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      {TABS.filter((tab) => tab.path !== '/' && visible.has(tab.path)).map((tab) => (
        <Route
          key={tab.path}
          path={tab.path}
          element={BUILT[tab.path] ?? <PlaceholderPage tab={tab} />}
        />
      ))}
      <Route path="/health" element={<HealthPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default function App() {
  const [queryClient] = useState(createQueryClient)
  return (
    <ErrorBoundary label="The app">
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthRoot>
            {(userMenu) => (
              <Shell userMenu={userMenu}>
                <AppRoutes />
              </Shell>
            )}
          </AuthRoot>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
