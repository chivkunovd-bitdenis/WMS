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

/** Межстрочный интервал текста — ниже 1.3 на термопечати ИП визуально «сплющивается». */
const TEXT_LINE_HEIGHT = 1.35
const FOOTER_LINE_HEIGHT = 1.2
/**
 * Базовый зазор между строками (мм при fontScale=1).
 * Масштабируем по шрифту (не только uniform): на 60×80/70×120 шрифт рос быстрее зазора.
 */
const TEXT_LINE_GAP_MM = 0.85
/** Отступ текстового блока от цифр ШК (мм при fontScale=1). */
const BODY_TOP_GAP_MM = 0.55

const PT_TO_MM = 25.4 / 72

/**
 * Масштаб текста: не даём площади этикетки раздувать шрифт так же агрессивно, как
 * исторический `labelScale.font` (sqrt(w×h)) — иначе на высоких наклейках строки слипаются.
 */
export function labelTextFontScale(size: LabelSize): number {
  const k = labelScale(size)
  return Math.min(k.w * 1.12, k.uniform * 1.25, 1.28)
}

function ptToMm(size: LabelSize, fontPt: number): number {
  return fontPt * labelTextFontScale(size) * PT_TO_MM
}

export type ProductLabelTextLineKind = 'seller' | 'name' | 'article' | 'meta' | 'footer'

export type ProductLabelTextLine = {
  kind: ProductLabelTextLineKind
  htmlClass: string
  text: string
  title?: string
  /** Сколько визуальных строк занимает блок (название — до 2–3). */
  visualLines: number
  fontPt: number
  lineHeight: number
}

/** Высота области под текст после штрихкода (мм), по расчёту вёрстки. */
export function estimateLabelTextAreaMm(size: LabelSize): number {
  const k = labelScale(size)
  const textFont = labelTextFontScale(size)
  const padding = (1.4 + 1) * k.uniform
  const barcodeBlock =
    0.8 * k.uniform +
    14 * k.uniform +
    0.3 * k.uniform +
    ptToMm(size, 8) * 1.2 +
    BODY_TOP_GAP_MM * textFont
  return size.heightMm - padding - barcodeBlock
}

function productLabelTextLineHeightMm(line: ProductLabelTextLine, size: LabelSize): number {
  return ptToMm(size, line.fontPt) * line.lineHeight * line.visualLines
}

function productLabelTextStackHeightMm(lines: ProductLabelTextLine[], size: LabelSize): number {
  const font = labelTextFontScale(size)
  const gap = TEXT_LINE_GAP_MM * font
  return lines.reduce(
    (sum, line, index) => sum + (index > 0 ? gap : 0) + productLabelTextLineHeightMm(line, size),
    0,
  )
}

export function maxProductNameVisualLines(size: LabelSize): number {
  return labelScale(size).h >= 1.8 ? 3 : 2
}

/** Строки этикетки сверху вниз: ИП → название → артикул → детали → отзыв. */
export function buildProductLabelTextLines(
  data: ProductThermalLabelData,
  printOptions?: ProductLabelPrintOptions,
  labelSize: LabelSize = DEFAULT_LABEL_SIZE,
): ProductLabelTextLine[] {
  const lines: ProductLabelTextLine[] = []
  const seller = data.seller_name?.trim()
  if (seller) {
    lines.push({
      kind: 'seller',
      htmlClass: 'seller',
      text: escapeLabelHtml(seller),
      title: escapeLabelHtml(seller),
      visualLines: 1,
      fontPt: 6.8,
      lineHeight: TEXT_LINE_HEIGHT,
    })
  }
  const name = escapeLabelHtml(normalizeProductLabelName(data.product_name))
  lines.push({
    kind: 'name',
    htmlClass: 'name',
    text: name,
    title: name,
    visualLines: maxProductNameVisualLines(labelSize),
    fontPt: 7,
    lineHeight: TEXT_LINE_HEIGHT,
  })
  const article = escapeLabelHtml(resolveProductLabelArticle(data))
  lines.push({
    kind: 'article',
    htmlClass: 'meta',
    text: `Артикул: ${article}`,
    visualLines: 1,
    fontPt: 6.8,
    lineHeight: TEXT_LINE_HEIGHT,
  })
  for (const detail of productLabelDetailLines(data, printOptions)) {
    const isComposition = detail.startsWith('Состав:')
    lines.push({
      kind: 'meta',
      htmlClass: isComposition ? 'meta meta-composition' : 'meta',
      text: escapeLabelHtml(detail),
      visualLines: 1,
      fontPt: 6.8,
      lineHeight: TEXT_LINE_HEIGHT,
    })
  }
  lines.push({
    kind: 'footer',
    htmlClass: 'footer',
    text: escapeLabelHtml(PRODUCT_LABEL_REVIEW_FOOTER),
    visualLines: 1,
    fontPt: 6.4,
    lineHeight: FOOTER_LINE_HEIGHT,
  })
  return lines
}

function mandatoryProductLabelPrefix(lines: ProductLabelTextLine[]): ProductLabelTextLine[] {
  const prefix: ProductLabelTextLine[] = []
  for (const line of lines) {
    prefix.push(line)
    if (line.kind === 'article') {
      break
    }
  }
  return prefix
}

/** Убирает нижние строки, пока блок не влезает; название сжимается до 1 строки в конце. */
export function trimProductLabelTextLinesFromBottom(
  lines: ProductLabelTextLine[],
  size: LabelSize,
): ProductLabelTextLine[] {
  if (lines.length === 0) {
    return lines
  }
  const budget = estimateLabelTextAreaMm(size)
  const minPrefix = mandatoryProductLabelPrefix(lines)
  let result = lines.map((line) => ({ ...line }))

  while (result.length > minPrefix.length && productLabelTextStackHeightMm(result, size) > budget) {
    result.pop()
  }

  while (productLabelTextStackHeightMm(result, size) > budget) {
    const nameLine = result.find((line) => line.kind === 'name')
    if (nameLine && nameLine.visualLines > 1) {
      nameLine.visualLines -= 1
      continue
    }
    break
  }

  return result
}

function renderProductLabelTextLine(line: ProductLabelTextLine): string {
  const title = line.title ? ` title="${line.title}"` : ''
  if (line.kind === 'name') {
    // max-height вместо -webkit-line-clamp: clamp в print Chromium даёт наезд на строку ИП.
    const maxHeightEm = (line.visualLines * line.lineHeight).toFixed(2)
    return `<p class="${line.htmlClass}"${title} style="max-height: ${maxHeightEm}em">${line.text}</p>`
  }
  return `<p class="${line.htmlClass}"${title}>${line.text}</p>`
}

/**
 * CSS контента этикетки товара (штрихкод + текстовые поля), масштабированный
 * под выбранный размер. Используется и в одиночной печати, и в ленте ЧЗ.
 */
export function buildProductLabelContentCss(size: LabelSize = DEFAULT_LABEL_SIZE): string {
  const k = labelScale(size)
  const textFont = labelTextFontScale(size)
  const nameLines = maxProductNameVisualLines(size)
  // На вытянутых этикетках нельзя масштабировать ШК по k.h (120/40=3): получалось
  // height≈42mm + текст > 120mm листа → принтер разъезжал на 2 наклейки.
  // Равномерный uniform + contain: ШК чуть крупнее 58×40, остальное — текст внизу.
  const barcodeWidthMm = 52 * k.uniform
  const barcodeMaxHeightMm = 14 * k.uniform
  const sellerMinHeightMm = 6.8 * textFont * PT_TO_MM * TEXT_LINE_HEIGHT
  const nameMaxHeightMm = 7 * textFont * PT_TO_MM * TEXT_LINE_HEIGHT * nameLines
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
    width: ${labelMm(barcodeWidthMm)};
    max-width: 100%;
    height: auto;
    max-height: ${labelMm(barcodeMaxHeightMm)};
    object-fit: contain;
    display: block;
  }
  .digits {
    margin: ${labelMm(0.3 * k.uniform)} 0 0;
    font-size: ${labelPt(8 * textFont)};
    letter-spacing: 0.04em;
    text-align: center;
    font-family: Arial, Helvetica, sans-serif;
    line-height: 1.2;
  }
  .body {
    flex: 1 1 auto;
    min-height: 0;
    overflow: hidden;
    margin-top: ${labelMm(BODY_TOP_GAP_MM * textFont)};
    line-height: ${TEXT_LINE_HEIGHT};
    font-size: ${labelPt(6.8 * textFont)};
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    gap: ${labelMm(TEXT_LINE_GAP_MM * textFont)};
  }
  .body > p {
    margin: 0;
    flex: 0 0 auto;
    flex-shrink: 0;
  }
  .seller {
    font-size: ${labelPt(6.8 * textFont)};
    line-height: ${TEXT_LINE_HEIGHT};
    min-height: ${labelMm(sellerMinHeightMm)};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .name {
    font-size: ${labelPt(7 * textFont)};
    font-weight: 400;
    line-height: ${TEXT_LINE_HEIGHT};
    max-height: ${labelMm(nameMaxHeightMm)};
    overflow: hidden;
    text-overflow: ellipsis;
    word-break: break-word;
  }
  .meta {
    line-height: ${TEXT_LINE_HEIGHT};
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .meta-composition {
    white-space: nowrap;
  }
  .footer {
    font-size: ${labelPt(6.4 * textFont)};
    text-align: left;
    line-height: ${FOOTER_LINE_HEIGHT};
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
  labelSize: LabelSize = DEFAULT_LABEL_SIZE,
): string {
  const barcode = escapeLabelHtml(data.barcode.trim())
  const textLines = trimProductLabelTextLinesFromBottom(
    buildProductLabelTextLines(data, printOptions, labelSize),
    labelSize,
  )
  const bodyHtml = textLines.map(renderProductLabelTextLine).join('')
  return `<section class="label" data-testid="product-thermal-label">
  <div class="barcode-wrap">
    <img id="barcode" src="${barcodeDataUrl}" alt="barcode" />
    <p class="digits">${barcode}</p>
  </div>
  <div class="body">
    ${bodyHtml}
  </div>
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
    buildProductLabelSectionHtml(data, barcodeDataUrl, printOptions, labelSize),
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
