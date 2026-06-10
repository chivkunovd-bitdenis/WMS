import { resolveProductPrimaryBarcode } from '../types/wbProductCatalog'
import { printBarcodeLabel } from './printBarcodeLabel'
import { renderBarcodeDataUrl } from './renderBarcodeDataUrl'

export function printProductBarcodeLabel(options: {
  sku_code: string
  product_name?: string
  barcode: string
}): void {
  const barcode = options.barcode.trim()
  if (!barcode) {
    throw new Error('У товара нет штрихкода для печати.')
  }
  const title = options.product_name
    ? `${options.sku_code} · ${options.product_name}`
    : options.sku_code
  printBarcodeLabel({
    title,
    barcode,
    barcodeDataUrl: renderBarcodeDataUrl(barcode),
  })
}

export function printProductBarcodeFromMeta(meta: {
  sku_code: string
  product_name?: string
  wb_primary_barcode?: string | null
  wb_barcodes?: string[]
}): void {
  const barcode = resolveProductPrimaryBarcode(meta)
  if (!barcode) {
    throw new Error('У товара нет штрихкода WB — синхронизируйте карточки или укажите баркод.')
  }
  printProductBarcodeLabel({
    sku_code: meta.sku_code,
    product_name: meta.product_name,
    barcode,
  })
}
