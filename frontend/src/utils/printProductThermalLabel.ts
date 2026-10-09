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
/** На 58×40 исторически был плотный интервал (~0.15mm), иначе 8 строк не влезают. */
const TEXT_LINE_GAP_COMPACT_MM = 0.18
/** Отступ текстового блока от цифр ШК (мм при fontScale=1). */
const BODY_TOP_GAP_MM = 0.55
const BODY_TOP_GAP_COMPACT_MM = 0.35

function isCompactLabel(size: LabelSize): boolean {
  return labelScale(size).h <= 1.01
}

function textLineGapMm(size: LabelSize): number {
  const font = labelTextFontScale(size)
  return (isCompactLabel(size) ? TEXT_LINE_GAP_COMPACT_MM : TEXT_LINE_GAP_MM) * font
}

function bodyTopGapMm(size: LabelSize): number {
  const font = labelTextFontScale(size)
  return (isCompactLabel(size) ? BODY_TOP_GAP_COMPACT_MM : BODY_TOP_GAP_MM) * font
}

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
  /** Исходный текст без HTML-экранирования (для повторной обрезки в trim). */
  plainText?: string
  /** Сколько визуальных строк занимает блок (название — до 2–3). */
  visualLines: number
  fontPt: number
  lineHeight: number
}

/** Высота области под текст внутри .body (мм), без футера «оставьте отзыв». */
export function estimateLabelTextAreaMm(size: LabelSize): number {
  const k = labelScale(size)
  const padding = (1.4 + 1) * k.uniform
  const barcodeBlock =
    0.8 * k.uniform +
    14 * k.uniform +
    0.3 * k.uniform +
    ptToMm(size, 8) * 1.2 +
    bodyTopGapMm(size)
  return size.heightMm - padding - barcodeBlock - footerReservedHeightMm(size)
}

function productLabelTextLineHeightMm(line: ProductLabelTextLine, size: LabelSize): number {
  return ptToMm(size, line.fontPt) * line.lineHeight * line.visualLines
}

function productLabelTextStackHeightMm(lines: ProductLabelTextLine[], size: LabelSize): number {
  const gap = textLineGapMm(size)
  return lines.reduce(
    (sum, line, index) => sum + (index > 0 ? gap : 0) + productLabelTextLineHeightMm(line, size),
    0,
  )
}

export function maxProductNameVisualLines(size: LabelSize): number {
  return labelScale(size).h >= 1.8 ? 3 : 2
}

/** Кегль названия (pt при fontScale=1) — держим в одном месте. */
const NAME_FONT_PT = 7
/** Приблизительная ширина символа относительно кегля (Arial/кириллица). */
const NAME_CHAR_WIDTH_RATIO = 0.55

/**
 * Максимум символов названия под размер этикетки. Обрезаем ТЕКСТ заранее,
 * а не через CSS max-height + overflow: на термопринтере обрезка «протекала»
 * и вторая строка названия печаталась поверх «Артикула».
 */
export function maxProductNameChars(size: LabelSize, targetLines?: number): number {
  const k = labelScale(size)
  const usableWidthMm = size.widthMm - 2 * 1.8 * k.uniform
  const charWidthMm = NAME_FONT_PT * labelTextFontScale(size) * NAME_CHAR_WIDTH_RATIO * PT_TO_MM
  const perLine = Math.max(1, Math.floor(usableWidthMm / charWidthMm))
  const lines = targetLines ?? maxProductNameVisualLines(size)
  return perLine * lines
}

function truncateNameToLines(name: string, size: LabelSize, targetLines?: number): string {
  const max = maxProductNameChars(size, targetLines)
  if (name.length <= max) {
    return name
  }
  return `${name.slice(0, Math.max(1, max - 1)).trimEnd()}…`
}

/** Сколько строк название реально займёт после переноса (для бюджета высоты). */
export function actualNameVisualLines(name: string, size: LabelSize): number {
  const k = labelScale(size)
  const usableWidthMm = size.widthMm - 2 * 1.8 * k.uniform
  const charWidthMm = NAME_FONT_PT * labelTextFontScale(size) * NAME_CHAR_WIDTH_RATIO * PT_TO_MM
  const perLine = Math.max(1, Math.floor(usableWidthMm / charWidthMm))
  const lines = Math.max(1, Math.ceil(name.length / perLine))
  return Math.min(maxProductNameVisualLines(size), lines)
}

const FOOTER_FONT_PT = 6.4

function footerReservedHeightMm(size: LabelSize): number {
  const k = labelScale(size)
  return (
    ptToMm(size, FOOTER_FONT_PT) * FOOTER_LINE_HEIGHT +
    0.35 * k.uniform +
    textLineGapMm(size)
  )
}

function resolveNameLineBudget(
  data: ProductThermalLabelData,
  size: LabelSize,
  printOptions?: ProductLabelPrintOptions,
): number {
  const maxLines = maxProductNameVisualLines(size)
  if (!isCompactLabel(size)) {
    return maxLines
  }
  const detailLines = productLabelDetailLines(data, printOptions).length
  if (detailLines >= 2 && data.wb_brand?.trim()) {
    return 1
  }
  return maxLines
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
  const rawName = normalizeProductLabelName(data.product_name)
  const nameLineBudget = resolveNameLineBudget(data, labelSize, printOptions)
  const truncatedName = truncateNameToLines(rawName, labelSize, nameLineBudget)
  const name = escapeLabelHtml(truncatedName)
  lines.push({
    kind: 'name',
    htmlClass: 'name',
    text: name,
    title: escapeLabelHtml(rawName),
    plainText: truncatedName,
    visualLines: actualNameVisualLines(truncatedName, labelSize),
    fontPt: NAME_FONT_PT,
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
  return lines
}

function isProtectedProductLabelLine(line: ProductLabelTextLine): boolean {
  if (line.kind === 'seller' || line.kind === 'name' || line.kind === 'article') {
    return true
  }
  // Цвет и бренд — приоритет на этикетке; состав режем раньше.
  return line.text.startsWith('Цвет:') || line.text.startsWith('Бренд:')
}

/** На 58×40 не выкидываем строки из HTML — как раньше: тело с overflow:hidden, футер снаружи. */
export function trimProductLabelTextLinesFromBottom(
  lines: ProductLabelTextLine[],
  size: LabelSize,
): ProductLabelTextLine[] {
  if (isCompactLabel(size)) {
    return lines.map((line) => ({ ...line }))
  }
  if (lines.length === 0) {
    return lines
  }
  const budget = estimateLabelTextAreaMm(size)
  let result = lines.map((line) => ({ ...line }))

  const dropFromBottom = (): boolean => {
    for (let i = result.length - 1; i >= 0; i -= 1) {
      const line = result[i]
      if (line && !isProtectedProductLabelLine(line)) {
        result.splice(i, 1)
        return true
      }
    }
    return false
  }

  while (productLabelTextStackHeightMm(result, size) > budget) {
    if (dropFromBottom()) {
      continue
    }
    const nameLine = result.find((line) => line.kind === 'name')
    if (nameLine && nameLine.visualLines > 1 && nameLine.plainText) {
      nameLine.visualLines -= 1
      const shorter = truncateNameToLines(nameLine.plainText, size, nameLine.visualLines)
      nameLine.plainText = shorter
      nameLine.text = escapeLabelHtml(shorter)
      continue
    }
    break
  }

  return result
}

function renderProductLabelTextLine(line: ProductLabelTextLine): string {
  const title = line.title ? ` title="${line.title}"` : ''
  // Название обрезаем по символам заранее (см. truncateNameToLines), поэтому здесь
  // без inline max-height: любой clamp на печати «протекал» и строки наезжали.
  return `<p class="${line.htmlClass}"${title}>${line.text}</p>`
}

/**
 * CSS контента этикетки товара (штрихкод + текстовые поля), масштабированный
 * под выбранный размер. Используется и в одиночной печати, и в ленте ЧЗ.
 */
export function buildProductLabelContentCss(size: LabelSize = DEFAULT_LABEL_SIZE): string {
  const k = labelScale(size)
  const textFont = labelTextFontScale(size)
  // На вытянутых этикетках нельзя масштабировать ШК по k.h (120/40=3): получалось
  // height≈42mm + текст > 120mm листа → принтер разъезжал на 2 наклейки.
  // Равномерный uniform + contain: ШК чуть крупнее 58×40, остальное — текст внизу.
  const compact = isCompactLabel(size)
  const barcodeWidthMm = 52 * k.uniform
  const barcodeMaxHeightMm = (compact ? 12 : 14) * k.uniform
  const sellerMinHeightMm = compact ? 0 : 6.8 * textFont * PT_TO_MM * TEXT_LINE_HEIGHT
  return `
  .barcode-wrap {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    margin-bottom: ${labelMm((compact ? 0.45 : 0.8) * k.uniform)};
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
    margin-top: ${labelMm(bodyTopGapMm(size))};
    line-height: ${TEXT_LINE_HEIGHT};
    font-size: ${labelPt(6.8 * textFont)};
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
  }
  /*
   * Межстрочный зазор — через margin-bottom, а не flex "gap": рендер термопринтера
   * (и старые движки печати) часто игнорируют flex gap → строки слипаются и длинное
   * название наезжает на «Артикул» (как на фото ИП Горячкина). margin работает везде.
   */
  .body > p {
    margin: 0 0 ${labelMm(textLineGapMm(size))};
    flex: 0 0 auto;
    flex-shrink: 0;
  }
  .body > p:last-child {
    margin-bottom: 0;
  }
  .seller {
    font-size: ${labelPt(6.8 * textFont)};
    line-height: ${TEXT_LINE_HEIGHT};
    ${compact ? '' : `min-height: ${labelMm(sellerMinHeightMm)};`}
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /*
   * Без max-height/overflow: название уже обрезано по символам в JS, поэтому строк
   * ровно столько, сколько влезает, и они идут обычным потоком — «Артикул» всегда
   * ниже названия и не может напечататься поверх (баг на термопринтере).
   */
  .name {
    font-size: ${labelPt(NAME_FONT_PT * textFont)};
    font-weight: 400;
    line-height: ${TEXT_LINE_HEIGHT};
    word-break: break-word;
  }
  .meta {
    line-height: ${TEXT_LINE_HEIGHT};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .meta-composition {
    white-space: nowrap;
  }
  .footer {
    flex: 0 0 auto;
    margin: ${labelMm(0.35 * k.uniform)} 0 0;
    font-size: ${labelPt(FOOTER_FONT_PT * textFont)};
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
  const compact = isCompactLabel(size)
  const labelPaddingTop = compact ? 1.2 * k.uniform : 1.4 * k.uniform
  const labelPaddingBottom = compact ? 0.8 * k.uniform : 1 * k.uniform
  return `
  @page { size: ${size.widthMm}mm ${size.heightMm}mm; margin: 0; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body { font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; }
  .label {
    width: ${size.widthMm}mm;
    height: ${size.heightMm}mm;
    padding: ${labelMm(labelPaddingTop)} ${labelMm(1.8 * k.uniform)} ${labelMm(labelPaddingBottom)};
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
  const footerHtml = `<p class="footer">${escapeLabelHtml(PRODUCT_LABEL_REVIEW_FOOTER)}</p>`
  return `<section class="label" data-testid="product-thermal-label">
  <div class="barcode-wrap">
    <img id="barcode" src="${barcodeDataUrl}" alt="barcode" />
    <p class="digits">${barcode}</p>
  </div>
  <div class="body">
    ${bodyHtml}
  </div>
  ${footerHtml}
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
