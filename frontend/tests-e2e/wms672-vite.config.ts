import { defineConfig, mergeConfig } from 'vite'
import application from '../vite.config'

// Two testers share this checkout. Isolate Vite's optimized React module cache.
export default mergeConfig(application, defineConfig({
  cacheDir: 'node_modules/.vite-wms672',
  optimizeDeps: { include: ['react', 'react-dom/client', 'react/jsx-runtime'] },
}))
