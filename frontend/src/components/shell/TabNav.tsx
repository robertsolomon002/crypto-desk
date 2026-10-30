import { MoreHorizontal } from 'lucide-react'
import { NavLink, useNavigate, useSearchParams } from 'react-router'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { PHONE_BAR_TABS, type Tab } from '@/lib/tabs'
import { cn } from '@/lib/utils'

/** Tab links keep only the selected coin from the current URL. */
function useTabSearch(): string {
  const [params] = useSearchParams()
  const coin = params.get('coin')
  return coin ? `?coin=${encodeURIComponent(coin)}` : ''
}

export function DesktopTabs({ tabs }: { tabs: Tab[] }) {
  const search = useTabSearch()
  return (
    <nav aria-label="Tabs" className="hidden min-w-0 overflow-x-auto md:block">
      <ul className="flex gap-1">
        {tabs.map((tab) => (
          <li key={tab.path}>
            <NavLink
              to={{ pathname: tab.path, search }}
              end={tab.path === '/'}
              className={({ isActive }) =>
                cn(
                  'block rounded-md px-2.5 py-1.5 text-sm whitespace-nowrap text-muted-foreground hover:bg-accent hover:text-foreground',
                  isActive && 'bg-accent font-medium text-foreground',
                )
              }
            >
              {tab.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

export function PhoneTabBar({ tabs }: { tabs: Tab[] }) {
  const search = useTabSearch()
  const navigate = useNavigate()
  const bar = tabs.slice(0, PHONE_BAR_TABS)
  const more = tabs.slice(PHONE_BAR_TABS)
  const item =
    'flex h-full flex-1 flex-col items-center justify-center text-xs text-muted-foreground'
  return (
    <nav
      aria-label="Tabs"
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-card pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <ul className="flex h-14">
        {bar.map((tab) => (
          <li key={tab.path} className="flex flex-1">
            <NavLink
              to={{ pathname: tab.path, search }}
              end={tab.path === '/'}
              className={({ isActive }) => cn(item, isActive && 'font-semibold text-foreground')}
            >
              {tab.short}
            </NavLink>
          </li>
        ))}
        {more.length > 0 && (
          <li className="flex flex-1">
            <DropdownMenu>
              <DropdownMenuTrigger className={item} aria-label="More tabs">
                <MoreHorizontal className="size-4" aria-hidden />
                More
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" side="top">
                {more.map((tab) => (
                  <DropdownMenuItem
                    key={tab.path}
                    onSelect={() => navigate({ pathname: tab.path, search })}
                  >
                    {tab.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </li>
        )}
      </ul>
    </nav>
  )
}
