import { describe, expect, it } from 'vitest'

import { TABS, visibleTabs } from './tabs'

const OFF = { onchain_macro: false, mco: false, agent: false, signals: false }

describe('tabs', () => {
  it('follow the ROADMAP Section 1 order', () => {
    expect(TABS.map((t) => t.label)).toEqual([
      'Overview',
      'Charts',
      'Cycles',
      'Stats',
      'On-chain & Macro',
      'MCO',
      'Agent',
      'Signals',
      'Data',
      'Settings',
    ])
  })

  it('hide flagged tabs until their flag is on', () => {
    const v1 = ['Overview', 'Charts', 'Cycles', 'Stats', 'Data', 'Settings']
    expect(visibleTabs(undefined).map((t) => t.label)).toEqual(v1)
    expect(visibleTabs(OFF).map((t) => t.label)).toEqual(v1)
    const labels = visibleTabs({ ...OFF, agent: true, mco: true }).map((t) => t.label)
    expect(labels).toContain('Agent')
    expect(labels).toContain('MCO')
    expect(labels).not.toContain('Signals')
  })
})
