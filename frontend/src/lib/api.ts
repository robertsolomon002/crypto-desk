import createClient from 'openapi-fetch'

import type { components, paths } from './api-schema'

// Generated from the FastAPI OpenAPI schema: `npm run gen:api` after any API change.
// In dev, Vite proxies /api to the local backend; in production VITE_API_BASE_URL points at Cloud Run.
export const api = createClient<paths>({
  // `||`, not `??`: the variable is often present but empty (dev), which must mean the origin.
  baseUrl: import.meta.env.VITE_API_BASE_URL || window.location.origin,
  // Look fetch up per call (openapi-fetch otherwise captures it at creation), so tests can stub it.
  fetch: (request) => globalThis.fetch(request),
})

// Every route except /api/health needs Clerk's session token. The app shell (Stage 3.1) registers
// Clerk's `getToken` here; until then requests go out unauthenticated.
type TokenGetter = () => Promise<string | null>
let getToken: TokenGetter | null = null

export function setTokenGetter(getter: TokenGetter | null): void {
  getToken = getter
}

api.use({
  async onRequest({ request }) {
    const token = getToken ? await getToken() : null
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
})

export type Health = components['schemas']['HealthResponse']

export async function getHealth(): Promise<Health> {
  const { data, error } = await api.GET('/api/health')
  if (error || !data) throw new Error('Health check failed')
  return data
}
