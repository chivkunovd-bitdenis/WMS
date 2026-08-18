const path = require('node:path');

const rootDir = path.resolve(__dirname, '../../../../../../');
const backendDir = path.join(rootDir, 'backend');
const frontendDir = path.join(rootDir, 'frontend');
const { defineConfig, devices } = require(path.join(frontendDir, 'node_modules/@playwright/test'));
const e2eApiPort = Number(process.env.E2E_API_PORT ?? 18136);
const e2eWebPort = Number(process.env.E2E_WEB_PORT ?? 18137);

module.exports = defineConfig({
  testDir: __dirname,
  timeout: 120_000,
  expect: { timeout: 12_000 },
  workers: 1,
  outputDir: path.join(__dirname, 'playwright-output'),
  use: {
    baseURL: `http://127.0.0.1:${e2eWebPort}`,
    trace: 'on',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `rm -f e2e-f03-browser-final-current.db && python3 -m uvicorn app.main:app --host 127.0.0.1 --port ${e2eApiPort}`,
      cwd: backendDir,
      env: {
        ...process.env,
        WMS_AUTO_CREATE_SCHEMA: '1',
        DATABASE_URL: 'sqlite+aiosqlite:///./e2e-f03-browser-final-current.db',
        JWT_SECRET_KEY: 'ci-jwt-secret-key-minimum-32-characters-long',
        E2E_MOCK_WB_CARDS: '1',
        E2E_MOCK_WB_SUPPLIES: '1',
        E2E_MOCK_WB_WAREHOUSES: '1',
      },
      port: e2eApiPort,
      reuseExistingServer: false,
    },
    {
      command: `npm run dev -- --host 0.0.0.0 --port ${e2eWebPort}`,
      cwd: frontendDir,
      env: {
        ...process.env,
        VITE_API_PROXY: `http://127.0.0.1:${e2eApiPort}`,
        E2E_SELLER_PATH_PREFIX: '/seller',
        VITE_SELLER_PORTAL_URL: `http://127.0.0.1:${e2eWebPort}/seller/`,
      },
      port: e2eWebPort,
      reuseExistingServer: false,
    },
  ],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
