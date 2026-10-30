// Security headers for the static frontend (Stage 2.2, D38). Built from the same env as the
// bundle: `vite build` writes them to `dist/_headers` for Cloudflare Pages, and `vite preview`
// serves them too, so the Playwright smoke tests run under the production CSP.
//
// Clerk's CSP guide (checked 2026-10-30) needs: the Frontend API host in script-src and
// connect-src; https://*.protect.clerk.com (connect-src with a `:*` port wildcard) and
// https://challenges.cloudflare.com (bot protection) in script-src and frame-src;
// https://img.clerk.com in img-src; `'self' blob:` in worker-src; and `'unsafe-inline'` in
// style-src (runtime CSS-in-JS; Lightweight Charts also injects a <style>). No inline or eval'd
// scripts: Vite emits external module scripts only.

export interface HeaderEnv {
  apiBaseUrl?: string // VITE_API_BASE_URL (Cloud Run); empty means same origin
  clerkPublishableKey?: string // VITE_CLERK_PUBLISHABLE_KEY
}

/** `pk_test_`/`pk_live_` + unpadded base64 of `<frontend-api-host>$` (Clerk's documented format,
 * the same decoding as the backend's `issuer_from_publishable_key`). */
export function clerkFrontendApi(publishableKey: string): string {
  const match = /^pk_(test|live)_([A-Za-z0-9+/=]+)$/.exec(publishableKey.trim())
  if (!match) throw new Error('not a Clerk publishable key')
  const encoded = match[2]
  const host = atob(encoded + '='.repeat((4 - (encoded.length % 4)) % 4))
  if (!host.endsWith('$') || !/^[a-z0-9.-]+\$$/i.test(host)) {
    throw new Error('not a Clerk publishable key')
  }
  return `https://${host.slice(0, -1)}`
}

function origin(url: string): string {
  const parsed = new URL(url)
  if (parsed.protocol !== 'https:' && parsed.hostname !== 'localhost') {
    throw new Error(`API base URL must be https: ${url}`)
  }
  return parsed.origin
}

export function contentSecurityPolicy(env: HeaderEnv): string {
  const clerk = env.clerkPublishableKey ? [clerkFrontendApi(env.clerkPublishableKey)] : []
  const api = env.apiBaseUrl ? [origin(env.apiBaseUrl)] : []
  const protect = 'https://*.protect.clerk.com'
  const challenges = 'https://challenges.cloudflare.com'
  const directives: Record<string, string[]> = {
    'default-src': ["'self'"],
    'script-src': ["'self'", ...clerk, challenges, protect],
    'connect-src': ["'self'", ...api, ...clerk, `${protect}:*`],
    'img-src': ["'self'", 'data:', 'https://img.clerk.com'],
    'style-src': ["'self'", "'unsafe-inline'"],
    'font-src': ["'self'"],
    'worker-src': ["'self'", 'blob:'],
    'frame-src': [challenges, protect],
    'form-action': ["'self'"],
    'base-uri': ["'self'"],
    'object-src': ["'none'"],
    'frame-ancestors': ["'none'"],
  }
  return Object.entries(directives)
    .map(([name, sources]) => `${name} ${sources.join(' ')}`)
    .join('; ')
}

export function securityHeaders(env: HeaderEnv): Record<string, string> {
  return {
    'Content-Security-Policy': contentSecurityPolicy(env),
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
    'Strict-Transport-Security': 'max-age=31536000',
  }
}

/** Cloudflare Pages `_headers`: one rule for every path; each line is limited to 2,000 chars. */
export function pagesHeadersFile(headers: Record<string, string>): string {
  const lines = ['/*', ...Object.entries(headers).map(([name, value]) => `  ${name}: ${value}`)]
  for (const line of lines) {
    if (line.length > 2000) throw new Error(`_headers line over 2,000 characters: ${line}`)
  }
  return lines.join('\n') + '\n'
}
