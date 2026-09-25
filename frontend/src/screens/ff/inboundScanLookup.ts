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
 * Область поиска задаёт документ (R5): обычная приёмка — товары документа,
 * затем каталог её селлера; возвратная — только товары документа, для неё
 * вызывающий передаёт `catalogIndex = null`.
 *
 * Порядок кандидатов (R7): сначала исходная строка во всей области — документ,
 * затем каталог. Только если исходная строка не нашлась нигде, проверяется
 * вариант раскладки (у скана со сканера) — тоже документ, затем каталог.
 * Иначе латинский код товара документа перебивал бы настоящий кириллический
 * артикул другой карточки каталога, и сервер засчитывал бы не тот товар.
 *
 * - Товар документа найден — его код и `product_id` как подсказка; сервер
 *   всё равно разрешает код сам и сверяет подсказку (R10).
 * - Код в документе ведёт к нескольким карточкам — не отправляется ничего (R2).
 * - Код узнал только каталог — уходит тот кандидат, по которому он нашёлся,
 *   без подсказки: найден ли товар и однозначен ли он, решает сервер (WMS-473).
 * - Не узнал никто — уходит код, как и раньше.
 */
export function resolveInboundProductScan(
  documentIndex: ProductScanIndex,
  catalogIndex: ProductScanIndex | null,
  input: InboundProductScanInput,
): InboundProductScanRequest {
  const raw = input.wedgeRaw ?? input.code
  const byRaw = resolveInScope(documentIndex, catalogIndex, raw)
  if (byRaw) return byRaw

  // Ручной ввод раскладку не исправляет: второго кандидата у него нет.
  if (input.wedgeRaw !== undefined && input.code !== raw) {
    const byLayout = resolveInScope(documentIndex, catalogIndex, input.code)
    if (byLayout) return byLayout
  }
  return { status: 'send', barcode: input.code }
}

/** Один кандидат во всей области приёмки: документ, затем каталог; null — не нашёлся нигде. */
function resolveInScope(
  documentIndex: ProductScanIndex,
  catalogIndex: ProductScanIndex | null,
  candidate: string,
): InboundProductScanRequest | null {
  const inDocument = resolveProductScan(documentIndex, candidate)
  if (inDocument.status === 'ambiguous') return { status: 'ambiguous' }
  if (inDocument.status === 'found') {
    return { status: 'send', barcode: inDocument.matchedCode, productId: inDocument.productId }
  }
  if (!catalogIndex) return null
  const inCatalog = resolveProductScan(catalogIndex, candidate)
  return inCatalog.status === 'not_found' ? null : { status: 'send', barcode: inCatalog.matchedCode }
}
