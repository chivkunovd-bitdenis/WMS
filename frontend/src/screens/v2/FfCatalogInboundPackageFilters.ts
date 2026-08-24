export type SourceDocument = {
  kind: string
  id: string
  number: string | null
  date: string
}

export type InboundPackageLine = {
  product_id: string
  remaining_qty: number
  name: string
  sku_code: string
  wb_vendor_code: string | null
  wb_barcode: string | null
  wb_size: string | null
  seller_name: string | null
}

export type InboundPackage = {
  id: string
  kind: 'box' | 'cargo_place'
  number: number
  internal_barcode: string
  request_id: string
  request_display_number: string | null
  warehouse_name: string | null
  intake_status: string
  composition_tracked: boolean
  fully_distributed: boolean
  remaining_qty: number | null
  lines: InboundPackageLine[]
  source_document: SourceDocument
}

export function normalizePackageProductSearch(value: string | null | undefined): string {
  return (value ?? '').trim().toLocaleLowerCase('ru-RU')
}

function normalizeSellerName(value: string | null | undefined): string {
  return (value ?? '').trim()
}

export function lineMatchesFilters(
  line: InboundPackageLine,
  selectedSeller: string,
  productSearch: string,
): boolean {
  if (selectedSeller && normalizeSellerName(line.seller_name) !== selectedSeller) return false
  const normalizedProductSearch = normalizePackageProductSearch(productSearch)
  if (!normalizedProductSearch) return true

  return [line.wb_barcode, line.wb_vendor_code, line.sku_code, line.name].some((value) =>
    normalizePackageProductSearch(value).includes(normalizedProductSearch),
  )
}

export function filterInboundPackages(
  packages: InboundPackage[],
  selectedSeller: string,
  productSearch: string,
): InboundPackage[] {
  return packages.filter((item) =>
    item.lines.some((line) => lineMatchesFilters(line, selectedSeller, productSearch)),
  )
}
