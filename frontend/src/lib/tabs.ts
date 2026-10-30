import type { Features } from './queries'

// Tabs in ROADMAP Section 1 order. Later-version tabs carry a feature flag from `/api/me`
// (config/settings.yaml, Decision 1) and stay hidden until it is on.

export interface Tab {
  path: string
  label: string
  short: string // phone bottom bar
  stage: string // the substage that builds it
  flag?: keyof Features
}

export const TABS: Tab[] = [
  { path: '/', label: 'Overview', short: 'Overview', stage: '3.1' },
  { path: '/charts', label: 'Charts', short: 'Charts', stage: '3.2' },
  { path: '/cycles', label: 'Cycles', short: 'Cycles', stage: '3.3' },
  { path: '/stats', label: 'Stats', short: 'Stats', stage: '3.3' },
  {
    path: '/onchain',
    label: 'On-chain & Macro',
    short: 'On-chain',
    stage: '4.1',
    flag: 'onchain_macro',
  },
  { path: '/mco', label: 'MCO', short: 'MCO', stage: '6.2', flag: 'mco' },
  { path: '/agent', label: 'Agent', short: 'Agent', stage: '5.2', flag: 'agent' },
  { path: '/signals', label: 'Signals', short: 'Signals', stage: '7.2', flag: 'signals' },
  { path: '/data', label: 'Data', short: 'Data', stage: '3.4' },
  { path: '/settings', label: 'Settings', short: 'Settings', stage: '3.4' },
]

/** Tabs to show; flagged tabs need their flag on (hidden while `/api/me` is loading). */
export function visibleTabs(features: Features | undefined): Tab[] {
  return TABS.filter((tab) => !tab.flag || features?.[tab.flag] === true)
}

/** How many tabs fit in the phone bottom bar before the "More" menu. */
export const PHONE_BAR_TABS = 4
