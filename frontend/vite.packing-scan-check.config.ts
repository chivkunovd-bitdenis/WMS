import { defineConfig } from 'vite'

export default defineConfig({
  base: './',
  publicDir: false,
  build: {
    outDir: 'dist-packing-scan-check',
    emptyOutDir: true,
    rollupOptions: { input: 'packing-scan-check.html' },
  },
})
