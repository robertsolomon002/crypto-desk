import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App.tsx'
import './index.css'
import { applyTheme, storedTheme } from './lib/theme'

// Before the first render, so there is no light flash (the CSP forbids an inline script).
applyTheme(storedTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
