import { defineConfig } from '../../../../../frontend/node_modules/vite/dist/node/index.js'
import react from '../../../../../frontend/node_modules/@vitejs/plugin-react/dist/index.js'
import { resolve } from 'node:path'
// Only a test entry point. URL parsing and UI belong to the real FBS screen.
export default defineConfig({
  root: resolve(import.meta.dirname, '../../../../../frontend'),
  cacheDir: resolve(import.meta.dirname, 'vite-cache'),
  optimizeDeps: { include: ['bwip-js'] },
  plugins: [react(), {
    name: 'wms652-critical-entry',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url?.split('?')[0] === '/app/ff/fbs') req.url = '/tests-e2e/wms652-critical/index.html'
        next()
      })
    },
  }],
  server: { host: '127.0.0.1', port: 16676, strictPort: true },
})
