export type MarketplaceCode = 'wb' | 'ozon'

export type MarketplaceProductBinding = {
  marketplace: MarketplaceCode
  external_product_id?: string | null
  external_offer_id?: string | null
  external_sku?: string | null
  external_barcodes?: string[]
}

export type MarketplaceProductCatalogRow = {
  id: string
  name: string
  sku_code: string
  seller_name?: string | null
  wb_nm_id: number | null
  wb_vendor_code: string | null
  wb_subject_name: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
  wb_size: string | null
  wb_color: string | null
  wb_brand?: string | null
  wb_composition?: string | null
  packaging_instructions?: string | null
  marketplace_bindings?: MarketplaceProductBinding[]
}

/** @deprecated Use MarketplaceProductCatalogRow. */
export type WbProductCatalogRow = MarketplaceProductCatalogRow

export type ProductLineDisplayMeta = {
  sku_code: string
  product_name: string
  seller_name?: string | null
  wb_primary_image_url: string | null
  wb_primary_barcode: string | null
  wb_barcodes: string[]
  wb_vendor_code: string | null
  wb_nm_id: number | null
  wb_size: string | null
  wb_color: string | null
  wb_brand?: string | null
  wb_composition?: string | null
  packaging_instructions?: string | null
  units_in_pack?: number | null
  marketplace_bindings?: MarketplaceProductBinding[]
}

export function productDisplayMetaFromMarketplaceCatalog(
  productId: string,
  line: { sku_code: string; product_name?: string; name?: string },
  catalogById: Map<string, MarketplaceProductCatalogRow>,
): ProductLineDisplayMeta {
  const cat = catalogById.get(productId)
  const productName = line.product_name ?? line.name ?? cat?.name ?? line.sku_code
  if (cat) {
    return {
      sku_code: cat.sku_code,
      product_name: productName,
      seller_name: cat.seller_name ?? null,
      wb_primary_image_url: cat.wb_primary_image_url,
      wb_primary_barcode: cat.wb_primary_barcode,
      wb_barcodes: cat.wb_barcodes,
      wb_vendor_code: cat.wb_vendor_code,
      wb_nm_id: cat.wb_nm_id,
      wb_size: cat.wb_size,
      wb_color: cat.wb_color,
      wb_brand: cat.wb_brand ?? null,
      wb_composition: cat.wb_composition ?? null,
      packaging_instructions: cat.packaging_instructions ?? null,
      marketplace_bindings: cat.marketplace_bindings ?? [],
    }
  }
  return {
    sku_code: line.sku_code,
    product_name: productName,
    seller_name: null,
    wb_primary_image_url: null,
    wb_primary_barcode: null,
    wb_barcodes: [],
    wb_vendor_code: null,
    wb_nm_id: null,
    wb_size: null,
    wb_color: null,
    wb_brand: null,
    wb_composition: null,
    marketplace_bindings: [],
  }
}

/** @deprecated Use productDisplayMetaFromMarketplaceCatalog. */
export const productDisplayMetaFromCatalog = productDisplayMetaFromMarketplaceCatalog

export function catalogRowToDisplayMeta(row: {
  name: string
  sku_code: string
  seller_name?: string | null
  wb_primary_image_url?: string | null
  wb_primary_barcode?: string | null
  wb_barcodes?: string[]
  wb_vendor_code?: string | null
  wb_nm_id?: number | null
  wb_size?: string | null
  wb_color?: string | null
  wb_brand?: string | null
  wb_composition?: string | null
  packaging_instructions?: string | null
  units_in_pack?: number | null
  marketplace_bindings?: MarketplaceProductBinding[]
}): ProductLineDisplayMeta {
  return {
    sku_code: row.sku_code,
    product_name: row.name,
    seller_name: row.seller_name ?? null,
    wb_primary_image_url: row.wb_primary_image_url ?? null,
    wb_primary_barcode: row.wb_primary_barcode ?? null,
    wb_barcodes: row.wb_barcodes ?? [],
    wb_vendor_code: row.wb_vendor_code ?? null,
    wb_nm_id: row.wb_nm_id ?? null,
    wb_size: row.wb_size ?? null,
    wb_color: row.wb_color ?? null,
    wb_brand: row.wb_brand ?? null,
    wb_composition: row.wb_composition ?? null,
    packaging_instructions: row.packaging_instructions ?? null,
    units_in_pack: row.units_in_pack ?? null,
    marketplace_bindings: row.marketplace_bindings ?? [],
  }
}

export type ProductBarcodeOption = {
  marketplace: MarketplaceCode
  barcode: string
}

type ProductBarcodeSource = {
  wb_primary_barcode?: string | null
  wb_barcodes?: string[]
  marketplace_bindings?: MarketplaceProductBinding[]
}

export function resolveProductBarcodeOptions(meta: ProductBarcodeSource): ProductBarcodeOption[] {
  const options: ProductBarcodeOption[] = []
  const seen = new Set<string>()
  const add = (marketplace: MarketplaceCode, raw: string | null | undefined) => {
    const barcode = raw?.trim()
    if (!barcode) return
    const key = `${marketplace}:${barcode}`
    if (seen.has(key)) return
    seen.add(key)
    options.push({ marketplace, barcode })
  }
  // Сохраняем прежний первый код WB; коды Ozon берём только из связанной карточки.
  add('wb', meta.wb_primary_barcode)
  for (const barcode of meta.wb_barcodes ?? []) add('wb', barcode)
  for (const marketplace of ['wb', 'ozon'] as const) {
    for (const binding of meta.marketplace_bindings ?? []) {
      if (binding.marketplace !== marketplace) continue
      for (const barcode of binding.external_barcodes ?? []) add(marketplace, barcode)
    }
  }
  return options
}

export function resolveProductBarcodeSelection(
  options: ProductBarcodeOption[],
  selectionKey: string,
): ProductBarcodeOption | undefined {
  return options.find((option) => `${option.marketplace}:${option.barcode}` === selectionKey) ?? options[0]
}

export function resolveProductPrimaryBarcode(meta: ProductBarcodeSource): string {
  return resolveProductBarcodeOptions(meta)[0]?.barcode ?? ''
}

export function formatProductBarcodeDisplay(meta: ProductBarcodeSource): string {
  const code = resolveProductPrimaryBarcode(meta)
  if (code) {
    return code
  }
  const all = (meta.wb_barcodes ?? []).filter((b) => b.trim())
  if (all.length > 0) {
    return all.join(', ')
  }
  return '—'
}
