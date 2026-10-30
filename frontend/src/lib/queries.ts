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
