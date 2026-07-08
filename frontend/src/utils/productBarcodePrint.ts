import { resolveProductPrimaryBarcode, type ProductLineDisplayMeta } from '../types/wbProductCatalog'
import { printProductThermalLabels, type ProductThermalLabelData } from './printProductThermalLabel'

export type PackUnitsSource = {
  units_in_pack?: number | null
  packaging_instructions?: string | null
}

function clampPackUnits(value: number): number {
  if (!Number.isFinite(value)) {
    return 1
  }
  return Math.max(1, Math.min(999, Math.floor(value)))
}

/** Кол-во товаров в упаковке: явное поле или `pack_units:N` в ТЗ на упаковку. */
export function resolvePackUnits(source?: PackUnitsSource | null): number {
  if (source?.units_in_pack != null && source.units_in_pack >= 1) {
    return clampPackUnits(source.units_in_pack)
  }
  const text = source?.packaging_instructions?.trim() ?? ''
  const explicit = text.match(/pack_units\s*[:=]\s*(\d+)/i)
  if (explicit) {
    return clampPackUnits(Number(explicit[1]))
  }
  const ru = text.match(/(\d+)\s*шт(?:\.|\s|$|\s*(?:в|\/)\s*уп)/i)
  if (ru) {
    return clampPackUnits(Number(ru[1]))
  }
  return 1
}

/** Итоговое число этикеток ШК ВБ: множитель × кол-во в упаковке. */
export function resolveWbBarcodeLabelCount(qtyMultiplier: number, packUnits = 1): number {
  const qty = clampPackUnits(qtyMultiplier)
  const pack = clampPackUnits(packUnits)
  return qty * pack
}

/** Ручной ввод в диалоге печати: N этикеток, опционально ×2 по чекбоксу «Печатать 2 ШК». */
export function resolveManualWbLabelCount(labelCount: number, doubleBarcode = false): number {
  const count = clampPackUnits(labelCount)
  return count * (doubleBarcode ? 2 : 1)
}

export function displayMetaToProductLabel(meta: ProductLineDisplayMeta): ProductThermalLabelData {
  const barcode = resolveProductPrimaryBarcode(meta) ?? meta.sku_code
  return {
    product_name: meta.product_name,
    sku_code: meta.sku_code,
    barcode,
    wb_vendor_code: meta.wb_vendor_code,
    wb_size: meta.wb_size,
    wb_color: meta.wb_color,
    wb_brand: meta.wb_brand,
    wb_composition: meta.wb_composition,
    seller_name: meta.seller_name,
  }
}

export function printProductBarcodeLabel(options: {
  sku_code: string
  product_name?: string
  wb_vendor_code?: string | null
  wb_size?: string | null
  wb_color?: string | null
  wb_brand?: string | null
  wb_composition?: string | null
  seller_name?: string | null
  barcode: string
  /** Множитель этикеток (× кол-во в упаковке применяется отдельно). */
  quantity?: number
  packUnits?: number
  packaging_instructions?: string | null
  units_in_pack?: number | null
}): void {
  const barcode = options.barcode.trim()
  if (!barcode) {
    throw new Error('У товара нет штрихкода для печати.')
  }
  const packUnits = resolvePackUnits({
    units_in_pack: options.units_in_pack,
    packaging_instructions: options.packaging_instructions,
  })
  const totalLabels = resolveWbBarcodeLabelCount(options.quantity ?? 1, packUnits)
  printProductThermalLabels(
    {
      product_name: options.product_name ?? options.sku_code,
      sku_code: options.sku_code,
      wb_vendor_code: options.wb_vendor_code,
      wb_size: options.wb_size,
      wb_color: options.wb_color,
      wb_brand: options.wb_brand,
      wb_composition: options.wb_composition,
      seller_name: options.seller_name,
      barcode,
    },
    totalLabels,
  )
}

export function printProductBarcodeFromMeta(
  meta: {
    sku_code: string
    product_name?: string
    wb_vendor_code?: string | null
    wb_size?: string | null
    wb_color?: string | null
    wb_brand?: string | null
    wb_composition?: string | null
    seller_name?: string | null
    wb_primary_barcode?: string | null
    wb_barcodes?: string[]
    packaging_instructions?: string | null
    units_in_pack?: number | null
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
    wb_size: meta.wb_size,
    wb_color: meta.wb_color,
    wb_brand: meta.wb_brand,
    wb_composition: meta.wb_composition,
    seller_name: meta.seller_name,
    barcode,
    quantity,
    packaging_instructions: meta.packaging_instructions,
    units_in_pack: meta.units_in_pack,
  })
}
