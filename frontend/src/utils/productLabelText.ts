/** Escape text for HTML label templates. */
export function escapeLabelHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** One-line product title on 58 mm thermal label (~8pt sans). */
export function truncateProductLabelName(name: string, maxLen = 34): string {
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

export function productLabelVariantLines(meta: {
  wb_size?: string | null
  wb_color?: string | null
}): string[] {
  const lines: string[] = []
  const size = meta.wb_size?.trim()
  const color = meta.wb_color?.trim()
  if (size) {
    lines.push(`Размер: ${size}`)
  }
  if (color) {
    lines.push(`Цвет: ${color}`)
  }
  return lines
}
