import { afterEach, describe, expect, it, vi } from 'vitest'

import { applyTheme, saveTheme, storedTheme, THEME_KEY } from './theme'

describe('theme', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    localStorage.clear()
    document.documentElement.className = ''
  })

  it('defaults to dark', () => {
    expect(storedTheme()).toBe('dark')
  })

  it('follows a light system preference', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('light') }))
    expect(storedTheme()).toBe('light')
  })

  it('prefers the saved choice and applies it', () => {
    saveTheme('light')
    expect(localStorage.getItem(THEME_KEY)).toBe('light')
    expect(storedTheme()).toBe('light')
    expect(document.documentElement).not.toHaveClass('dark')
    applyTheme('dark')
    expect(document.documentElement).toHaveClass('dark')
  })

  it('still works when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(storedTheme()).toBe('dark')
    expect(() => saveTheme('light')).not.toThrow()
    expect(document.documentElement).not.toHaveClass('dark')
  })
})
