import { useCallback, useState } from 'react'

// The friend's own LLM key (Decision 2, Section 3.6). It lives only in this browser's
// localStorage and is sent only in the `X-LLM-Key` header of the requests that need it (the key
// test now, the agent from v1.1), never with every API call. The backend never stores or logs it.
// Storage can be missing or throw (private windows, blocked site data), so every access is
// guarded, and a stored value is validated field by field before use.

export type Provider = 'openrouter' | 'anthropic' | 'openai'

export interface LlmKey {
  provider: Provider
  key: string
  model: string | null // the default model; null = the provider's default
}

export const KEY_STORAGE = 'desk.llm.v1'
const PROVIDERS: readonly Provider[] = ['openrouter', 'anthropic', 'openai']

export const LABEL: Record<Provider, string> = {
  openrouter: 'OpenRouter',
  anthropic: 'Anthropic',
  openai: 'OpenAI',
}

/** The provider a key's prefix points to (OpenRouter `sk-or-`, Anthropic `sk-ant-`, OpenAI `sk-`). */
export function detectProvider(key: string): Provider | null {
  if (key.startsWith('sk-or-')) return 'openrouter'
  if (key.startsWith('sk-ant-')) return 'anthropic'
  if (key.startsWith('sk-')) return 'openai'
  return null
}

const PREFIX: Record<Provider, string> = {
  openrouter: 'sk-or-',
  anthropic: 'sk-ant-',
  openai: 'sk-',
}

/** A problem with the pasted key, in plain words, or null when it looks right. */
export function keyProblem(provider: Provider, raw: string): string | null {
  const key = raw.trim()
  if (!key) return 'Paste your key first.'
  if (/\s/.test(key)) return 'The key has spaces or line breaks in it. Copy it again.'
  if (key.length < 20 || key.length > 300) return "That doesn't look like a full key."
  const detected = detectProvider(key)
  if (detected === null) return `${LABEL[provider]} keys start with "${PREFIX[provider]}".`
  if (detected !== provider)
    return `This looks like an ${LABEL[detected]} key. Pick ${LABEL[detected]} above.`
  return null
}

function parse(raw: string | null): LlmKey | null {
  if (!raw) return null
  try {
    const v = JSON.parse(raw) as Partial<LlmKey>
    if (!v || typeof v !== 'object') return null
    if (!PROVIDERS.includes(v.provider as Provider)) return null
    if (typeof v.key !== 'string' || keyProblem(v.provider as Provider, v.key)) return null
    const model = typeof v.model === 'string' && v.model.trim() ? v.model.trim() : null
    return { provider: v.provider as Provider, key: v.key.trim(), model }
  } catch {
    return null
  }
}

export function loadKey(): LlmKey | null {
  try {
    return parse(localStorage.getItem(KEY_STORAGE))
  } catch {
    return null
  }
}

/** Saves the key; false if this browser won't store it (it then lasts only for this visit). */
export function saveKey(value: LlmKey): boolean {
  const clean: LlmKey = {
    provider: value.provider,
    key: value.key.trim(),
    model: value.model?.trim() || null,
  }
  try {
    localStorage.setItem(KEY_STORAGE, JSON.stringify(clean))
    return true
  } catch {
    return false
  }
}

export function clearKey(): void {
  try {
    localStorage.removeItem(KEY_STORAGE)
  } catch {
    // nothing stored
  }
}

/** "sk-or-v1-…9f3a": enough to recognize the key without showing it. */
export function maskKey(key: string): string {
  const k = key.trim()
  const head = k.slice(0, { openrouter: 9, anthropic: 7, openai: 3 }[detectProvider(k) ?? 'openai'])
  return `${head}…${k.slice(-4)}`
}

/** The header for requests that need the key, or none. */
export function keyHeader(value: LlmKey | null): Record<string, string> {
  return value ? { 'X-LLM-Key': value.key } : {}
}

export function useStoredKey(): [LlmKey | null, (value: LlmKey | null) => boolean] {
  const [value, setValue] = useState<LlmKey | null>(loadKey)
  const update = useCallback((next: LlmKey | null) => {
    let stored = true
    if (next) stored = saveKey(next)
    else clearKey()
    setValue(next ? { ...next, key: next.key.trim(), model: next.model?.trim() || null } : null)
    return stored
  }, [])
  return [value, update]
}
