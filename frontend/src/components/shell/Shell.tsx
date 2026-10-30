import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router'

import { useMe } from '@/lib/queries'
import { visibleTabs } from '@/lib/tabs'

import { CoinSelector } from './CoinSelector'
import { ColdStartBanner } from './ColdStartBanner'
import { ErrorBoundary } from './ErrorBoundary'
import { Footer } from './Footer'
import { DesktopTabs, PhoneTabBar } from './TabNav'
import { ThemeToggle } from './ThemeToggle'

export function Shell({ userMenu, children }: { userMenu: ReactNode; children: ReactNode }) {
  const { data: me } = useMe()
  const tabs = visibleTabs(me?.features)
  const { pathname } = useLocation()
  return (
    <div className="flex min-h-svh flex-col bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
        <div className="flex h-12 items-center gap-3 px-4">
          <Link to="/" className="shrink-0 font-mono text-sm font-semibold tracking-tight">
            Crypto Desk
          </Link>
          <DesktopTabs tabs={tabs} />
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <CoinSelector />
            <ThemeToggle />
            {userMenu}
          </div>
        </div>
        <ColdStartBanner />
      </header>
      {/* pb-16 leaves room for the phone tab bar */}
      <main className="w-full flex-1 px-4 py-4 pb-20 md:pb-6">
        <ErrorBoundary key={pathname} label="This tab">
          {children}
        </ErrorBoundary>
      </main>
      <div className="pb-14 md:pb-0">
        <Footer />
      </div>
      <PhoneTabBar tabs={tabs} />
    </div>
  )
}
