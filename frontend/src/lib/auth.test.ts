import { describe, expect, it } from 'vitest'

import { FAKE_AUTH } from './auth'

// The workflow and vite.config.ts checks live in build-guards.test.ts (they read files).
describe('fake auth', () => {
  it('is off in normal builds and tests', () => {
    expect(FAKE_AUTH).toBe(false)
  })
})
