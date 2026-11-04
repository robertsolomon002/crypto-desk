import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { Segmented } from '@/components/charts/ChartCard'
import {
  InvitesPanel,
  UsagePanel,
  UsersPanel,
  WatchlistPanel,
} from '@/components/settings/AdminPanels'
import { KeyWizard } from '@/components/settings/KeyWizard'
import { ViewsPanel } from '@/components/settings/ViewsPanel'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { useMe } from '@/lib/queries'
import { useTheme, type Theme } from '@/lib/theme'

function Section({
  id,
  title,
  badge,
  children,
}: {
  id: string
  title: string
  badge?: ReactNode
  children: ReactNode
}) {
  return (
    <Card size="sm" className="gap-3 px-4 py-3" aria-labelledby={`${id}-title`} role="region">
      <h2 id={`${id}-title`} className="flex items-center gap-2 text-sm font-semibold">
        {title}
        {badge}
      </h2>
      {children}
    </Card>
  )
}

const THEMES = [
  ['dark', 'Dark'],
  ['light', 'Light'],
] as const

export function SettingsPage() {
  const { data: me } = useMe()
  const [theme, setTheme] = useTheme()
  const isAdmin = me?.role === 'admin'
  return (
    <div className="mx-auto max-w-4xl space-y-3">
      <h1 className="text-sm font-semibold">Settings</h1>

      <Section id="appearance" title="Appearance">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Theme</span>
          <Segmented<Theme> label="Theme" value={theme} options={THEMES} onChange={setTheme} />
        </div>
      </Section>

      <Section
        id="llm"
        title="Your AI key and default model"
        badge={!me?.features.agent && <Badge variant="outline">Agent arrives in v1.1</Badge>}
      >
        <p className="text-sm text-muted-foreground">
          The Agent tab answers questions with the desk&apos;s data, using your own key, so you pay
          the provider directly (usually cents a month) and can cap it.
          {!me?.features.agent &&
            " You can set it up now; it's used once the agent is switched on."}
        </p>
        <KeyWizard />
      </Section>

      {isAdmin && (
        <>
          <Section id="watchlist" title="Watchlist" badge={<Badge variant="outline">admin</Badge>}>
            <WatchlistPanel />
          </Section>
          <Section
            id="invites"
            title="Invite friends"
            badge={<Badge variant="outline">admin</Badge>}
          >
            <InvitesPanel />
          </Section>
          <Section
            id="users"
            title="Users and roles"
            badge={<Badge variant="outline">admin</Badge>}
          >
            <UsersPanel me={me.clerk_id} />
          </Section>
          <Section id="views" title="Outside views" badge={<Badge variant="outline">admin</Badge>}>
            <ViewsPanel />
          </Section>
          <Section id="usage" title="Usage and cost" badge={<Badge variant="outline">admin</Badge>}>
            <UsagePanel />
            <p className="text-sm">
              <Link to="/health" className="underline">
                Open the Health page
              </Link>{' '}
              <span className="text-muted-foreground">
                for jobs, data freshness, errors and free-tier usage.
              </span>
            </p>
          </Section>
        </>
      )}
    </div>
  )
}
