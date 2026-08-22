import type { WbProductCatalogRow } from '../../types/wbProductCatalog'

type InboundScanLine = {
  product_id: string
  sku_code: string
  wb_barcode?: string | null
}

function addCode(target: Map<string, string>, code: string | null | undefined, productId: string) {
  const value = (code ?? '').trim()
  if (!value) return
  target.set(value, productId)
  target.set(value.toUpperCase(), productId)
}

export function buildInboundScanProductMap(
  lines: InboundScanLine[],
  catalogById: Map<string, WbProductCatalogRow>,
): Map<string, string> {
  const result = new Map<string, string>()
  for (const line of lines) {
    addCode(result, line.sku_code, line.product_id)
    addCode(result, line.wb_barcode, line.product_id)
    const catalog = catalogById.get(line.product_id)
    if (!catalog) continue
    addCode(result, catalog.sku_code, line.product_id)
    addCode(result, catalog.wb_primary_barcode, line.product_id)
    for (const barcode of catalog.wb_barcodes) {
      addCode(result, barcode, line.product_id)
    }
  }
  return result
}

export function findInboundScanProductId(
  barcode: string,
  productByBarcode: Map<string, string>,
): string | undefined {
  const value = barcode.trim()
  return productByBarcode.get(value) ?? productByBarcode.get(value.toUpperCase())
}
