/** Escape text for HTML label templates. */
export function escapeLabelHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export const PRODUCT_LABEL_REVIEW_FOOTER = 'Пожалуйста оставьте отзыв'

/** Product title on 58 mm WB-style thermal label — normalize only; overflow is clipped in CSS (up to 2 lines). */
export function normalizeProductLabelName(name: string): string {
  return name.trim().replace(/\s+/g, ' ')
}

/** @deprecated Alias for {@link normalizeProductLabelName}. */
export function truncateProductLabelName(name: string): string {
  return normalizeProductLabelName(name)
}

export function resolveProductLabelArticle(meta: {
  sku_code: string
  wb_vendor_code?: string | null
}): string {
  const vendor = meta.wb_vendor_code?.trim()
  if (vendor) {
    return vendor
  }
  return meta.sku_code.trim()
}

/** Truncate long WB composition for narrow ШК column / thermal label. */
export function truncateProductLabelComposition(text: string, maxLen = 48): string {
  const trimmed = text.trim().replace(/\s+/g, ' ')
  if (trimmed.length <= maxLen) {
    return trimmed
  }
  return `${trimmed.slice(0, Math.max(1, maxLen - 1))}…`
}

/** Sub-lines under barcode in table ШК column (size, composition). */
export function productBarcodeColumnSubLines(meta: {
  wb_size?: string | null
  wb_composition?: string | null
}): string[] {
  const lines: string[] = []
  const size = meta.wb_size?.trim()
  const composition = meta.wb_composition?.trim()
  if (size) {
    lines.push(`Размер: ${size}`)
  }
  if (composition) {
    lines.push(`Состав: ${truncateProductLabelComposition(composition, 42)}`)
  }
  return lines
}

/** Which optional WB fields to show on thermal label / print preview. */
export type ProductLabelPrintOptions = {
  /** @deprecated Размер на термоэтикетке ШК больше не печатаем — место под цвет/бренд. */
  includeSize?: boolean
  includeComposition: boolean
}

export const DEFAULT_PRODUCT_LABEL_PRINT_OPTIONS: ProductLabelPrintOptions = {
  includeSize: false,
  includeComposition: true,
}

/**
 * WB marketplace label lines below article.
 * Порядок: цвет → бренд → состав. Размер на этикетку не выводим (мешает цвету/бренду на 58×40).
 */
export function productLabelDetailLines(
  meta: {
    wb_size?: string | null
    wb_color?: string | null
    wb_brand?: string | null
    wb_composition?: string | null
  },
  options: Partial<ProductLabelPrintOptions> = {},
): string[] {
  const includeComposition =
    options.includeComposition ?? DEFAULT_PRODUCT_LABEL_PRINT_OPTIONS.includeComposition
  const lines: string[] = []
  const color = meta.wb_color?.trim()
  const brand = meta.wb_brand?.trim()
  const composition = meta.wb_composition?.trim()
  // Размер намеренно не печатаем на ШК ВБ — на узкой этикетке важнее цвет и бренд.
  if (color) {
    lines.push(`Цвет: ${color}`)
  }
  if (brand) {
    lines.push(`Бренд: ${brand}`)
  }
  if (includeComposition && composition) {
    lines.push(`Состав: ${truncateProductLabelComposition(composition)}`)
  }
  return lines
}
