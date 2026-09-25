// WMS-536 · Товарная ветка скана приёмки поверх единого поиска товара.
//
// Сопоставление кода с карточкой делает только общий productScanResolver. Здесь
// остаётся то, что относится именно к приёмке: какие карточки входят в область
// документа и какую строку кода отправить серверу. ЧЗ/КИЗ сюда не попадает —
// экран распознаёт его раньше (isInboundMarkingScan), R8/R9.

import type { WbProductCatalogRow } from '../../types/wbProductCatalog'
import {
  buildProductScanIndex,
  productScanSourceFromCatalogRow,
  resolveProductScan,
  type ProductScanIndex,
  type ProductScanSource,
} from '../../utils/productScanResolver'

type InboundScanLine = {
  product_id: string
  sku_code: string
  wb_barcode?: string | null
}

/**
 * Индекс товаров документа: коды строк и все коды их карточек каталога —
 * sku, основной и все WB-коды, Ozon external_barcodes (R3). Товар, которого
 * в документе нет, сюда не попадает: его ищет сервер по каталогу селлера (R5).
 */
export function buildInboundDocumentScanIndex(
  lines: readonly InboundScanLine[],
  catalogById: ReadonlyMap<string, WbProductCatalogRow>,
): ProductScanIndex {
  const sources: ProductScanSource[] = []
  for (const line of lines) {
    sources.push({ productId: line.product_id, skuCode: line.sku_code, wbPrimaryBarcode: line.wb_barcode })
    const catalog = catalogById.get(line.product_id)
    if (catalog) sources.push(productScanSourceFromCatalogRow(catalog))
  }
  return buildProductScanIndex(sources)
}

const catalogIndexCache = new WeakMap<ReadonlyMap<string, WbProductCatalogRow>, ProductScanIndex>()

/** Индекс всего загруженного каталога селлера; строится один раз на загруженный каталог. */
export function inboundCatalogScanIndex(
  catalogById: ReadonlyMap<string, WbProductCatalogRow>,
): ProductScanIndex {
  const cached = catalogIndexCache.get(catalogById)
  if (cached) return cached
  const index = buildProductScanIndex(Array.from(catalogById.values(), productScanSourceFromCatalogRow))
  catalogIndexCache.set(catalogById, index)
  return index
}

export type InboundProductScanInput = {
  /** Код, который экран отправлял серверу и до WMS-536: у клавиатурного сканера — в латинской раскладке. */
  code: string
  /** Исходные символы клавиатурного сканера (R7). У ручного ввода их нет — раскладка не исправляется. */
  wedgeRaw?: string
}

export type InboundProductScanRequest =
  | { status: 'ambiguous' }
  | { status: 'send'; barcode: string; productId?: string }

/**
 * Что товарная ветка приёмки отправляет серверу.
 *
 * - Товар документа найден — его код и `product_id` как подсказка; сервер
 *   всё равно разрешает код сам и сверяет подсказку (R10).
 * - Код в документе ведёт к нескольким карточкам — не отправляется ничего (R2).
 * - В документе нет — сервер ищет в каталоге селлера (WMS-473) по одной строке
 *   и раскладку не исправляет. Поэтому для скана со сканера загруженный каталог
 *   подсказывает, какую строку отдать: исходную (настоящий кириллический
 *   артикул) или исправленную. Если каталог не узнал ни одну — уходит код, как
 *   и раньше. Найден ли товар и однозначен ли он, решает сервер.
 */
export function resolveInboundProductScan(
  documentIndex: ProductScanIndex,
  catalogIndex: ProductScanIndex | null,
  input: InboundProductScanInput,
): InboundProductScanRequest {
  const wedge = input.wedgeRaw !== undefined
  const raw = input.wedgeRaw ?? input.code
  const options = wedge ? { layoutCandidate: input.code } : {}

  const inDocument = resolveProductScan(documentIndex, raw, options)
  if (inDocument.status === 'ambiguous') return { status: 'ambiguous' }
  if (inDocument.status === 'found') {
    return { status: 'send', barcode: inDocument.matchedCode, productId: inDocument.productId }
  }

  if (wedge && catalogIndex) {
    const inCatalog = resolveProductScan(catalogIndex, raw, options)
    if (inCatalog.status !== 'not_found') return { status: 'send', barcode: inCatalog.matchedCode }
  }
  return { status: 'send', barcode: input.code }
}
