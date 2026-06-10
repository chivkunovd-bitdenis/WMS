import { EAC_MARK_DATA_URL } from './eacMarkSvg'
import {
  escapeLabelHtml,
  productLabelVariantLines,
  resolveProductLabelArticle,
  truncateProductLabelName,
} from './productLabelText'
import { renderBarcodeDataUrl } from './renderBarcodeDataUrl'

export type ProductThermalLabelData = {
  product_name: string
  sku_code: string
  wb_vendor_code?: string | null
  wb_size?: string | null
  wb_color?: string | null
  barcode: string
}

const LABEL_CSS = `
  @page { size: 58mm 40mm; margin: 0; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body { font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; }
  .label {
    width: 58mm;
    height: 40mm;
    padding: 1.6mm 1.8mm 1.2mm;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    page-break-after: always;
    break-after: page;
  }
  .label:last-child { page-break-after: auto; break-after: auto; }
  .head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1.2mm;
    min-height: 14mm;
    flex: 0 0 auto;
  }
  .text { flex: 1 1 auto; min-width: 0; line-height: 1.22; font-size: 7.2pt; }
  .name {
    font-size: 7.6pt;
    font-weight: 400;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin: 0 0 0.6mm;
  }
  .meta { margin: 0; }
  .eac {
    flex: 0 0 9mm;
    width: 9mm;
    height: 11.5mm;
    object-fit: contain;
  }
  .barcode-wrap {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-end;
    min-height: 0;
    padding-top: 0.4mm;
  }
  .barcode-wrap img {
    width: 52mm;
    max-width: 100%;
    height: auto;
    max-height: 17mm;
    object-fit: contain;
    display: block;
  }
  .digits {
    margin: 0.5mm 0 0;
    font-size: 8.5pt;
    letter-spacing: 0.04em;
    text-align: center;
    font-family: Arial, Helvetica, sans-serif;
  }
`

function buildLabelHtml(data: ProductThermalLabelData, barcodeDataUrl: string): string {
  const name = escapeLabelHtml(truncateProductLabelName(data.product_name))
  const article = escapeLabelHtml(resolveProductLabelArticle(data))
  const barcode = escapeLabelHtml(data.barcode.trim())
  const variantLines = productLabelVariantLines(data)
    .map((line) => `<p class="meta">${escapeLabelHtml(line)}</p>`)
    .join('')
  return `<section class="label" data-testid="product-thermal-label">
  <div class="head">
    <div class="text">
      <p class="name" title="${name}">${name}</p>
      <p class="meta">Артикул: ${article}</p>
      ${variantLines}
    </div>
    <img class="eac" src="${EAC_MARK_DATA_URL}" alt="EAC" />
  </div>
  <div class="barcode-wrap">
    <img id="barcode" src="${barcodeDataUrl}" alt="barcode" />
    <p class="digits">${barcode}</p>
  </div>
</section>`
}

export function buildProductThermalLabelDocument(
  data: ProductThermalLabelData,
  quantity: number,
  barcodeDataUrl: string,
): string {
  const copies = Math.max(1, Math.min(999, Math.floor(quantity)))
  const labels = Array.from({ length: copies }, () => buildLabelHtml(data, barcodeDataUrl)).join('')
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Этикетка товара</title>
    <style>${LABEL_CSS}</style>
  </head>
  <body>${labels}</body>
</html>`
}

export function printProductThermalLabels(data: ProductThermalLabelData, quantity: number): void {
  const barcode = data.barcode.trim()
  if (!barcode) {
    throw new Error('У товара нет штрихкода для печати.')
  }
  const barcodeDataUrl = renderBarcodeDataUrl(barcode, { variant: 'thermal58' })
  const html = buildProductThermalLabelDocument(data, quantity, barcodeDataUrl)

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
    const imgs = doc?.querySelectorAll('img') ?? []
    if (imgs.length === 0) {
      printNow()
      return
    }
    let pending = imgs.length
    const done = () => {
      pending -= 1
      if (pending <= 0) {
        printNow()
      }
    }
    imgs.forEach((img) => {
      const el = img as HTMLImageElement
      if (el.complete) {
        done()
        return
      }
      el.addEventListener('load', done, { once: true })
      el.addEventListener('error', done, { once: true })
    })
  }
}
