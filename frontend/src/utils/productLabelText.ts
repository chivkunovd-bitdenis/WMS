/** Escape text for HTML label templates. */
export function escapeLabelHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export const PRODUCT_LABEL_REVIEW_FOOTER = 'Пожалуйста оставьте отзыв'

/** Product title on 58 mm WB-style thermal label (~7pt sans, up to two lines). */
export function truncateProductLabelName(name: string, maxLen = 42): string {
  const trimmed = name.trim().replace(/\s+/g, ' ')
  if (trimmed.length <= maxLen) {
    return trimmed
  }
  return `${trimmed.slice(0, Math.max(1, maxLen - 1))}…`
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

/** WB marketplace label lines below article (color, brand). */
export function productLabelDetailLines(meta: {
  wb_color?: string | null
  wb_brand?: string | null
}): string[] {
  const lines: string[] = []
  const color = meta.wb_color?.trim()
  const brand = meta.wb_brand?.trim()
  if (color) {
    lines.push(`Цвет: ${color}`)
  }
  if (brand) {
    lines.push(`Бренд: ${brand}`)
  }
  return lines
}

/** @deprecated Use productLabelDetailLines — size is not printed on WB 58×40 labels. */
export function productLabelVariantLines(meta: {
  wb_size?: string | null
  wb_color?: string | null
  wb_brand?: string | null
}): string[] {
  return productLabelDetailLines(meta)
}
