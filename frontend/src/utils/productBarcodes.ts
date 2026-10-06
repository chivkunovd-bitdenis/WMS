export function normalizeProductBarcodes(
  primaryBarcode: string | null | undefined,
  barcodes: string[] = [],
  fallbackBarcode?: string | null,
): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  for (const raw of [primaryBarcode, ...barcodes]) {
    const value = raw?.trim()
    if (!value || seen.has(value)) continue
    seen.add(value)
    result.push(value)
  }
  if (result.length === 0) {
    const fallback = fallbackBarcode?.trim()
    if (fallback && fallback !== '—') result.push(fallback)
  }
  return result
}
