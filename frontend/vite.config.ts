import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxyTarget =
  // Docker compose exposes API on host port 18080 by default (see docker-compose.yml).
  // Using 8000 here often accidentally targets a different local uvicorn instance.
  process.env.VITE_API_PROXY ?? 'http://127.0.0.1:18080'

// In Docker, the app listens on 5173 inside the container but the browser uses the
// published host port (e.g. 15173). Without this, HMR may target :5173 and never
// connect — tab looks stuck / blank until timeout.
const devClientPortRaw = process.env.VITE_DEV_CLIENT_PORT?.trim()
const devClientPort =
  devClientPortRaw && /^\d+$/.test(devClientPortRaw)
    ? Number(devClientPortRaw)
    : undefined

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    ...(devClientPort !== undefined ? { hmr: { clientPort: devClientPort } } : {}),
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    rollupOptions: {
      input: {
        ff: 'index.html',
        seller: 'seller/index.html',
      },
    },
  },
})
