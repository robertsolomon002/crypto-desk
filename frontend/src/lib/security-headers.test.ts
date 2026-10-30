import { describe, expect, it } from 'vitest'

import {
  clerkFrontendApi,
  contentSecurityPolicy,
  pagesHeadersFile,
  securityHeaders,
} from './security-headers'

// base64 of "test-instance.clerk.accounts.dev$", unpadded (the backend tests use the same key)
const PK = 'pk_test_dGVzdC1pbnN0YW5jZS5jbGVyay5hY2NvdW50cy5kZXYk'
const API = 'https://desk-api-850576035365.us-central1.run.app'

function directives(csp: string): Record<string, string[]> {
  return Object.fromEntries(
    csp.split('; ').map((d) => {
      const [name, ...sources] = d.split(' ')
      return [name, sources]
    }),
  )
}

describe('security headers', () => {
  it('decodes the Clerk Frontend API host from the publishable key', () => {
    expect(clerkFrontendApi(PK)).toBe('https://test-instance.clerk.accounts.dev')
    expect(() => clerkFrontendApi('sk_test_abc')).toThrow()
    expect(() => clerkFrontendApi('pk_test_' + btoa('evil.com/path$'))).toThrow()
  })

  it('allows only self, the API, Clerk and Cloudflare bot protection', () => {
    const csp = directives(
      contentSecurityPolicy({ apiBaseUrl: API + '/', clerkPublishableKey: PK }),
    )
    const clerk = 'https://test-instance.clerk.accounts.dev'
    expect(csp['script-src']).toEqual([
      "'self'",
      clerk,
      'https://challenges.cloudflare.com',
      'https://*.protect.clerk.com',
    ])
    expect(csp['connect-src']).toEqual(["'self'", API, clerk, 'https://*.protect.clerk.com:*'])
    expect(csp['default-src']).toEqual(["'self'"])
    expect(csp['object-src']).toEqual(["'none'"])
    expect(csp['frame-ancestors']).toEqual(["'none'"])
    // never inline or eval'd scripts
    expect(csp['script-src'].join(' ')).not.toMatch(/unsafe/)
  })

  it('works without a Clerk key or API URL (CI smoke builds)', () => {
    const csp = directives(contentSecurityPolicy({}))
    expect(csp['connect-src']).toEqual(["'self'", 'https://*.protect.clerk.com:*'])
  })

  it('rejects a plain-http API URL', () => {
    expect(() => contentSecurityPolicy({ apiBaseUrl: 'http://example.com' })).toThrow()
  })

  it('writes a Cloudflare Pages _headers rule for every path', () => {
    const file = pagesHeadersFile(securityHeaders({ apiBaseUrl: API, clerkPublishableKey: PK }))
    const lines = file.trimEnd().split('\n')
    expect(lines[0]).toBe('/*')
    expect(lines.slice(1).every((line) => line.startsWith('  ') && line.length <= 2000)).toBe(true)
    expect(file).toContain('  X-Content-Type-Options: nosniff\n')
  })
})
