import { expandLayoutTape } from './markingPrintPresets'
import {
  buildProductLabelSectionHtml,
  type ProductThermalLabelData,
} from './printProductThermalLabel'
import { escapeLabelHtml } from './productLabelText'
import type { PrintLayout } from './printTemplate'
import { renderBarcodeDataUrl } from './renderBarcodeDataUrl'

const TAPE_PAGE_CSS = `
  @page { size: 58mm 40mm; margin: 0; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body { font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; }
  .label {
    width: 58mm;
    height: 40mm;
    overflow: hidden;
    page-break-after: always;
    break-after: page;
  }
  .label:last-child { page-break-after: auto; break-after: auto; }
  .label--cz {
    padding: 1.5mm;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }
  .matrix img {
    width: 28mm;
    height: 28mm;
    object-fit: contain;
    display: block;
  }
  .tail {
    margin: 0.5mm 0 0;
    font-size: 5.5pt;
    text-align: center;
    word-break: break-all;
    line-height: 1.1;
    max-width: 54mm;
  }
  .label:not(.label--cz) {
    padding: 1.4mm 1.8mm 1mm;
    display: flex;
    flex-direction: column;
  }
  .barcode-wrap {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    margin-bottom: 0.8mm;
  }
  .barcode-wrap img {
    width: 52mm;
    max-width: 100%;
    height: auto;
    max-height: 14mm;
    object-fit: contain;
    display: block;
  }
  .digits {
    margin: 0.3mm 0 0;
    font-size: 8pt;
    letter-spacing: 0.04em;
    text-align: center;
    font-family: Arial, Helvetica, sans-serif;
    line-height: 1.1;
  }
  .body {
    flex: 1 1 auto;
    min-height: 0;
    line-height: 1.2;
    font-size: 6.8pt;
    display: flex;
    flex-direction: column;
    gap: 0.15mm;
  }
  .seller {
    margin: 0;
    font-size: 6.8pt;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .name {
    margin: 0;
    font-size: 7pt;
    font-weight: 400;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    text-overflow: ellipsis;
    word-break: break-word;
  }
  .meta { margin: 0; }
  .meta-composition {
    margin: 0;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    word-break: break-word;
  }
  .footer {
    flex: 0 0 auto;
    margin: 0.4mm 0 0;
    font-size: 6.4pt;
    text-align: left;
    line-height: 1.15;
  }
`

export function maskCisCode(cis: string): string {
  const t = cis.trim()
  if (t.length <= 12) {
    return t
  }
  return `…${t.slice(-12)}`
}

export async function renderDataMatrixDataUrl(cis: string): Promise<string> {
  const bwipjs = await import('bwip-js')
  const canvas = document.createElement('canvas')
  bwipjs.toCanvas(canvas, {
    bcid: 'datamatrix',
    text: cis,
    scale: 2,
    height: 12,
    includetext: false,
  })
  return canvas.toDataURL('image/png')
}

function buildCzLabelHtml(cis: string, matrixDataUrl: string): string {
  return `<section class="label label--cz" data-testid="marking-thermal-label" data-tape-block="cz">
  <div class="matrix"><img src="${matrixDataUrl}" alt="ЧЗ" /></div>
  <p class="tail">${escapeLabelHtml(maskCisCode(cis))}</p>
</section>`
}

export type MarkingTapeUnitInput = {
  cis: string
  productLabel?: ProductThermalLabelData | null
}

export type PrintMarkingCodeLabelsOptions = {
  layout?: PrintLayout
  duplicateCopies?: number
  productLabel?: ProductThermalLabelData | null
}

export function buildMarkingTapeDocument(
  sections: string[],
): string {
  const body = sections.join('')
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Честный знак</title>
    <style>${TAPE_PAGE_CSS}</style>
  </head>
  <body>${body}</body>
</html>`
}

/** @deprecated используйте buildMarkingTapeDocument */
export function buildMarkingLabelsDocument(
  labels: { cis: string; matrixDataUrl: string }[],
): string {
  const body = labels
    .map((l) => buildCzLabelHtml(l.cis, l.matrixDataUrl))
    .join('')
  return buildMarkingTapeDocument([body])
}

export function expandCodesWithDuplicates(codes: string[], duplicateCopies: number): string[] {
  const layout: PrintLayout = {
    units: [{ block: 'cz', copies: duplicateCopies === 2 ? 2 : 1 }],
  }
  return expandLayoutTape(codes, layout).map((item) => item.cis)
}

function resolveLayout(options: PrintMarkingCodeLabelsOptions): PrintLayout {
  if (options.layout) {
    return options.layout
  }
  const copies = options.duplicateCopies === 2 ? 2 : 1
  return { units: [{ block: 'cz', copies }] }
}

function resolveProductLabel(
  unit: MarkingTapeUnitInput,
  fallback?: ProductThermalLabelData | null,
): ProductThermalLabelData {
  if (unit.productLabel?.barcode?.trim()) {
    return unit.productLabel
  }
  if (fallback?.barcode?.trim()) {
    return fallback
  }
  const sku = unit.productLabel?.sku_code ?? fallback?.sku_code ?? maskCisCode(unit.cis)
  const barcode = sku.trim()
  return {
    product_name: unit.productLabel?.product_name ?? fallback?.product_name ?? sku,
    sku_code: sku,
    barcode,
    wb_vendor_code: unit.productLabel?.wb_vendor_code ?? fallback?.wb_vendor_code,
    wb_size: unit.productLabel?.wb_size ?? fallback?.wb_size,
    wb_color: unit.productLabel?.wb_color ?? fallback?.wb_color,
    wb_brand: unit.productLabel?.wb_brand ?? fallback?.wb_brand,
    wb_composition: unit.productLabel?.wb_composition ?? fallback?.wb_composition,
    seller_name: unit.productLabel?.seller_name ?? fallback?.seller_name,
  }
}

export async function printMarkingCodeTape(
  units: MarkingTapeUnitInput[],
  layout: PrintLayout,
  defaultProductLabel?: ProductThermalLabelData | null,
): Promise<void> {
  if (units.length === 0) {
    throw new Error('Нет КМ для печати.')
  }
  const codes = units.map((unit) => unit.cis)
  const tape = expandLayoutTape(codes, layout)
  const uniqueCis = [...new Set(codes)]
  const matrixByCis = new Map<string, string>()
  await Promise.all(
    uniqueCis.map(async (cis) => {
      matrixByCis.set(cis, await renderDataMatrixDataUrl(cis))
    }),
  )

  const barcodeBySku = new Map<string, string>()
  const sections: string[] = []
  for (const item of tape) {
    const unitInput = units[item.unitIndex]
    if (item.block === 'cz') {
      sections.push(buildCzLabelHtml(item.cis, matrixByCis.get(item.cis) ?? ''))
      continue
    }
    const product = resolveProductLabel(unitInput, defaultProductLabel)
    const barcode = product.barcode.trim()
    let barcodeDataUrl = barcodeBySku.get(barcode)
    if (!barcodeDataUrl) {
      barcodeDataUrl = renderBarcodeDataUrl(barcode, { variant: 'thermal58' })
      barcodeBySku.set(barcode, barcodeDataUrl)
    }
    const html = buildProductLabelSectionHtml(product, barcodeDataUrl)
    sections.push(html.replace('data-testid="product-thermal-label"', 'data-testid="product-thermal-label" data-tape-block="label"'))
  }

  const html = buildMarkingTapeDocument(sections)
  await printHtmlInIframe(html)
}

export async function printMarkingCodeLabels(
  codes: string[],
  duplicateCopiesOrOptions: number | PrintMarkingCodeLabelsOptions = 2,
): Promise<void> {
  const options: PrintMarkingCodeLabelsOptions =
    typeof duplicateCopiesOrOptions === 'number'
      ? { duplicateCopies: duplicateCopiesOrOptions }
      : duplicateCopiesOrOptions
  const layout = resolveLayout(options)
  const units = codes.map((cis) => ({
    cis,
    productLabel: options.productLabel ?? null,
  }))
  await printMarkingCodeTape(units, layout, options.productLabel)
}

async function printHtmlInIframe(html: string): Promise<void> {
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
