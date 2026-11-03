import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, useLocation } from 'react-router'
import { vi } from 'vitest'

/**
 * Answers fetches by URL path from `routes`; a number value is an error status, and a function
 * builds the response itself (an SSE stream, say).
 */
export function stubApi(routes: Record<string, unknown>) {
  const fetch = vi.fn(async (request: Request) => {
    const body = routes[new URL(request.url).pathname]
    if (body === undefined) return Response.json({ detail: 'not mocked' }, { status: 404 })
    if (typeof body === 'function') return (body as (r: Request) => Response)(request)
    if (typeof body === 'number') return Response.json({}, { status: body })
    return Response.json(body)
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

/** Shows the current URL so tests can assert navigation and query changes. */
function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

export function renderWithProviders(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        {ui}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

export const envelope = <T,>(data: T) => ({ as_of: '2026-10-29', sources: [], data })

/** An SSE response from (event, data) pairs, cut into small chunks that split events apart. */
export function sseResponse(events: [string, unknown][], chunk = 17): Response {
  const text = events
    .map(
      ([e, d]) => `event: ${e}
data: ${JSON.stringify(d)}

`,
    )
    .join('')
  const bytes = new TextEncoder().encode(`: ping

${text}`)
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let i = 0; i < bytes.length; i += chunk) controller.enqueue(bytes.slice(i, i + chunk))
      controller.close()
    },
  })
  return new Response(stream, { headers: { 'content-type': 'text/event-stream' } })
}
