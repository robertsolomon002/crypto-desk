import { QueryClient, useQuery } from '@tanstack/react-query'

import { api } from './api'
import type { components } from './api-schema'

type Schemas = components['schemas']
export type Me = Schemas['Me']
export type Features = Schemas['Features']
export type CoinOut = Schemas['CoinOut']
export type Overview = Schemas['Envelope_OverviewData_']
export type CoinCard = Schemas['CoinCard']
export type Freshness = Schemas['Freshness']
export type JobStatus = Schemas['JobStatus']
export type Headline = Schemas['Headline']
export type MacroEvent = Schemas['Event']
export type SeriesPoint = Schemas['SeriesPoint']

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** The body of an openapi-fetch result, or an ApiError carrying the HTTP status. */
export async function unwrap<T>(call: Promise<{ data?: T; response: Response }>): Promise<T> {
  const { data, response } = await call
  if (!response.ok || data === undefined) {
    throw new ApiError(response.status, `Request failed (${response.status})`)
  }
  return data
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 60_000, // data changes once a day; the daily job runs at 00:20 UTC
        refetchOnWindowFocus: false,
        // A 4xx won't fix itself; a 5xx or network error gets one retry.
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 1,
      },
    },
  })
}

export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: () => unwrap(api.GET('/api/me')) })
}

export function useCoins() {
  return useQuery({ queryKey: ['coins'], queryFn: () => unwrap(api.GET('/api/coins')) })
}

export function useOverview() {
  return useQuery({ queryKey: ['overview'], queryFn: () => unwrap(api.GET('/api/overview')) })
}

export function useFearGreed(start: string) {
  return useQuery({
    queryKey: ['fng', start],
    queryFn: () => unwrap(api.GET('/api/macro/fng', { params: { query: { start } } })),
  })
}

export function useCalendar(daysAhead: number) {
  return useQuery({
    queryKey: ['calendar', daysAhead],
    queryFn: () =>
      unwrap(api.GET('/api/calendar', { params: { query: { days_ahead: daysAhead } } })),
  })
}

export function useNews(limit: number) {
  return useQuery({
    queryKey: ['news', limit],
    queryFn: () => unwrap(api.GET('/api/news', { params: { query: { limit } } })),
  })
}

export type Candle = Schemas['Candle']
export type ChartTimeframe = '1d' | '1w' | '4h'

export function useOhlcv(coin: string | null, tf: ChartTimeframe) {
  return useQuery({
    queryKey: ['ohlcv', coin, tf],
    queryFn: () =>
      unwrap(
        api.GET('/api/ohlcv/{coin}', { params: { path: { coin: coin as string }, query: { tf } } }),
      ),
    enabled: coin !== null,
  })
}

export function useLevels(coin: string, enabled: boolean) {
  return useQuery({
    queryKey: ['levels', coin],
    queryFn: () => unwrap(api.GET('/api/levels/{coin}', { params: { path: { coin } } })),
    enabled,
  })
}

export function usePivots(coin: string, timeframe: '1d' | '1w', enabled: boolean) {
  return useQuery({
    queryKey: ['pivots', coin, timeframe],
    queryFn: () =>
      unwrap(api.GET('/api/pivots/{coin}', { params: { path: { coin }, query: { timeframe } } })),
    enabled,
  })
}

// --- Cycles and Stats (Stage 3.3). Each returns the analytics envelope; `result` is typed by the
// caller from `cycles-data.ts` / `stats-data.ts`. A 404 means the coin has no such data (cycles
// cover BTC and ETH only).

export type AnalyticsEnvelope = Schemas['Envelope_AnalyticsData_']
export type AnchorModeParam = 'halving' | 'bottom' | 'top'

export function useCycleAnchors(coin: string) {
  return useQuery({
    queryKey: ['cycles', 'anchors', coin],
    queryFn: () => unwrap(api.GET('/api/cycles/{coin}/anchors', { params: { path: { coin } } })),
  })
}

export function useCyclePaths(coin: string, mode: AnchorModeParam, enabled = true) {
  return useQuery({
    queryKey: ['cycles', 'paths', coin, mode],
    queryFn: () =>
      unwrap(
        api.GET('/api/cycles/{coin}/paths', {
          params: { path: { coin }, query: { mode, max_days: 1500 } },
        }),
      ),
    enabled,
  })
}

export function useCycleDayN(coin: string, mode: AnchorModeParam, enabled = true) {
  return useQuery({
    queryKey: ['cycles', 'day-n', coin, mode],
    queryFn: () =>
      unwrap(api.GET('/api/cycles/{coin}/day-n', { params: { path: { coin }, query: { mode } } })),
    enabled,
  })
}

export function useRoiSinceBottom(coin: string, enabled = true) {
  return useQuery({
    queryKey: ['cycles', 'roi', coin],
    queryFn: () => unwrap(api.GET('/api/cycles/{coin}/roi', { params: { path: { coin } } })),
    enabled,
  })
}

export function useYoy(coin: string, enabled = true) {
  return useQuery({
    queryKey: ['cycles', 'yoy', coin],
    queryFn: () => unwrap(api.GET('/api/cycles/{coin}/yoy', { params: { path: { coin } } })),
    enabled,
  })
}

export function useSeasonality(coin: string, period: 'monthly' | 'weekly' | 'dow') {
  return useQuery({
    queryKey: ['stats', 'seasonality', coin, period],
    queryFn: () =>
      unwrap(
        api.GET('/api/stats/{coin}/seasonality/{period}', {
          params: { path: { coin, period } },
        }),
      ),
  })
}

export function useDistribution(coin: string, horizon: '1d' | '1w' | '30d') {
  return useQuery({
    queryKey: ['stats', 'distribution', coin, horizon],
    queryFn: () =>
      unwrap(
        api.GET('/api/stats/{coin}/distribution', {
          params: { path: { coin }, query: { horizon } },
        }),
      ),
  })
}

export function useDrawdowns(coin: string) {
  return useQuery({
    queryKey: ['stats', 'drawdowns', coin],
    queryFn: () => unwrap(api.GET('/api/stats/{coin}/drawdowns', { params: { path: { coin } } })),
  })
}

export function useDrawdownEpisodes(coin: string) {
  return useQuery({
    queryKey: ['stats', 'drawdown-episodes', coin],
    queryFn: () =>
      unwrap(
        api.GET('/api/stats/{coin}/drawdown-episodes', {
          params: { path: { coin }, query: { top_n: 10 } },
        }),
      ),
  })
}

export function useVolatility(coin: string) {
  return useQuery({
    queryKey: ['stats', 'volatility', coin],
    queryFn: () => unwrap(api.GET('/api/stats/{coin}/volatility', { params: { path: { coin } } })),
  })
}

export function useCorrelation(coin: string, window: number) {
  return useQuery({
    queryKey: ['stats', 'correlation', coin, window],
    queryFn: () =>
      unwrap(
        api.GET('/api/stats/{coin}/correlation', {
          params: { path: { coin }, query: { window } },
        }),
      ),
  })
}

// --- On-chain & Macro (Stage 4.1) ---------------------------------------------------------------

export function useOnchain(coin: string) {
  return useQuery({
    queryKey: ['onchain', coin],
    queryFn: () => unwrap(api.GET('/api/onchain/{coin}', { params: { path: { coin } } })),
  })
}

export function useMacro() {
  return useQuery({ queryKey: ['macro'], queryFn: () => unwrap(api.GET('/api/macro')) })
}

export function useDominance() {
  return useQuery({
    queryKey: ['dominance'],
    queryFn: () => unwrap(api.GET('/api/macro/dominance')),
  })
}

// --- Data tab (Stage 3.4) ------------------------------------------------------------------------

export type TableInfo = Schemas['TableInfo']
export type TablePage = Schemas['TablePage']

export function useTables() {
  return useQuery({
    queryKey: ['data', 'tables'],
    queryFn: () => unwrap(api.GET('/api/data/tables')),
  })
}

export interface TableQuery {
  filters: string[]
  order: string | null
  desc: boolean
  page: number
  pageSize: number
}

export function useTablePage(name: string | null, q: TableQuery, enabled = true) {
  return useQuery({
    queryKey: ['data', 'table', name, q],
    queryFn: () =>
      unwrap(
        api.GET('/api/data/tables/{name}', {
          params: {
            path: { name: name as string },
            query: {
              filter: q.filters,
              order: q.order ?? undefined,
              desc: q.desc,
              page: q.page,
              page_size: q.pageSize,
            },
          },
        }),
      ),
    enabled: enabled && name !== null,
    placeholderData: (previous) => previous, // keep the old page on screen while paging
  })
}

/** The filtered table as a CSV blob (the endpoint needs the session token, so no plain link). */
export async function exportTable(name: string, q: Pick<TableQuery, 'filters' | 'order' | 'desc'>) {
  const { data, response } = await api.GET('/api/data/tables/{name}/export.csv', {
    params: {
      path: { name },
      query: { filter: q.filters, order: q.order ?? undefined, desc: q.desc },
    },
    parseAs: 'blob',
  })
  if (!response.ok || !data)
    throw new ApiError(response.status, `Export failed (${response.status})`)
  return data as Blob
}

/**
 * A computed analytics result by registry name (`table=analytics&fn=...`, D41), through the same
 * route its chart uses. Unknown names are a 404 like an unknown table.
 */
export async function fetchAnalytics(
  fn: string,
  coin: string,
  p: Record<string, string | undefined>,
): Promise<AnalyticsEnvelope> {
  const path = { coin }
  const mode = (p.mode ?? 'halving') as AnchorModeParam
  switch (fn) {
    case 'cycles_anchors':
      return unwrap(api.GET('/api/cycles/{coin}/anchors', { params: { path } }))
    case 'cycles_paths':
      return unwrap(
        api.GET('/api/cycles/{coin}/paths', { params: { path, query: { mode, max_days: 1500 } } }),
      )
    case 'cycles_day_n':
      return unwrap(api.GET('/api/cycles/{coin}/day-n', { params: { path, query: { mode } } }))
    case 'roi_since_bottom':
      return unwrap(api.GET('/api/cycles/{coin}/roi', { params: { path } }))
    case 'yoy':
      return unwrap(api.GET('/api/cycles/{coin}/yoy', { params: { path } }))
    case 'seasonality_monthly':
    case 'seasonality_weekly':
    case 'seasonality_dow': {
      const period = fn.slice('seasonality_'.length) as 'monthly' | 'weekly' | 'dow'
      return unwrap(
        api.GET('/api/stats/{coin}/seasonality/{period}', { params: { path: { coin, period } } }),
      )
    }
    case 'return_distribution': {
      const horizon = (['1d', '1w', '30d'].includes(p.horizon ?? '') ? p.horizon : '1w') as
        '1d' | '1w' | '30d'
      return unwrap(
        api.GET('/api/stats/{coin}/distribution', { params: { path, query: { horizon } } }),
      )
    }
    case 'drawdowns':
      return unwrap(api.GET('/api/stats/{coin}/drawdowns', { params: { path } }))
    case 'drawdown_episodes':
      return unwrap(
        api.GET('/api/stats/{coin}/drawdown-episodes', { params: { path, query: { top_n: 10 } } }),
      )
    case 'rolling_volatility':
      return unwrap(api.GET('/api/stats/{coin}/volatility', { params: { path } }))
    case 'rolling_correlation': {
      const window = Number(p.window) || 90
      return unwrap(
        api.GET('/api/stats/{coin}/correlation', { params: { path, query: { window } } }),
      )
    }
    case 'onchain':
      return unwrap(api.GET('/api/onchain/{coin}', { params: { path } }))
    default:
      throw new ApiError(404, `Unknown analytics result ${fn}`)
  }
}

export function useAnalyticsResult(
  fn: string | null,
  coin: string,
  p: Record<string, string | undefined>,
) {
  return useQuery({
    queryKey: ['data', 'analytics', fn, coin, p],
    queryFn: () => fetchAnalytics(fn as string, coin, p),
    enabled: fn !== null,
  })
}

// --- Settings (Stage 3.4) ------------------------------------------------------------------------

export type ProviderModels = Schemas['ProviderModels']
export type KeyTestResult = Schemas['KeyTestResult']

export function useModels() {
  return useQuery({
    queryKey: ['agent', 'models'],
    queryFn: () => unwrap(api.GET('/api/agent/models')),
    staleTime: Infinity,
  })
}

/** The 1-token key test. The key goes only into this request's `X-LLM-Key` header. */
export function testKey(
  provider: 'openrouter' | 'anthropic' | 'openai',
  key: string,
  model: string | null,
) {
  return unwrap(
    api.POST('/api/agent/test-key', {
      body: { provider, model: model || null },
      headers: { 'X-LLM-Key': key },
    }),
  )
}

export type WatchlistCoin = Schemas['WatchlistCoin']
export type Eligibility = Schemas['Eligibility']
export type Invite = Schemas['Invite']
export type UserOut = Schemas['UserOut']
export type Usage = Schemas['Usage']

export function useWatchlist(enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'watchlist'],
    queryFn: () => unwrap(api.GET('/api/admin/watchlist')),
    enabled,
  })
}

export function useInvites(enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'invites'],
    queryFn: () => unwrap(api.GET('/api/admin/invites')),
    enabled,
  })
}

export function useUsers(enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => unwrap(api.GET('/api/admin/users')),
    enabled,
  })
}

export function useUsage(enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'usage'],
    queryFn: () => unwrap(api.GET('/api/admin/usage')),
    enabled,
  })
}

/** The API's error text (`detail`) for a failed admin action, shown to the admin as text. */
export async function apiAction<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call
  if (response.ok) return data as T
  const detail = (error as { detail?: unknown } | undefined)?.detail
  const message =
    typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? 'Check the fields and try again.'
        : `Request failed (${response.status})`
  throw new ApiError(response.status, message)
}
