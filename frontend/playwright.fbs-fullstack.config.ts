import { defineConfig, devices } from "@playwright/test";

const webPort = Number(process.env.WMS_WEB_PORT ?? 25173);

export default defineConfig({
  testDir: "./tests-e2e",
  timeout: 480_000,
  expect: { timeout: 20_000 },
  retries: 0,
  workers: 1,
  outputDir: "test-results/fbs-fullstack",
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    viewport: { width: 1280, height: 720 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
