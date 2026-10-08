import { describe, expect, it } from 'vitest'
import {
  buildProductRows,
  classifyScan,
  isBoxBarcode,
  looksLikeMarkingCode,
  matchProductIds,
  printTargetOf,
} from './fboPackingScan'
import type { FboPackingDetail } from './fboPackingTypes'

const KIZ = '0104650000000011215abcdefghij1\x1d91EE06\x1d92dGVzdHNpZ25hdHVyZXRlc3RzaWduYXR1cmV0ZXN0c2lnbmF0dXJl'

const detail: FboPackingDetail = {
  id: 'R1',
  warehouse_name: 'Склад',
  seller_name: 'Селлер',
  marketplace: 'wb',
  status: 'collecting',
  created_at: null,
  lines: [
    { id: 'L1', product_id: 'p1', sku_code: 'SKU1', product_name: 'Футболка', quantity: 30, picked_qty: 20 },
    { id: 'L2', product_id: 'p2', sku_code: 'SKU2', product_name: 'Носки', quantity: 5 },
  ],
  boxes: [
    { id: 'B1', internal_barcode: 'INB-0001', lines: [{ id: 'BL1', product_id: 'p1', sku_code: 'SKU1', product_name: 'Футболка', quantity: 12 }] },
    { id: 'B2', internal_barcode: 'WHB-0002', lines: [{ id: 'BL2', product_id: 'p1', sku_code: 'SKU1', product_name: 'Футболка', quantity: 8 }] },
  ],
  pick_allocations: [{ product_id: 'p2', quantity: 3 }],
}

describe('WMS-686 FBO упаковка · числа общей таблицы', () => {
  it('P из плана, B — сумма по всем коробам, S из строки либо из подборов', () => {
    const rows = buildProductRows(detail)
    expect(rows.map((row) => [row.productId, row.need, row.inBoxes, row.picked])).toEqual([
      ['p1', 30, 20, 20],
      ['p2', 5, 0, 3],
    ])
  })

  it('N для «ШК + ЧЗ» и «Допечатать»: подобрано, а при S = 0 — план', () => {
    expect(printTargetOf({ picked: 7, need: 10 })).toBe(7)
    expect(printTargetOf({ picked: 0, need: 10 })).toBe(10)
  })
})

describe('WMS-686 FBO упаковка · разбор скана', () => {
  const codes = new Map([['p1', ['SKU1', '2000000000011']], ['p2', ['SKU2', '2000000000028']]])

  it('ШК короба: WHB-, INB- и внутренний ШК короба отгрузки', () => {
    expect(isBoxBarcode('WHB-123', detail)).toBe(true)
    expect(isBoxBarcode('INB-777', detail)).toBe(true)
    expect(isBoxBarcode('inb-0001', detail)).toBe(true)
    expect(isBoxBarcode('2000000000011', detail)).toBe(false)
  })

  it('КИЗ: GS, префикс GS1 или длинная строка; ШК и артикулы не принимаются за КИЗ', () => {
    expect(looksLikeMarkingCode(KIZ)).toBe(true)
    expect(looksLikeMarkingCode('0104650000000011215abc')).toBe(true)
    expect(looksLikeMarkingCode('x'.repeat(26))).toBe(true)
    expect(looksLikeMarkingCode('2000000000011')).toBe(false)
    expect(looksLikeMarkingCode('SKU-ABC-1')).toBe(false)
  })

  it('порядок: короб → товар → КИЗ → неизвестный короткий код уходит серверу как ШК товара', () => {
    expect(classifyScan('INB-0001', detail, codes)).toEqual({ kind: 'box' })
    expect(classifyScan('2000000000028', detail, codes)).toEqual({ kind: 'product', productId: 'p2' })
    expect(classifyScan('sku1', detail, codes)).toEqual({ kind: 'product', productId: 'p1' })
    expect(classifyScan(KIZ, detail, codes)).toEqual({ kind: 'kiz' })
    expect(classifyScan('999', detail, codes)).toEqual({ kind: 'product', productId: null })
  })

  it('один ШК у двух товаров не выбирает товар сам', () => {
    const shared = new Map([['p1', ['555']], ['p2', ['555']]])
    expect(matchProductIds('555', shared)).toEqual(['p1', 'p2'])
    expect(classifyScan('555', detail, shared)).toEqual({ kind: 'product', productId: null })
  })
})
