import { useState } from 'react'

// Dark-first (ROADMAP Section 8). The choice lives in localStorage; storage can be missing or
// throw (private windows, blocked site data), so every access is guarded. The class is applied
// in main.tsx before the first render because the CSP allows no inline script in index.html.

export type Theme = 'dark' | 'light'

export const THEME_KEY = 'desk.theme'

export function storedTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY)
    if (saved === 'dark' || saved === 'light') return saved
  } catch {
    // fall through to the system preference
  }
  try {
    if (window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light'
  } catch {
    // no matchMedia
  }
  return 'dark'
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    // the theme still applies for this visit
  }
  applyTheme(theme)
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(storedTheme)
  return [
    theme,
    (next) => {
      saveTheme(next)
      setTheme(next)
    },
  ]
}
