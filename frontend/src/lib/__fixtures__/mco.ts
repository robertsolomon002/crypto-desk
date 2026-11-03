import type { McoVideo } from '@/lib/queries'

// A made-up MCO video for the frontend tests (no real MCO content in the repo, Decision 6).

export const FAKE_VIDEO: McoVideo = {
  video_id: 'fakeVideo01',
  title: 'Fake title about ETH',
  url: 'https://www.youtube.com/watch?v=fakeVideo01',
  published_at: '2026-10-02T13:00:00Z',
  low_detail: false,
  model: 'gemini-3.5-flash-lite',
  prompt_version: 'mco_extract_v2',
  summary: 'A made-up summary.',
  checks: [],
  coins: [
    {
      coin: 'ETH',
      bias: 'bearish',
      wave_position: 'wave B up',
      timeframe: 'days',
      key_levels: [{ price: 9, label: 'support box' }],
      scenarios: [
        {
          name: 'primary',
          color: 'yellow',
          bias: 'bearish',
          description: 'One more leg down.',
          levels: [{ price: 8, label: '161.8% extension' }],
          targets: [8, 7.5],
          invalidation: null,
          trigger: null,
        },
        {
          name: 'alternative',
          color: null,
          bias: 'bullish',
          description: 'The low is in.',
          levels: [{ price: 13, label: 'resistance' }],
          targets: [],
          invalidation: null,
          trigger: 'a break above $13',
        },
      ],
      extraction_confidence: 'high',
    },
    {
      coin: 'BTC',
      bias: 'neutral',
      wave_position: 'range',
      timeframe: 'weeks',
      key_levels: [],
      scenarios: [
        {
          name: 'primary',
          color: null,
          bias: 'neutral',
          description: 'Sideways.',
          levels: [],
          targets: [],
          invalidation: 90,
          trigger: null,
        },
      ],
      extraction_confidence: 'medium',
    },
  ],
}
