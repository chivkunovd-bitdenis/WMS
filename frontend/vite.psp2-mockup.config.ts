import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// Отдельная статическая сборка кликабельного макета PSP-2: одна страница
// psp2-mockup.html + assets, относительные пути — открывается с любого адреса
// без сервера и API (fetch подменён внутри макета).
//
// Две подмены действуют только в этой сборке, продуктовый код не меняется:
// - иллюстрации базы знаний (≈12 МБ PNG) заменены пустой картинкой — раздел
//   в макете неактивен, а без подмены сборка весила бы 16 МБ;
// - логотип портала задан в продукте абсолютным путём «/portal-logo-*.png»,
//   на чужом адресе он ушёл бы в корень домена — в макете путь относительный.

const EMPTY_IMAGE = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
const LOGOS = ['portal-logo-ff.png', 'portal-logo-seller.png']

function psp2MockupAssets(): Plugin {
  return {
    name: 'psp2-mockup-assets',
    enforce: 'pre',
    load(id) {
      if (/[\\/]content[\\/]knowledge[\\/]images[\\/][^?]+\.(png|jpe?g|svg)(\?.*)?$/.test(id)) {
        return `export default ${JSON.stringify(EMPTY_IMAGE)}`
      }
      return null
    },
    transform(code, id) {
      if (id.endsWith('WmsBrandMark.tsx')) {
        return code.replace(/'\/portal-logo-/g, "'./portal-logo-")
      }
      return null
    },
    generateBundle() {
      for (const fileName of LOGOS) {
        this.emitFile({ type: 'asset', fileName, source: readFileSync(resolve(__dirname, 'public', fileName)) })
      }
    },
  }
}

export default defineConfig({
  plugins: [react(), psp2MockupAssets()],
  base: './',
  publicDir: false,
  build: {
    outDir: 'dist-psp2-mockup',
    emptyOutDir: true,
    chunkSizeWarningLimit: 4000,
    rollupOptions: {
      input: { psp2Mockup: 'psp2-mockup.html' },
    },
  },
})
