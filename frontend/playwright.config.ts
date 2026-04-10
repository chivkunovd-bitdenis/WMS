import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig, devices } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const backendDir = path.resolve(__dirname, '..', 'backend');

const reuse = !process.env.CI;
const e2eApiPort = 18000;

export default defineConfig({
  testDir: './tests-e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  webServer: [
    {
      command: `python3 -m uvicorn app.main:app --host 127.0.0.1 --port ${e2eApiPort}`,
      cwd: backendDir,
      env: {
        ...process.env,
        WMS_AUTO_CREATE_SCHEMA: '1',
        DATABASE_URL: 'sqlite+aiosqlite:///./e2e.db',
        JWT_SECRET_KEY: 'ci-jwt-secret-key-minimum-32-characters-long',
      },
      port: e2eApiPort,
      reuseExistingServer: reuse,
    },
    {
      command: 'npm run dev -- --host 0.0.0.0 --port 5173',
      env: {
        ...process.env,
        VITE_API_PROXY: `http://127.0.0.1:${e2eApiPort}`,
      },
      port: 5173,
      reuseExistingServer: reuse,
    },
  ],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
