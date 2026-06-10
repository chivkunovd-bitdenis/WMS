export type WbProductCatalogRow = {
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
}

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
}

export function productDisplayMetaFromCatalog(
  productId: string,
  line: { sku_code: string; product_name?: string; name?: string },
  catalogById: Map<string, WbProductCatalogRow>,
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
  }
}

export function resolveProductPrimaryBarcode(meta: {
  wb_primary_barcode?: string | null
  wb_barcodes?: string[]
}): string {
  const primary = meta.wb_primary_barcode?.trim()
  if (primary) {
    return primary
  }
  const first = meta.wb_barcodes?.find((b) => b.trim())
  return first?.trim() ?? ''
}

export function formatProductBarcodeDisplay(meta: {
  wb_primary_barcode?: string | null
  wb_barcodes?: string[]
}): string {
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
