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
