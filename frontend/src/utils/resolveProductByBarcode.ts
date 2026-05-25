export type BarcodeCatalogRow = {
  id: string
  sku_code: string
  wb_primary_barcode?: string | null
  wb_barcodes?: string[]
}

/** Exact match: SKU, primary WB barcode, or any WB barcode on the card. */
export function resolveProductIdByBarcode(
  rows: BarcodeCatalogRow[],
  raw: string,
): string | null {
  const code = raw.trim()
  if (!code) {
    return null
  }
  const lower = code.toLowerCase()
  for (const r of rows) {
    if (r.sku_code.toLowerCase() === lower) {
      return r.id
    }
    const primary = r.wb_primary_barcode?.trim()
    if (primary && primary.toLowerCase() === lower) {
      return r.id
    }
    for (const b of r.wb_barcodes ?? []) {
      if (b.trim().toLowerCase() === lower) {
        return r.id
      }
    }
  }
  return null
}
