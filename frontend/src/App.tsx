import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router'

import { HealthPage } from '@/routes/health'

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="flex min-h-svh flex-col bg-background text-foreground">
          <header className="border-b px-4 py-2 font-semibold">Crypto Desk</header>
          <main className="flex-1 px-4">
            <Routes>
              <Route path="/" element={<HealthPage />} />
            </Routes>
          </main>
          <footer className="border-t px-4 py-2 text-xs text-muted-foreground">
            Not financial advice. For information only; no trading.
          </footer>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
