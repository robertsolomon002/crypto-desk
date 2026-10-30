import { QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router'

import { ErrorBoundary } from '@/components/shell/ErrorBoundary'
import { Shell } from '@/components/shell/Shell'
import { AuthRoot } from '@/lib/auth'
import { createQueryClient, useMe } from '@/lib/queries'
import { TABS, visibleTabs } from '@/lib/tabs'
import { HealthPage } from '@/routes/health'
import { OverviewPage } from '@/routes/overview'
import { NotFoundPage, PlaceholderPage } from '@/routes/placeholder'

function AppRoutes() {
  const { data: me } = useMe()
  const visible = new Set(visibleTabs(me?.features).map((tab) => tab.path))
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      {TABS.filter((tab) => tab.path !== '/' && visible.has(tab.path)).map((tab) => (
        <Route key={tab.path} path={tab.path} element={<PlaceholderPage tab={tab} />} />
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
