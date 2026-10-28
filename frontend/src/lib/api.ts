import createClient from 'openapi-fetch'

import type { components, paths } from './api-schema'

// Generated from the FastAPI OpenAPI schema: `npm run gen:api` after any API change.
// In dev, Vite proxies /api to the local backend; in production VITE_API_BASE_URL points at Cloud Run.
export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? window.location.origin,
  // Look fetch up per call (openapi-fetch otherwise captures it at creation), so tests can stub it.
  fetch: (request) => globalThis.fetch(request),
})

export type Health = components['schemas']['HealthResponse']

export async function getHealth(): Promise<Health> {
  const { data, error } = await api.GET('/api/health')
  if (error || !data) throw new Error('Health check failed')
  return data
}
