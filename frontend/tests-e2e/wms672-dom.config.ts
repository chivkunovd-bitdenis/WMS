import { defineConfig } from 'vitest/config'
export default defineConfig({
  esbuild: { jsx: 'automatic' },
  test: { environment: 'jsdom', include: ['tests-e2e/wms672-dom.test.tsx'],
    maxWorkers: 1, fileParallelism: false, testTimeout: 15000 },
})
