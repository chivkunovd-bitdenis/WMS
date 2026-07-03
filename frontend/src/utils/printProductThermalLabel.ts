import { DEFAULT_LABEL_SIZE, loadLabelSizeId, resolveLabelSize, type LabelSize } from './labelSize'
import {
  escapeLabelHtml,
  PRODUCT_LABEL_REVIEW_FOOTER,
  productLabelDetailLines,
  resolveProductLabelArticle,
  normalizeProductLabelName,
  type ProductLabelPrintOptions,
} from './productLabelText'
import { renderBarcodeDataUrl } from './renderBarcodeDataUrl'

export type ProductThermalLabelData = {
  product_name: string
  sku_code: string
  wb_vendor_code?: string | null
  wb_size?: string | null
  wb_color?: string | null
  wb_brand?: string | null
  wb_composition?: string | null
  seller_name?: string | null
  barcode: string
}

/** Базовый размер, под который исторически свёрстана этикетка. */
const BASE_LABEL_WIDTH_MM = 58
const BASE_LABEL_HEIGHT_MM = 40

export type LabelScale = {
  /** Масштаб по ширине относительно 58×40. */
  w: number
  /** Масштаб по высоте относительно 58×40. */
  h: number
  /** Равномерный масштаб (минимум из w/h) — отступы и квадратные элементы. */
  uniform: number
  /** Масштаб шрифтов: растёт с площадью этикетки, но ограничен шириной строки. */
  font: number
}

/** Коэффициенты масштабирования контента этикетки под выбранный физический размер. */
export function labelScale(size: LabelSize): LabelScale {
  const w = size.widthMm / BASE_LABEL_WIDTH_MM
  const h = size.heightMm / BASE_LABEL_HEIGHT_MM
  return {
    w,
    h,
    uniform: Math.min(w, h),
    font: Math.min(w * 1.4, Math.sqrt(w * h)),
  }
}

export function labelMm(value: number): string {
  return `${Math.round(value * 100) / 100}mm`
}

export function labelPt(value: number): string {
  return `${Math.round(value * 10) / 10}pt`
}

/**
 * CSS контента этикетки товара (штрихкод + текстовые поля), масштабированный
 * под выбранный размер. Используется и в одиночной печати, и в ленте ЧЗ.
 */
export function buildProductLabelContentCss(size: LabelSize = DEFAULT_LABEL_SIZE): string {
  const k = labelScale(size)
  const nameLines = k.h >= 1.8 ? 3 : 2
  // На вытянутых этикетках штрихкод растягиваем по высоте (бары это переносят),
  // на базовых — естественная высота растра, как было до масштабирования.
  const barcodeHeight =
    k.h > 1
      ? `height: ${labelMm(14 * k.h)};
    object-fit: fill;`
      : `height: auto;
    max-height: ${labelMm(14 * k.h)};
    object-fit: contain;`
  return `
  .barcode-wrap {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    margin-bottom: ${labelMm(0.8 * k.uniform)};
  }
  .barcode-wrap img {
    width: ${labelMm(52 * k.w)};
    max-width: 100%;
    ${barcodeHeight}
    display: block;
  }
  .digits {
    margin: ${labelMm(0.3 * k.uniform)} 0 0;
    font-size: ${labelPt(8 * k.font)};
    letter-spacing: 0.04em;
    text-align: center;
    font-family: Arial, Helvetica, sans-serif;
    line-height: 1.1;
  }
  .body {
    flex: 1 1 auto;
    min-height: 0;
    line-height: 1.2;
    font-size: ${labelPt(6.8 * k.font)};
    display: flex;
    flex-direction: column;
    gap: ${labelMm(0.15 * k.uniform)};
  }
  .seller {
    margin: 0;
    font-size: ${labelPt(6.8 * k.font)};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .name {
    margin: 0;
    font-size: ${labelPt(7 * k.font)};
    font-weight: 400;
    display: -webkit-box;
    -webkit-line-clamp: ${nameLines};
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
    margin: ${labelMm(0.4 * k.uniform)} 0 0;
    font-size: ${labelPt(6.4 * k.font)};
    text-align: left;
    line-height: 1.15;
  }
`
}

/**
 * CSS этикетки товара под выбранный физический размер.
 * Контент (штрихкод, шрифты, отступы) масштабируется вместе с листом,
 * чтобы этикетка заполняла всю наклейку, а не только угол.
 */
export function buildProductThermalLabelCss(size: LabelSize = DEFAULT_LABEL_SIZE): string {
  const k = labelScale(size)
  return `
  @page { size: ${size.widthMm}mm ${size.heightMm}mm; margin: 0; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body { font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; }
  .label {
    width: ${size.widthMm}mm;
    height: ${size.heightMm}mm;
    padding: ${labelMm(1.4 * k.uniform)} ${labelMm(1.8 * k.uniform)} ${labelMm(1 * k.uniform)};
    display: flex;
    flex-direction: column;
    overflow: hidden;
    page-break-after: always;
    break-after: page;
  }
  .label:last-child { page-break-after: auto; break-after: auto; }
  ${buildProductLabelContentCss(size)}
`
}

/** Дефолтный (58×40) CSS — обратная совместимость для существующих импортов. */
export const PRODUCT_THERMAL_LABEL_CSS = buildProductThermalLabelCss()

export function buildProductLabelSectionHtml(
  data: ProductThermalLabelData,
  barcodeDataUrl: string,
  printOptions?: ProductLabelPrintOptions,
): string {
  const name = escapeLabelHtml(normalizeProductLabelName(data.product_name))
  const article = escapeLabelHtml(resolveProductLabelArticle(data))
  const barcode = escapeLabelHtml(data.barcode.trim())
  const seller = data.seller_name?.trim()
  const sellerLine = seller
    ? `<p class="seller" title="${escapeLabelHtml(seller)}">${escapeLabelHtml(seller)}</p>`
    : ''
  const detailLines = productLabelDetailLines(data, printOptions)
    .map((line) => {
      const cls = line.startsWith('Состав:') ? 'meta meta-composition' : 'meta'
      return `<p class="${cls}">${escapeLabelHtml(line)}</p>`
    })
    .join('')
  const review = escapeLabelHtml(PRODUCT_LABEL_REVIEW_FOOTER)
  return `<section class="label" data-testid="product-thermal-label">
  <div class="barcode-wrap">
    <img id="barcode" src="${barcodeDataUrl}" alt="barcode" />
    <p class="digits">${barcode}</p>
  </div>
  <div class="body">
    ${sellerLine}
    <p class="name" title="${name}">${name}</p>
    <p class="meta">Артикул: ${article}</p>
    ${detailLines}
  </div>
  <p class="footer">${review}</p>
</section>`
}

export function buildProductThermalLabelDocument(
  data: ProductThermalLabelData,
  quantity: number,
  barcodeDataUrl: string,
  printOptions?: ProductLabelPrintOptions,
  labelSize: LabelSize = DEFAULT_LABEL_SIZE,
): string {
  const copies = Math.max(1, Math.min(999, Math.floor(quantity)))
  const labels = Array.from({ length: copies }, () =>
    buildProductLabelSectionHtml(data, barcodeDataUrl, printOptions),
  ).join('')
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Этикетка товара</title>
    <style>${buildProductThermalLabelCss(labelSize)}</style>
  </head>
  <body>${labels}</body>
</html>`
}

export function printProductThermalLabels(
  data: ProductThermalLabelData,
  quantity: number,
  printOptions?: ProductLabelPrintOptions,
  labelSize?: LabelSize,
): void {
  const barcode = data.barcode.trim()
  if (!barcode) {
    throw new Error('У товара нет штрихкода для печати.')
  }
  // Без явного размера печатаем на последнем выбранном пользователем.
  const size = labelSize ?? resolveLabelSize(loadLabelSizeId())
  const barcodeDataUrl = renderBarcodeDataUrl(barcode, { variant: 'thermal58' })
  const html = buildProductThermalLabelDocument(data, quantity, barcodeDataUrl, printOptions, size)

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
