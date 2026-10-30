import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { loadEnv, type Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

import { pagesHeadersFile, securityHeaders } from './src/lib/security-headers.ts'

// One .env at the repo root; only VITE_* variables reach the browser bundle.
const ENV_DIR = '..'

// `dist/_headers` for Cloudflare Pages (CSP and friends, D38)
function pagesHeaders(headers: Record<string, string>): Plugin {
  return {
    name: 'crypto-desk:pages-headers',
    apply: 'build',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: '_headers', source: pagesHeadersFile(headers) })
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // loadEnv also picks up VITE_* variables from the process environment (CI, deploy workflow)
  const env = loadEnv(mode, ENV_DIR, 'VITE_')
  const headers = securityHeaders({
    apiBaseUrl: env.VITE_API_BASE_URL,
    clerkPublishableKey: env.VITE_CLERK_PUBLISHABLE_KEY,
  })
  return {
    plugins: [react(), tailwindcss(), pagesHeaders(headers)],
    envDir: ENV_DIR,
    resolve: {
      alias: { '@': path.resolve(import.meta.dirname, './src') },
    },
    server: {
      // Local dev: the backend runs on :8000 (`uv run desk api serve`). No CSP here: the dev
      // server injects inline scripts for hot reload.
      proxy: { '/api': 'http://127.0.0.1:8000' },
    },
    // Same headers as production, so the Playwright smoke tests catch CSP violations
    preview: { headers },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
    },
  }
})
