import { expect, test, type Page } from '@playwright/test'

import { DESK_SIGNAL, DESK_STREAM } from '../src/lib/__fixtures__/desk.ts'
import { ME, mockApi } from './fixtures.ts'

// Agent tab smoke tests at 1440 and 390 px, with the chat stream mocked (the real one is tested
// in the backend with fake models, D45).

const OR_KEY = 'sk-or-v1-0123456789abcdef0123456789abcdef'
const AGENT_ME = { ...ME, features: { ...ME.features, agent: true } }
const env = (data: unknown) => ({ as_of: '2026-11-02', sources: [], data })

const MODELS = env([
  {
    id: 'openrouter',
    label: 'OpenRouter',
    recommended: true,
    default: 'anthropic/claude-haiku-5.5',
    choices: ['anthropic/claude-haiku-5.5', 'openai/gpt-5-mini'],
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    recommended: false,
    default: 'claude-haiku-5-5',
    choices: [],
  },
  { id: 'openai', label: 'OpenAI', recommended: false, default: 'gpt-6-luna', choices: [] },
])

const sse = (events: [string, unknown][]) =>
  events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join('')

const STREAM = sse([
  [
    'conversation',
    { id: 12, title: 'Where is BTC in its cycle vs 2017?', model: 'm', server_key: false },
  ],
  [
    'tool_start',
    { call_id: 'c1', name: 'get_cycle_comparison', args: { coin: 'BTC', mode: 'halving' } },
  ],
  [
    'tool_end',
    {
      call_id: 'c1',
      name: 'get_cycle_comparison',
      snapshot_id: 7,
      ok: true,
      preview: '{"as_of":"2026-11-02","sources":["coinmetrics"],"data":{"cycles":',
    },
  ],
  [
    'token',
    { text: '**BTC is 1.18x its anchor** on day 926.\n\n| Cycle | Multiple |\n|---|---|\n' },
  ],
  ['token', { text: '| 2017 | 5.4x |\n| 2025 | 1.18x |\n\n<img src=x onerror=alert(1)>' }],
  [
    'done',
    {
      message_id: 2,
      model: 'anthropic/claude-haiku-5.5',
      tokens_in: 17000,
      tokens_out: 2000,
      cost_usd: null,
      tool_calls: 1,
      limited: false,
      truncated: false,
    },
  ],
])

const SNAPSHOT = {
  id: 7,
  conversation_id: 12,
  tool: 'get_cycle_comparison',
  args: { coin: 'BTC', mode: 'halving' },
  result: {
    as_of: '2026-11-02',
    sources: ['coinmetrics candles_daily:BTC'],
    data: {
      cycles: {
        columns: ['cycle', 'multiple', 'drawdown'],
        rows: [
          ['2017', 5.4, -0.82],
          ['2025', 1.18, -0.385],
        ],
        total_rows: 2,
      },
    },
  },
  as_of: '2026-11-02T00:00:00Z',
  created_at: '2026-11-03T15:00:00Z',
}

async function mock(page: Page, { key = true } = {}) {
  if (key)
    await page.addInitScript((k) => {
      localStorage.setItem(
        'desk.llm.v1',
        JSON.stringify({ provider: 'openrouter', key: k, model: null }),
      )
    }, OR_KEY)
  await mockApi(page, {
    '/api/me': AGENT_ME,
    '/api/agent/models': MODELS,
    '/api/agent/conversations': [],
    '/api/agent/snapshots/7': SNAPSHOT,
    '/api/data/tables': env([]),
  })
  const seen: { key: string | undefined; body: unknown }[] = []
  await page.route('**/api/agent/chat', (route) => {
    seen.push({ key: route.request().headers()['x-llm-key'], body: route.request().postDataJSON() })
    return route.fulfill({ body: STREAM, contentType: 'text/event-stream' })
  })
  return seen
}

test('ask, see the tool card, and open its exact data', async ({ page }) => {
  const dialogs: string[] = []
  page.on('dialog', (d) => {
    dialogs.push(d.message())
    void d.dismiss()
  })
  const seen = await mock(page)
  await page.goto('/agent')
  await expect(page.getByRole('heading', { name: 'Agent', level: 1 })).toBeVisible()
  await page.getByRole('button', { name: 'Where is BTC in its cycle vs 2017?' }).click()

  const answer = page.getByRole('article', { name: 'Answer' })
  await expect(answer.getByTestId('data-used')).toContainText('Cycle comparison (as of 2026-11-02)')
  await expect(answer.getByTestId('tool-card')).toContainText('BTC · mode halving · latest data')
  await expect(answer.getByRole('table')).toBeVisible()
  await expect(answer.locator('img')).toHaveCount(0)
  await expect(page).toHaveURL(/\/agent\?c=12/)
  expect(seen).toHaveLength(1)
  expect(seen[0].key).toBe(OR_KEY)
  expect(seen[0].body).toMatchObject({
    provider: 'openrouter',
    model: 'anthropic/claude-haiku-5.5',
  })
  expect(JSON.stringify(seen[0].body)).not.toContain(OR_KEY)

  await answer
    .getByTestId('tool-card')
    .getByRole('link', { name: /View data/ })
    .click()
  await expect(page).toHaveURL(/\/data\?snapshot=7/)
  await expect(page.getByRole('heading', { name: /Cycle comparison/ })).toBeVisible()
  const grid = page.getByTestId('data-grid')
  await expect(grid.getByRole('cell', { name: '5.4', exact: true })).toBeVisible()
  await expect(page.getByText('Sources: coinmetrics candles_daily:BTC')).toBeVisible()
  expect(dialogs).toEqual([])
})

test('without a key a friend is sent to Settings', async ({ page }) => {
  await mock(page, { key: false })
  await page.goto('/agent')
  await expect(page.getByText('Add your AI key to chat')).toBeVisible()
  await page.getByRole('link', { name: /Set up a key/ }).click()
  await expect(page).toHaveURL(/\/settings/)
})

test('the chat box stays usable on a phone', async ({ page, viewport }) => {
  await mock(page)
  await page.goto('/agent')
  const box = page.getByRole('textbox', { name: 'Ask the agent' })
  await box.fill('Is SOL above its 20-week band?')
  await box.press('Enter')
  await expect(page.getByTestId('data-used')).toBeVisible()
  // Nothing scrolls sideways at either width.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
  if ((viewport?.width ?? 1440) < 1024) {
    await page.getByRole('button', { name: 'Conversations' }).click()
    await expect(page.getByRole('button', { name: 'New chat' })).toBeVisible()
  }
})

test('ask the desk: stages, signal and the full run in the Data tab', async ({
  page,
  viewport,
}) => {
  const dialogs: string[] = []
  page.on('dialog', (d) => {
    dialogs.push(d.message())
    void d.dismiss()
  })
  await mock(page)
  await mockApi(page, {
    '/api/me': AGENT_ME,
    '/api/agent/models': MODELS,
    '/api/agent/conversations': [],
    '/api/data/tables': env([]),
    '/api/agent/desk/estimate': env({
      provider: 'openrouter',
      model: 'anthropic/claude-haiku-5.5',
      model_calls: 11,
      tokens_in: 49000,
      tokens_out: 4000,
      cost_usd: null,
      nodes: [],
    }),
    '/api/agent/snapshots/40': {
      ...SNAPSHOT,
      id: 40,
      tool: 'desk_run',
      args: { coin: 'SOL' },
      result: { coin: 'SOL', status: 'valid', signal: DESK_SIGNAL },
    },
  })
  const seen: unknown[] = []
  await page.route('**/api/agent/desk', (route) => {
    seen.push(route.request().postDataJSON())
    return route.fulfill({ body: sse(DESK_STREAM), contentType: 'text/event-stream' })
  })
  await page.goto('/agent')
  await page.getByRole('button', { name: 'Ask the desk' }).click()
  await page.getByRole('combobox', { name: 'Coin for the desk' }).selectOption('SOL')
  await expect(page.getByTestId('desk-estimate')).toContainText('About 11 model calls')
  await page.getByRole('button', { name: /Run the desk/ }).click()

  const run = page.getByTestId('desk-run')
  await expect(run.getByTestId('desk-validation')).toHaveText('Validator: passed after one retry')
  await expect(run.getByTestId('desk-signal')).toContainText('Lean long SOL')
  await expect(run.getByTestId('desk-node-context')).toContainText('Report unavailable')
  await expect(run.getByTestId('desk-node-bear_rebut')).toContainText('bear rebuttal point')
  await expect(run.locator('img')).toHaveCount(0)
  await expect(page).toHaveURL(/\/agent\?c=30/)
  expect(seen).toEqual([
    { coin: 'SOL', provider: 'openrouter', model: 'anthropic/claude-haiku-5.5' },
  ])

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
  if ((viewport?.width ?? 1440) >= 768) {
    // Analysts sit side by side on wide screens.
    const a = await run.getByTestId('desk-node-technical').boundingBox()
    const b = await run.getByTestId('desk-node-context').boundingBox()
    expect(a && b && Math.abs(a.y - b.y) < 2).toBe(true)
  }

  await run.getByRole('link', { name: /View the full run/ }).click()
  await expect(page).toHaveURL(/\/data\?snapshot=40/)
  await expect(page.getByRole('heading', { name: /Desk run/ })).toBeVisible()
  expect(dialogs).toEqual([])
})
