export function normalizeProductBarcodes(
  primaryBarcode: string | null | undefined,
  barcodes: string[] = [],
): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  for (const raw of [primaryBarcode, ...barcodes]) {
    const value = raw?.trim()
    if (!value || seen.has(value)) continue
    seen.add(value)
    result.push(value)
  }
  return result
}
