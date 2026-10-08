import type { FboPackingDetail, FboProductRow } from './fboPackingTypes'

const GS = '\x1d'

/**
 * Общая таблица товаров отгрузки: P (план) из строк, S (подобрано) из строк или
 * из подборов, B (в коробах) из составов коробов. Ничего не хранится отдельно.
 */
export function buildProductRows(detail: FboPackingDetail): FboProductRow[] {
  const pickedByProduct = new Map<string, number>()
  for (const allocation of detail.pick_allocations ?? []) {
    pickedByProduct.set(
      allocation.product_id,
      (pickedByProduct.get(allocation.product_id) ?? 0) + allocation.quantity,
    )
  }
  const boxedByProduct = new Map<string, number>()
  for (const box of detail.boxes) {
    for (const line of box.lines) {
      boxedByProduct.set(line.product_id, (boxedByProduct.get(line.product_id) ?? 0) + line.quantity)
    }
  }
  const rows: FboProductRow[] = []
  const byProduct = new Map<string, FboProductRow>()
  for (const line of detail.lines) {
    const existing = byProduct.get(line.product_id)
    if (existing) {
      existing.lineIds.push(line.id)
      existing.need += line.quantity
      existing.picked += line.picked_qty ?? 0
      existing.kizCount += line.kiz_count ?? 0
      if (line.requires_honest_sign !== undefined) {
        existing.requiresHonestSign = (existing.requiresHonestSign ?? false) || line.requires_honest_sign
      }
      existing.packagingInstructions ??= line.packaging_instructions ?? null
      continue
    }
    const row: FboProductRow = {
      productId: line.product_id,
      lineIds: [line.id],
      skuCode: line.sku_code,
      productName: line.product_name,
      need: line.quantity,
      picked: line.picked_qty ?? pickedByProduct.get(line.product_id) ?? 0,
      inBoxes: boxedByProduct.get(line.product_id) ?? 0,
      requiresHonestSign: line.requires_honest_sign,
      kizCount: line.kiz_count ?? 0,
      packagingInstructions: line.packaging_instructions ?? null,
    }
    byProduct.set(line.product_id, row)
    rows.push(row)
  }
  return rows
}

/**
 * N для «ШК + ЧЗ»: подобрано S, а если ничего не подобрано — план P.
 * Сервер не выдаёт кодов больше P − K.
 */
export function printTargetOf(row: Pick<FboProductRow, 'picked' | 'need'>): number {
  return row.picked > 0 ? row.picked : row.need
}

/** ШК короба: складской WHB-, приёмки INB- или внутренний ШК короба этой отгрузки. */
export function isBoxBarcode(raw: string, detail: FboPackingDetail): boolean {
  const code = raw.trim()
  if (!code) return false
  if (code.startsWith('WHB-') || code.startsWith('INB-')) return true
  const lower = code.toLowerCase()
  return detail.boxes.some((box) => box.internal_barcode?.trim().toLowerCase() === lower)
}

/**
 * Признак «это код Честного знака», когда он не совпал ни с ШК товара, ни с ШК короба.
 * Полный КИЗ — GS1: 01 + 14 цифр GTIN + 21 + серия, с разделителем GS; сканер в
 * другой раскладке или без GS отдаёт ту же длинную строку, разбор остаётся серверу
 * (та же функция, что в упаковке FBS). ШК товаров и артикулы такими длинными не бывают.
 */
export function looksLikeMarkingCode(raw: string): boolean {
  const code = raw.trim()
  if (!code) return false
  if (code.includes(GS)) return true
  if (/^\]d2/i.test(code)) return true
  if (/^01\d{14}21/.test(code)) return true
  return code.length >= 26
}

export type FboProductCodes = Map<string, string[]>

/** Товары отгрузки, чей ШК или артикул равен отсканированному (без учёта регистра). */
export function matchProductIds(raw: string, codesByProduct: FboProductCodes): string[] {
  const lower = raw.trim().toLowerCase()
  if (!lower) return []
  const matched: string[] = []
  for (const [productId, codes] of codesByProduct) {
    if (codes.some((code) => code.trim().toLowerCase() === lower)) matched.push(productId)
  }
  return matched
}

export type FboScanKind =
  | { kind: 'box' }
  | { kind: 'kiz' }
  | { kind: 'product'; productId: string | null }

/** Порядок разбора скана: короб → ШК товара → ЧЗ → неизвестный код уходит серверу как ШК товара. */
export function classifyScan(
  raw: string,
  detail: FboPackingDetail,
  codesByProduct: FboProductCodes,
): FboScanKind {
  if (isBoxBarcode(raw, detail)) return { kind: 'box' }
  const matched = matchProductIds(raw, codesByProduct)
  if (matched.length >= 1) return { kind: 'product', productId: matched.length === 1 ? matched[0]! : null }
  if (looksLikeMarkingCode(raw)) return { kind: 'kiz' }
  return { kind: 'product', productId: null }
}
