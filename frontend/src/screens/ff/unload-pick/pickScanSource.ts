import {
  buildProductScanIndex,
  productScanSourceFromCatalogRow,
  type ProductScanCatalogRow,
  type ProductScanIndex,
  type ProductScanSource,
} from '../../../utils/productScanResolver'
import { cellRef, objRef, type ObjKind } from './pickStub'

/** Товар плана подбора так, как его уже показывают колонки «SKU» и «ШК». */
type PickPlanProductCodes = { id: string; sku: string; barcode: string }

/** Строка pick-options: `scan_codes` — все коды карточки списком строк (FbsPickOptionProductOut). */
type PickOptionCodes = {
  product_id: string
  scan_codes?: readonly (string | null | undefined)[] | null
}

/**
 * WMS-536 · Индекс «код → товар» подбора (S-OUT-01).
 *
 * Область — только товары плана этого документа (R5): товар, которого нет в
 * плане, по скану не находится, даже если он есть в каталоге селлера.
 *
 * Коды каждого товара берутся одновременно (R3): SKU и ШК строки плана, все
 * коды карточки каталога селлера (sku_code, основной и все WB-ШК, Ozon
 * external_barcodes) и `scan_codes` из pick-options, если сервер их отдаёт.
 *
 * В Ozon-поставке ФБС каталога у экрана нет, а в поле SKU строки плана сервер
 * кладёт Ozon SKU товара. Он находился по скану здесь и до WMS-536, и сервер в
 * этом подборе его тоже принимает (R4) — поэтому остаётся подсказкой, как был.
 * В других экранах Ozon SKU и offer_id товаром не становятся.
 */
export function pickProductScanIndex(
  products: readonly PickPlanProductCodes[],
  catalogById: ReadonlyMap<string, ProductScanCatalogRow>,
  pickOptions: readonly PickOptionCodes[],
): ProductScanIndex {
  const scanCodesByProductId = new Map<string, PickOptionCodes['scan_codes']>()
  for (const option of pickOptions) {
    if (option.scan_codes?.length) scanCodesByProductId.set(option.product_id, option.scan_codes)
  }
  const sources: ProductScanSource[] = []
  for (const product of products) {
    sources.push({
      productId: product.id,
      skuCode: product.sku,
      wbPrimaryBarcode: product.barcode,
      // scan_codes — все коды карточки одним списком. Поле источника в индексе
      // приоритета не задаёт: коды одной карточки просто сливаются.
      wbBarcodes: scanCodesByProductId.get(product.id),
    })
    const catalog = catalogById.get(product.id)
    if (catalog) sources.push(productScanSourceFromCatalogRow(catalog))
  }
  return buildProductScanIndex(sources)
}

/** The server already subtracts assignments/reservations in source.available. */
type ScanLocation = {
  storage_location_id: string
  available: number
  sources?: {
    available?: number
    container_path: { id: string; kind: ObjKind }[]
  }[]
}

export type ScanSource = {
  locationId: string
  containerKind: ObjKind | null
  containerId: string | null
}

/** Existing row disclosure needs the product identity even for an alternate barcode. */
export class PickScanSourceError extends Error {
  readonly productId: string

  constructor(productId: string, message: string) {
    super(message)
    this.name = 'PickScanSourceError'
    this.productId = productId
  }
}

export function resolveProductScanSource(
  product: { id: string; sku: string },
  locations: ScanLocation[],
  selected: ScanSource | null,
): ScanSource {
  // Preserve every explicit source: cell + NULL means loose stock, not any
  // container at that cell. The server validates its current availability.
  if (selected) return selected
  const candidates: ScanSource[] = []
  for (const location of locations) {
    const sources = location.sources?.length
      ? location.sources
      : [{ available: location.available, container_path: [] }]
    for (const source of sources) {
      if ((source.available ?? 0) < 1) continue
      const leaf = source.container_path.at(-1)
      candidates.push({
        locationId: location.storage_location_id,
        containerKind: leaf?.kind ?? null,
        containerId: leaf?.id ?? null,
      })
    }
  }
  if (candidates.length === 1) return candidates[0]
  throw new PickScanSourceError(
    product.id,
    candidates.length > 1
      ? `${product.sku} лежит в ${candidates.length} местах — уточните место или укажите число руками`
      : `${product.sku} — в выбранном месте нет доступного товара`,
  )
}

export function scanSourceKey(source: ScanSource): string {
  return source.containerId ? objRef(source.containerId) : cellRef(source.locationId)
}
