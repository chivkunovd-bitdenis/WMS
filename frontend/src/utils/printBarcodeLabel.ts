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
    __WMS_PRINT_JOB_COUNT__?: number
    __WMS_PRINT_CLEANUP_EVENTS__?: string[]
  }
}

export type BarcodeLabelLayout = 'default' | 'storageCell' | 'internalBox'

export type BarcodeLabelPrintOptions = {
  title: string
  barcode: string
  barcodeDataUrl: string
  /** Физический размер этикетки (см. utils/labelSize.ts). Без него — прежнее поведение (авто-размер листа браузера). */
  labelSize?: LabelSize
  /** Ячейки печатаются на крупной складской этикетке, а не на товарном термоформате. */
  layout?: BarcodeLabelLayout
}

function labelPageHtml(options: BarcodeLabelPrintOptions, index: number, total: number): string {
  const { title, barcode, barcodeDataUrl } = options
  const safeTitle = escapeHtml(title)
  const safeBarcode = escapeHtml(barcode)
  const safeBarcodeDataUrl = escapeHtml(barcodeDataUrl)
  return `<section class="label${index + 1 < total ? ' label--next' : ''}" data-barcode="${safeBarcode}">
      <div class="wrap">
        <div class="title">${safeTitle}</div>
        <img class="barcode" src="${safeBarcodeDataUrl}" alt="barcode" />
        <div class="code">${safeBarcode}</div>
      </div>
    </section>`
}

/**
 * Одна печатная задача для одной или нескольких внутренних этикеток.
 * Массовая печать намеренно собирает все страницы в один iframe: термопринтер
 * получает непрерывную ленту, а не набор отдельных браузерных заданий.
 */
export function printBarcodeLabels(optionsList: BarcodeLabelPrintOptions[]): void {
  if (optionsList.length === 0) return
  const first = optionsList[0]!
  const { labelSize, layout = 'default' } = first
  if (optionsList.some((options) => options.labelSize?.id !== labelSize?.id || (options.layout ?? 'default') !== layout)) {
    throw new Error('Все этикетки в одной печати должны иметь одинаковый размер и макет.')
  }
  const pageStyle = layout === 'storageCell'
    ? `@page { margin: 4mm; }
      .wrap { min-height: calc(100vh - 8mm); padding: 2mm; box-sizing: border-box; }
      .title { font-size: 24pt; }
      .code { font-size: 18pt; }
      .barcode { width: 96%; max-width: 190mm; height: 48mm; object-fit: fill; }`
    : layout === 'internalBox' && labelSize
      ? `@page { size: ${labelSize.widthMm}mm ${labelSize.heightMm}mm; margin: 0; }
      html, body { width: ${labelSize.widthMm}mm; height: ${labelSize.heightMm}mm; }
      .label { width: ${labelSize.widthMm}mm; height: ${labelSize.heightMm}mm; box-sizing: border-box; }
      .label--next { break-after: page; page-break-after: always; }
      .wrap { width: 100%; height: 100%; box-sizing: border-box; padding: 1.5mm; display: grid; grid-template-rows: auto 1fr auto; gap: 1mm; justify-items: stretch; align-items: center; }
      .title { font-size: 13pt; font-weight: 800; text-align: center; }
      .code { font-size: 9pt; text-align: center; }
      .barcode { width: 100%; max-width: none; height: auto; max-height: none; display: block; image-rendering: pixelated; }`
    : labelSize
      ? `@page { size: ${labelSize.widthMm}mm ${labelSize.heightMm}mm; margin: 0; }
      html, body { width: ${labelSize.widthMm}mm; height: ${labelSize.heightMm}mm; }
      .wrap { width: 100%; height: 100%; box-sizing: border-box; padding: 2mm; }
      .barcode { width: auto; max-width: 90%; max-height: 55%; }`
      : `@page { margin: 10mm; }
        .barcode { width: 320px; height: auto; }`
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
    ${optionsList.map((options, index) => labelPageHtml(options, index, optionsList.length)).join('\n')}
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

  const cleanup = (reason: 'afterprint' | 'image-error') => {
    if (window.__WMS_CAPTURE_PRINT_HTML__) {
      window.__WMS_PRINT_CLEANUP_EVENTS__ = [
        ...(window.__WMS_PRINT_CLEANUP_EVENTS__ ?? []),
        reason,
      ]
    }
    try {
      document.body.removeChild(iframe)
    } catch {
      // ignore
    }
  }

  const printNow = () => {
    const w = iframe.contentWindow
    if (!w) {
      cleanup('image-error')
      return
    }
    try {
      w.focus()
    } catch {
      // ignore
    }
    setTimeout(() => {
      // Нельзя удалять iframe сразу после print(): системное окно предпросмотра
      // ещё читает data URL из этого документа. afterprint — единственный
      // успешный конец печати; до него источник этикетки обязан оставаться жив.
      w.addEventListener('afterprint', () => cleanup('afterprint'), { once: true })
      try {
        if (window.__WMS_CAPTURE_PRINT_HTML__) {
          window.__WMS_PRINT_JOB_COUNT__ = (window.__WMS_PRINT_JOB_COUNT__ ?? 0) + 1
        }
        w.print()
      } catch {
        cleanup('image-error')
      }
    }, 100)
  }

  iframe.srcdoc = html
  iframe.onload = () => {
    const doc = iframe.contentDocument
    const images = Array.from(doc?.querySelectorAll<HTMLImageElement>('img.barcode') ?? [])
    if (images.length === 0) {
      cleanup('image-error')
      return
    }
    Promise.all(images.map((image) => image.decode()))
      .then(printNow)
      .catch(() => cleanup('image-error'))
  }
}

/** Обратная совместимость для одиночной печати. */
export function printBarcodeLabel(options: BarcodeLabelPrintOptions): void {
  printBarcodeLabels([options])
}
