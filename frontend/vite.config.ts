import { defineConfig, type Plugin } from 'vite'
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

function sellerSpaFallback(): Plugin {
  const rewriteSellerHtml = (url: string | undefined) => {
    const path = (url ?? '').split('?')[0] ?? ''
    return path.startsWith('/seller/') && path !== '/seller/'
  }

  return {
    name: 'wms-seller-spa-fallback',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.method === 'GET' && rewriteSellerHtml(req.url)) {
          req.url = '/seller/index.html'
        }
        next()
      })
    },
    configurePreviewServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.method === 'GET' && rewriteSellerHtml(req.url)) {
          req.url = '/seller/index.html'
        }
        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), sellerSpaFallback()],
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
  // Тот же прокси на preview: без него продовую сборку нечем прогнать браузерными
  // тестами, и дефект, который живёт только в собранном бандле, уходит на прод.
  preview: {
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
