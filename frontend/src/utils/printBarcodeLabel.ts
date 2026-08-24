import type { LabelSize } from './labelSize'

/** Print a CODE128 label (58×40 workflow — same iframe pattern as catalog cell labels). */
function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

declare global {
  interface Window {
    __WMS_CAPTURE_PRINT_HTML__?: boolean
    __WMS_LAST_PRINT_HTML__?: string
  }
}

export function printBarcodeLabel(options: {
  title: string
  barcode: string
  barcodeDataUrl: string
  /** Физический размер этикетки (см. utils/labelSize.ts). Без него — прежнее поведение (авто-размер листа браузера). */
  labelSize?: LabelSize
  /** Ячейки печатаются на крупной складской этикетке, а не на товарном термоформате. */
  layout?: 'default' | 'storageCell'
}): void {
  const { title, barcode, barcodeDataUrl, labelSize, layout = 'default' } = options
  const safeTitle = escapeHtml(title)
  const safeBarcode = escapeHtml(barcode)
  const safeBarcodeDataUrl = escapeHtml(barcodeDataUrl)
  const pageStyle = layout === 'storageCell'
    ? `@page { margin: 4mm; }
      .wrap { min-height: calc(100vh - 8mm); padding: 2mm; box-sizing: border-box; }
      .title { font-size: 24pt; }
      .code { font-size: 18pt; }
      img { width: 96%; max-width: 190mm; height: 48mm; object-fit: fill; }`
    : labelSize
      ? `@page { size: ${labelSize.widthMm}mm ${labelSize.heightMm}mm; margin: 0; }
      html, body { width: ${labelSize.widthMm}mm; height: ${labelSize.heightMm}mm; }
      .wrap { width: 100%; height: 100%; box-sizing: border-box; padding: 2mm; }
      img { width: auto; max-width: 90%; max-height: 55%; }`
      : `@page { margin: 10mm; }
        img { width: 320px; height: auto; }`
  const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Print barcode</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 0; margin: 0; }
      .wrap { display: grid; gap: 8px; justify-items: center; align-content: center; }
      .title { font-size: 14px; font-weight: 700; text-align: center; }
      .code { font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; text-align: center; word-break: break-all; }
      ${pageStyle}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="title">${safeTitle}</div>
      <img id="barcode" src="${safeBarcodeDataUrl}" alt="barcode" />
      <div class="code">${safeBarcode}</div>
    </div>
  </body>
</html>`

  if (window.__WMS_CAPTURE_PRINT_HTML__) {
    window.__WMS_LAST_PRINT_HTML__ = html
  }

  const iframe = document.createElement('iframe')
  iframe.setAttribute('aria-hidden', 'true')
  iframe.style.position = 'fixed'
  iframe.style.right = '0'
  iframe.style.bottom = '0'
  iframe.style.width = '0'
  iframe.style.height = '0'
  iframe.style.border = '0'
  document.body.appendChild(iframe)

  const cleanup = () => {
    try {
      document.body.removeChild(iframe)
    } catch {
      // ignore
    }
  }

  const printNow = () => {
    const w = iframe.contentWindow
    if (!w) {
      cleanup()
      return
    }
    try {
      w.focus()
    } catch {
      // ignore
    }
    setTimeout(() => {
      try {
        w.print()
      } finally {
        setTimeout(cleanup, 500)
      }
    }, 100)
  }

  iframe.srcdoc = html
  iframe.onload = () => {
    const doc = iframe.contentDocument
    const img = doc?.getElementById('barcode') as HTMLImageElement | null
    if (!img) {
      printNow()
      return
    }
    if (img.complete) {
      printNow()
      return
    }
    img.addEventListener('load', printNow, { once: true })
    img.addEventListener('error', printNow, { once: true })
  }
}
