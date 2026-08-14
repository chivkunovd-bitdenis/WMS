import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.E2E_WEB_ORIGIN ?? 'https://web-production-9e7c1.up.railway.app'

export default defineConfig({
  testDir: './tests-e2e',
  timeout: 180_000,
  expect: { timeout: 20_000 },
  retries: 0,
  workers: 1,
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
