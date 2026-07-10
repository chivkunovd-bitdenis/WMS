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

/** Truncate long WB color for narrow thermal label (ellipsis in CSS is not enough for trim budget). */
export function truncateProductLabelColor(text: string, maxLen = 32): string {
  const trimmed = text.trim().replace(/\s+/g, ' ')
  if (trimmed.length <= maxLen) {
    return trimmed
  }
  return `${trimmed.slice(0, Math.max(1, maxLen - 1))}…`
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
  includeSize?: boolean
  includeComposition: boolean
}

export const DEFAULT_PRODUCT_LABEL_PRINT_OPTIONS: ProductLabelPrintOptions = {
  includeSize: true,
  includeComposition: true,
}

/**
 * WB marketplace label lines below article.
 * Порядок как на эталонных этикетках: размер → цвет → бренд → состав.
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
  const includeSize = options.includeSize ?? DEFAULT_PRODUCT_LABEL_PRINT_OPTIONS.includeSize
  const includeComposition =
    options.includeComposition ?? DEFAULT_PRODUCT_LABEL_PRINT_OPTIONS.includeComposition
  const lines: string[] = []
  const size = meta.wb_size?.trim()
  const color = meta.wb_color?.trim()
  const brand = meta.wb_brand?.trim()
  const composition = meta.wb_composition?.trim()
  if (includeSize && size && size !== '0') {
    lines.push(`Размер: ${size}`)
  }
  if (color) {
    lines.push(`Цвет: ${truncateProductLabelColor(color)}`)
  }
  if (brand) {
    lines.push(`Бренд: ${brand}`)
  }
  if (includeComposition && composition) {
    lines.push(`Состав: ${truncateProductLabelComposition(composition)}`)
  }
  return lines
}
