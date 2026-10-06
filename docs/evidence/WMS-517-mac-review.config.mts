import { defineConfig } from 'vitest/config'
export default defineConfig({
  esbuild: { jsx: 'automatic' },
  test: {
    maxWorkers: 1,
    minWorkers: 1,
    environment: 'jsdom',
    environmentOptions: { jsdom: { url: 'https://wms.sellerfocus.pro/seller/honest-sign/withdrawals' } },
    include: ['docs/evidence/WMS-517-mac-review.test.tsx'],
    testTimeout: 15000,
  },
})
