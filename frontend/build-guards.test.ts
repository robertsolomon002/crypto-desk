import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import type { ConfigEnv, UserConfig } from 'vite'
import { afterEach, describe, expect, it, vi } from 'vitest'

import viteConfig from './vite.config.ts'

// The Playwright-only fake sign-in (D39) must never reach a deployed build.
const read = (path: string) => readFileSync(resolve(import.meta.dirname, path), 'utf8')
const build = viteConfig as (env: ConfigEnv) => UserConfig
const ENV: ConfigEnv = { command: 'build', mode: 'production' }

describe('fake auth build guards', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('the deploy and CI workflows never set VITE_E2E_FAKE_AUTH', () => {
    const deploy = read('../.github/workflows/deploy-frontend.yml')
    expect(deploy).toContain('npm run build') // the right file was read
    expect(deploy).not.toContain('VITE_E2E_FAKE_AUTH')
    expect(read('../.github/workflows/ci.yml')).not.toContain('VITE_E2E_FAKE_AUTH')
  })

  it('only the Playwright web server sets it', () => {
    expect(read('playwright.config.ts')).toContain("VITE_E2E_FAKE_AUTH: '1'")
  })

  it('vite refuses a fake-auth build that points at a real API', () => {
    vi.stubEnv('VITE_E2E_FAKE_AUTH', '1')
    vi.stubEnv('VITE_API_BASE_URL', 'https://desk-api.example.run.app')
    expect(() => build(ENV)).toThrow(/Playwright builds/)
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:4173')
    expect(() => build(ENV)).not.toThrow()
  })
})
