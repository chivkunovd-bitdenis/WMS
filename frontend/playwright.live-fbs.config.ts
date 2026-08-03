import { defineConfig, devices } from '@playwright/test'

// This config intentionally has no webServer and no E2E_MOCK_WB_* switches.
// `scripts/run-fbs-live-e2e.sh` starts an isolated docker-compose WMS API +
// WB emulator stack. Vite is used only as the browser shell because the old
// local Caddy override is absent; every /api request still reaches real WMS.
const webPort = Number(process.env.E2E_LIVE_WEB_PORT ?? 19173)
const apiUrl = process.env.E2E_LIVE_API_URL ?? 'http://127.0.0.1:19080'

export default defineConfig({
  testDir: './tests-e2e',
  testMatch: 'ff-fbs-live.spec.ts',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  workers: 1,
  use: {
    baseURL: process.env.E2E_LIVE_WEB_URL ?? `http://127.0.0.1:${webPort}`,
    trace: 'on-first-retry',
  },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
    env: {
      ...process.env,
      VITE_API_PROXY: apiUrl,
      E2E_SELLER_PATH_PREFIX: '/seller',
      VITE_SELLER_PORTAL_URL: `http://127.0.0.1:${webPort}/seller/`,
    },
    port: webPort,
    reuseExistingServer: false,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
