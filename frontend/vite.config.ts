import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxyTarget =
  // Docker compose exposes API on host port 18080 by default (see docker-compose.yml).
  // Using 8000 here often accidentally targets a different local uvicorn instance.
  process.env.VITE_API_PROXY ?? 'http://127.0.0.1:18080'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
