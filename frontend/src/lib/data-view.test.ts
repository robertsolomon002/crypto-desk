import { describe, expect, it } from 'vitest'

import {
  expandCompact,
  snapshotView,
  buildFilters,
  cellText,
  coinColumn,
  dateColumn,
  isNumeric,
  resultView,
  toCsv,
  type ColumnInfo,
} from './data-view'

const col = (name: string, type: string, filterable = true): ColumnInfo => ({
  name,
  type,
  filterable,
})
const CANDLES = [
  col('coin', 'VARCHAR(16)'),
  col('date', 'DATE'),
  col('close', 'DOUBLE'),
  col('source', 'VARCHAR(32)'),
]
const NEWS = [
  col('id', 'BIGINT'),
  col('title', 'TEXT'),
  col('published_at', 'DATETIME'),
  col('coins', 'ARRAY'),
  col('fetched_at', 'DATETIME'),
]
const SERIES = [col('key', 'VARCHAR(64)'), col('date', 'DATE'), col('value', 'DOUBLE')]

describe('filters from deep links', () => {
  it('filters candles by coin and an inclusive date range', () => {
    expect(buildFilters(CANDLES, { coin: 'BTC', from: '2026-01-01', to: '2026-01-31' })).toEqual([
      'coin:eq:BTC',
      'date:gte:2026-01-01',
      'date:lte:2026-01-31',
    ])
  })

  it('uses contains on the headline coins array and a next-day bound on timestamps', () => {
    expect(buildFilters(NEWS, { coin: 'ETH', from: '2026-10-01', to: '2026-10-31' })).toEqual([
      'coins:contains:ETH',
      'published_at:gte:2026-10-01',
      'published_at:lt:2026-11-01',
    ])
  })

  it('turns other column parameters into equality filters and ignores unknown ones', () => {
    expect(
      buildFilters(SERIES, {
        extra: [
          ['key', 'fng'],
          ['nope', 'x'],
          ['page', '2'],
        ],
      }),
    ).toEqual(['key:eq:fng'])
  })

  it('leaves the coins table unfiltered by the selected coin', () => {
    const coins = [col('symbol', 'VARCHAR(16)'), col('added_at', 'DATETIME')]
    expect(coinColumn(coins)).toBeNull()
    expect(buildFilters(coins, { coin: 'BTC' })).toEqual([])
  })

  it('picks the main date column and spots numeric columns', () => {
    expect(dateColumn(NEWS)?.name).toBe('published_at')
    expect(dateColumn([col('x', 'TEXT')])).toBeNull()
    expect(isNumeric(col('cost', 'NUMERIC(12, 6)'))).toBe(true)
    expect(isNumeric(col('id', 'BIGINT'))).toBe(true)
    expect(isNumeric(col('date', 'DATE'))).toBe(false)
  })
})

describe('cells and CSV', () => {
  it('renders arrays, objects and nulls as plain text', () => {
    expect(cellText(['BTC', 'ETH'])).toBe('BTC, ETH')
    expect(cellText({ a: 1 })).toBe('{"a":1}')
    expect(cellText(null)).toBe('')
  })

  it('neutralizes formulas in text but keeps negative numbers', () => {
    const csv = toCsv(
      ['title', 'value'],
      [
        { title: '=HYPERLINK("http://x")', value: -0.5 },
        { title: 'a, "quoted" title', value: 1 },
        { title: '@cmd', value: null },
      ],
    )
    expect(csv.split('\r\n')).toEqual([
      'title,value',
      `"'=HYPERLINK(""http://x"")",-0.5`,
      '"a, ""quoted"" title",1',
      "'@cmd,",
    ])
  })
})

describe('analytics results as tables', () => {
  it('shows a list of records as one table, flattening nested objects', () => {
    const view = resultView([
      { name: '2013', bottom: { date: '2011-11-18', price: 2.1 }, top: null },
    ])
    expect(view.parts[0].columns).toEqual(['name', 'bottom.date', 'bottom.price', 'top'])
    expect(view.values).toEqual([])
  })

  it('splits an object into its tables and single values', () => {
    const view = resultView({
      mode: 'halving',
      current_cycle: '2025',
      day: 924,
      table: [{ cycle: '2013', day: 924 }],
    })
    expect(view.parts.map((p) => p.name)).toEqual(['table'])
    expect(view.values).toEqual([
      ['mode', 'halving'],
      ['current_cycle', '2025'],
      ['day', 924],
    ])
  })

  it('turns bins and counts into a histogram table', () => {
    const view = resultView({
      horizon: '1w',
      bins: [-0.1, 0, 0.1],
      counts: [3, 5],
      quantiles: { p50: 0.01 },
    })
    expect(view.parts[0]).toEqual({
      name: 'histogram',
      columns: ['bin_from', 'bin_to', 'count'],
      rows: [
        { bin_from: -0.1, bin_to: 0, count: 3 },
        { bin_from: 0, bin_to: 0.1, count: 5 },
      ],
    })
    expect(view.values).toContainEqual(['quantiles.p50', 0.01])
  })

  it('keeps both tables of a seasonality result', () => {
    const view = resultView({
      matrix: [{ year: 2026, '1': 0.1 }],
      summary: [{ month: 1, mean: 0.1 }],
    })
    expect(view.parts.map((p) => p.name)).toEqual(['matrix', 'summary'])
  })
})

describe('agent snapshots', () => {
  it('expands desk-mcp compact tables into rows, at any depth', () => {
    const compact = {
      levels: {
        columns: ['name', 'value'],
        rows: [
          ['ath', 126000],
          ['sma200', 98000],
        ],
        total_rows: 2,
      },
      note: 'x',
    }
    expect(expandCompact(compact)).toEqual({
      levels: [
        { name: 'ath', value: 126000 },
        { name: 'sma200', value: 98000 },
      ],
      note: 'x',
    })
  })

  it('reads a tool result into tables, values and provenance', () => {
    const view = snapshotView({
      as_of: '2026-11-02',
      sources: ['coinmetrics candles_daily:BTC'],
      data: {
        current: { day: 926, multiple: 1.18 },
        cycles: { columns: ['cycle', 'multiple'], rows: [['2017', 5.4]], total_rows: 1 },
      },
    })
    expect(view.asOf).toBe('2026-11-02')
    expect(view.sources).toEqual(['coinmetrics candles_daily:BTC'])
    expect(view.error).toBeNull()
    expect(view.view.parts).toEqual([
      { name: 'cycles', columns: ['cycle', 'multiple'], rows: [{ cycle: '2017', multiple: 5.4 }] },
    ])
    expect(view.view.values).toEqual([
      ['current.day', 926],
      ['current.multiple', 1.18],
    ])
  })

  it('shows a bare record as one row, and a failed call as its error', () => {
    const one = snapshotView({
      as_of: '2026-11-02',
      sources: [],
      data: { current: 'uptrend', date: '2026-11-02' },
    })
    expect(one.view.parts[0].rows).toEqual([{ current: 'uptrend', date: '2026-11-02' }])
    const failed = snapshotView({ error: 'Error executing tool get_regime: unknown coin NOPE' })
    expect(failed.error).toMatch(/unknown coin/)
    expect(failed.view.parts).toEqual([])
  })
})
