import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
// Only a test entry point. URL parsing and UI belong to the real FBS screen.
export default defineConfig({
  root: resolve(import.meta.dirname, '../..'),
  plugins: [react(), {
    name: 'wms666-native-entry',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url?.split('?')[0] === '/app/ff/fbs') req.url = '/tests-e2e/wms652-critical/index.html'
        next()
      })
    },
  }],
  server: { host: '127.0.0.1', port: 16696, strictPort: true },
})
