import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig, devices } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const backendDir = path.resolve(__dirname, '..', 'backend');

// Avoid collisions with locally running dev servers during development.
// e2e should start with a fresh backend DB and a dedicated Vite instance.
const reuse = false;
const e2eApiPort = 18000;
// Use a non-default port to avoid colliding with a locally running `npm run dev`.
const e2eWebPort = Number(process.env.E2E_WEB_PORT ?? 5174);

export default defineConfig({
  testDir: './tests-e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 2 : 0,
  // One API + shared sqlite file: parallel workers cause DB locks and flaky catalog writes.
  workers: 1,
  // Always hit the Playwright-managed Vite instance (not docker :15173/:15174) so API proxy → e2e API :18000.
  use: {
    baseURL: `http://127.0.0.1:${e2eWebPort}`,
    trace: 'on-first-retry',
  },
  webServer: [
    {
      // Fresh DB file: SQLAlchemy create_all does not migrate existing tables; stale e2e.db breaks schema.
      command: `rm -f e2e.db && python3 -m uvicorn app.main:app --host 127.0.0.1 --port ${e2eApiPort}`,
      cwd: backendDir,
      env: {
        ...process.env,
        WMS_AUTO_CREATE_SCHEMA: '1',
        DATABASE_URL: 'sqlite+aiosqlite:///./e2e.db',
        JWT_SECRET_KEY: 'ci-jwt-secret-key-minimum-32-characters-long',
        E2E_MOCK_WB_CARDS: '1',
        E2E_MOCK_WB_SUPPLIES: '1',
        E2E_MOCK_WB_WAREHOUSES: '1',
      },
      port: e2eApiPort,
      reuseExistingServer: reuse,
    },
    {
      command: `npm run dev -- --host 0.0.0.0 --port ${e2eWebPort}`,
      env: {
        ...process.env,
        VITE_API_PROXY: `http://127.0.0.1:${e2eApiPort}`,
        E2E_SELLER_PATH_PREFIX: '/seller',
        // Keep seller on the same origin during e2e (no redirect to docker :15174).
        VITE_SELLER_PORTAL_URL: `http://127.0.0.1:${e2eWebPort}/seller/`,
      },
      port: e2eWebPort,
      reuseExistingServer: reuse,
    },
  ],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
