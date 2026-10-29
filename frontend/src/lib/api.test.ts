import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, setTokenGetter } from './api'

describe('api client auth', () => {
  afterEach(() => {
    setTokenGetter(null)
    vi.unstubAllGlobals()
  })

  function stubFetch() {
    // Typed so the test can read the request the client sent.
    const fetch = vi.fn<(request: Request) => Promise<Response>>(async () =>
      Response.json({ clerk_id: 'u', role: 'member' }),
    )
    vi.stubGlobal('fetch', fetch)
    return fetch
  }

  it('sends the Clerk token as a bearer header', async () => {
    const fetch = stubFetch()
    setTokenGetter(async () => 'tok_123')
    await api.GET('/api/me')
    expect(fetch.mock.calls[0][0].headers.get('Authorization')).toBe('Bearer tok_123')
  })

  it('sends no header without a token', async () => {
    const fetch = stubFetch()
    await api.GET('/api/me')
    expect(fetch.mock.calls[0][0].headers.get('Authorization')).toBeNull()
  })
})
