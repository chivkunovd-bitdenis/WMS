import { resolveProductPrimaryBarcode } from '../types/wbProductCatalog'
import { printProductThermalLabels } from './printProductThermalLabel'

export function printProductBarcodeLabel(options: {
  sku_code: string
  product_name?: string
  wb_vendor_code?: string | null
  wb_color?: string | null
  wb_brand?: string | null
  seller_name?: string | null
  barcode: string
  quantity?: number
}): void {
  const barcode = options.barcode.trim()
  if (!barcode) {
    throw new Error('У товара нет штрихкода для печати.')
  }
  printProductThermalLabels(
    {
      product_name: options.product_name ?? options.sku_code,
      sku_code: options.sku_code,
      wb_vendor_code: options.wb_vendor_code,
      wb_color: options.wb_color,
      wb_brand: options.wb_brand,
      seller_name: options.seller_name,
      barcode,
    },
    options.quantity ?? 1,
  )
}

export function printProductBarcodeFromMeta(
  meta: {
    sku_code: string
    product_name?: string
    wb_vendor_code?: string | null
    wb_color?: string | null
    wb_brand?: string | null
    seller_name?: string | null
    wb_primary_barcode?: string | null
    wb_barcodes?: string[]
  },
  quantity = 1,
): void {
  const barcode = resolveProductPrimaryBarcode(meta)
  if (!barcode) {
    throw new Error('У товара нет штрихкода WB — синхронизируйте карточки или укажите баркод.')
  }
  printProductBarcodeLabel({
    sku_code: meta.sku_code,
    product_name: meta.product_name,
    wb_vendor_code: meta.wb_vendor_code,
    wb_color: meta.wb_color,
    wb_brand: meta.wb_brand,
    seller_name: meta.seller_name,
    barcode,
    quantity,
  })
}
