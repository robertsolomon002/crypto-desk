import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  clearKey,
  detectProvider,
  KEY_STORAGE,
  keyHeader,
  keyProblem,
  loadKey,
  maskKey,
  saveKey,
} from './keys'

const OR_KEY = 'sk-or-v1-0123456789abcdef0123456789abcdef'
const ANT_KEY = 'sk-ant-api03-0123456789abcdef0123456789'
const OAI_KEY = 'sk-proj-0123456789abcdef0123456789abcd'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('key storage', () => {
  it('round-trips a key with its default model, trimmed', () => {
    expect(
      saveKey({ provider: 'openrouter', key: `  ${OR_KEY}\n`, model: ' openai/gpt-5-nano ' }),
    ).toBe(true)
    expect(JSON.parse(localStorage.getItem(KEY_STORAGE)!)).toEqual({
      provider: 'openrouter',
      key: OR_KEY,
      model: 'openai/gpt-5-nano',
    })
    expect(loadKey()).toEqual({ provider: 'openrouter', key: OR_KEY, model: 'openai/gpt-5-nano' })
  })

  it('stores an empty model as null (the provider default)', () => {
    saveKey({ provider: 'anthropic', key: ANT_KEY, model: '  ' })
    expect(loadKey()?.model).toBeNull()
  })

  it('forgets the key', () => {
    saveKey({ provider: 'openai', key: OAI_KEY, model: null })
    clearKey()
    expect(loadKey()).toBeNull()
    expect(localStorage.getItem(KEY_STORAGE)).toBeNull()
  })

  it('ignores corrupt, old or tampered values', () => {
    for (const raw of [
      'not json',
      'null',
      '[]',
      JSON.stringify({ provider: 'gemini', key: OR_KEY }),
      JSON.stringify({ provider: 'openrouter', key: 42 }),
      JSON.stringify({ provider: 'openrouter', key: ANT_KEY }), // wrong provider
      JSON.stringify({ provider: 'openrouter', key: 'sk-or-short' }),
    ]) {
      localStorage.setItem(KEY_STORAGE, raw)
      expect(loadKey()).toBeNull()
    }
  })

  it('survives storage that throws (private windows, blocked site data)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied')
    })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('denied')
    })
    expect(loadKey()).toBeNull()
    expect(saveKey({ provider: 'openrouter', key: OR_KEY, model: null })).toBe(false)
    expect(() => clearKey()).not.toThrow()
  })

  it('stores nothing but the one key record', () => {
    saveKey({ provider: 'openrouter', key: OR_KEY, model: null })
    expect(Object.keys(localStorage)).toEqual([KEY_STORAGE])
  })
})

describe('key checks', () => {
  it('detects the provider from the prefix', () => {
    expect(detectProvider(OR_KEY)).toBe('openrouter')
    expect(detectProvider(ANT_KEY)).toBe('anthropic')
    expect(detectProvider(OAI_KEY)).toBe('openai')
    expect(detectProvider('AIza123')).toBeNull()
  })

  it('explains what is wrong with a pasted key', () => {
    expect(keyProblem('openrouter', OR_KEY)).toBeNull()
    expect(keyProblem('openrouter', '')).toBe('Paste your key first.')
    expect(keyProblem('openrouter', 'sk-or-v1 0123456789abcdef0123')).toMatch(/spaces/)
    expect(keyProblem('openrouter', 'sk-or-v1-x')).toMatch(/full key/)
    expect(keyProblem('openrouter', ANT_KEY)).toBe(
      'This looks like an Anthropic key. Pick Anthropic above.',
    )
    expect(keyProblem('openai', OR_KEY)).toBe(
      'This looks like an OpenRouter key. Pick OpenRouter above.',
    )
    expect(keyProblem('anthropic', 'AIza0123456789abcdef0123456789')).toBe(
      'Anthropic keys start with "sk-ant-".',
    )
  })

  it('masks a key to its prefix and last 4 characters', () => {
    expect(maskKey(OR_KEY)).toBe('sk-or-v1-…cdef')
    expect(maskKey(ANT_KEY)).toBe('sk-ant-…6789')
    expect(maskKey(OAI_KEY)).not.toContain('0123456789')
  })

  it('builds the X-LLM-Key header only when there is a key', () => {
    expect(keyHeader(null)).toEqual({})
    expect(keyHeader({ provider: 'openrouter', key: OR_KEY, model: null })).toEqual({
      'X-LLM-Key': OR_KEY,
    })
  })
})
