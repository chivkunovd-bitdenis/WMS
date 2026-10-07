import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  root: new URL('../../..', import.meta.url).pathname,
  plugins: [react(), {
    name: 'native-print-proof-entry',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url?.split('?')[0] === '/app/ff/fbs') {
          req.url = '/tests-e2e/native-print-proof/index.html'
        }
        next()
      })
    },
  }],
  server: {
    host: '127.0.0.1',
    port: 16696,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:16692',
        changeOrigin: true,
        rewrite: (path) => `/proxy${path.slice(4)}`,
      },
    },
  },
})
