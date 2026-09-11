import { describe, expect, it } from 'vitest'

import {
  mapConcurrentlyInOrder,
  resolveFbsFallbackLabelCopies,
  resolveProductTapeBarcodeError,
  resolveTapeCounts,
  withSelectedFbsTapeBarcode,
  remainingProductLabelsAfterPrintedCodes,
} from './MarkingPrintDialog'

describe('product tape barcode validation before consuming marking codes', () => {
  const mixedLayout = { units: [{ block: 'cz' as const, copies: 1 }, { block: 'label' as const, copies: 1 }] }

  it('rejects a missing actual Ozon barcode in mixed tapes', () => {
    expect(resolveProductTapeBarcodeError([], '', mixedLayout)).toContain('нет штрихкода Ozon')
    expect(resolveProductTapeBarcodeError([], '  ', mixedLayout)).toContain('нет штрихкода Ozon')
  })

  it('allows marking codes alone without an Ozon barcode', () => {
    expect(resolveProductTapeBarcodeError([], '', { units: [{ block: 'cz', copies: 2 }] })).toBeNull()
  })

  it('allows an actual selected barcode and preserves the WB-only path', () => {
    expect(resolveProductTapeBarcodeError([{ marketplace: 'ozon', barcode: 'OZN-ACTUAL' }], 'OZN-ACTUAL', mixedLayout)).toBeNull()
    expect(resolveProductTapeBarcodeError(undefined, '', mixedLayout)).toBeNull()
  })
})

describe('mapConcurrentlyInOrder', () => {
  it('limits concurrency and preserves source order', async () => {
    let active = 0
    let maxActive = 0
    const completed: number[] = []

    const result = await mapConcurrentlyInOrder([40, 5, 25, 10], 2, async (delay) => {
      active += 1
      maxActive = Math.max(maxActive, active)
      await new Promise((resolve) => setTimeout(resolve, delay))
      completed.push(delay)
      active -= 1
      return `ready-${delay}`
    })

    expect(maxActive).toBe(2)
    expect(completed).not.toEqual([40, 5, 25, 10])
    expect(result).toEqual(['ready-40', 'ready-5', 'ready-25', 'ready-10'])
  })
})

describe('resolveTapeCounts', () => {
  it('keeps zero ЧЗ and an empty tape when the order QR is printed', () => {
    expect(resolveTapeCounts(0, 0, true)).toEqual({
      cz: 0,
      wb: 0,
      tape: [],
      layout: { units: [] },
    })
  })

  it('keeps the old one-ЧЗ minimum when there is no order QR', () => {
    expect(resolveTapeCounts(0, 0, false)).toEqual({
      cz: 1,
      wb: 0,
      tape: ['cz'],
      layout: { units: [{ block: 'cz', copies: 1 }] },
    })
  })

  it('does not add ЧЗ when WB labels remain in the tape', () => {
    expect(resolveTapeCounts(0, 2, true)).toEqual({
      cz: 0,
      wb: 2,
      tape: ['label', 'label'],
      layout: { units: [{ block: 'label', copies: 2 }] },
    })
  })
})

describe('resolveFbsFallbackLabelCopies', () => {
  it('does not add product labels to ordinary orders in a mixed QR-only supply', () => {
    expect(resolveFbsFallbackLabelCopies(true, { units: [] }, 1, true)).toBe(0)
  })

  it('keeps the existing fallback outside QR-only printing', () => {
    expect(resolveFbsFallbackLabelCopies(true, { units: [{ block: 'cz', copies: 1 }] }, 1, false)).toBe(1)
  })
})


describe('Ozon position labels stay complete and keep their own identity', () => {
  const labelA = { product_name: 'A', sku_code: 'Ozon-A', barcode: '111', wb_size: null }
  const labelB = { product_name: 'B', sku_code: 'Ozon-B', barcode: '222', wb_size: null }
  const order: Parameters<typeof withSelectedFbsTapeBarcode>[0] = {
    orderId: 'order-a', wbOrderId: 0, marketplace: 'ozon', requiresHonestSign: true,
    productLabel: labelA,
    productLabels: [
      { positionId: 'position-a', productLabel: labelA, copies: 1 },
      { positionId: 'position-b', productLabel: labelB, copies: 2 },
    ],
  }
  const tape: Parameters<typeof withSelectedFbsTapeBarcode>[1] = {
    orders: [order], selectedBarcodeOrderId: 'order-a', selectedBarcodePositionId: 'position-a',
    includeOrderQr: false,
    print: async () => ({ orders: [], order_errors: [], shortage: 0 }),
    confirmQrApplied: async () => {},
  }
  const code = { id: 'code-a', cis_code: 'fixture-only', has_label_artifact: false, order_product_id: 'position-a' }

  it('uses the selected barcode only for the exact position and order', () => {
    const selected = { marketplace: 'ozon' as const, barcode: '113' }
    const result = withSelectedFbsTapeBarcode(order, tape, selected)
    expect(result.productLabels?.map((item) => item.productLabel.barcode)).toEqual(['113', '222'])
    expect(order.productLabels?.[0].productLabel.barcode).toBe('111')
    expect(withSelectedFbsTapeBarcode({ ...order, orderId: 'other' }, tape, selected).productLabels).toBe(order.productLabels)
    expect(withSelectedFbsTapeBarcode({ ...order, marketplace: 'wb' }, tape, selected).productLabels).toBe(order.productLabels)
  })

  it('keeps both ordinary units when the other position has a marking label', () => {
    const remaining = remainingProductLabelsAfterPrintedCodes(order, [code])
    expect(remaining.map((item) => [item.productLabel.barcode, item.copies])).toEqual([['222', 2]])
    expect(remainingProductLabelsAfterPrintedCodes({ ...order, marketplace: 'wb' }, [code])).toEqual([])
  })

  it('does not duplicate units already covered by their own marking labels', () => {
    const remaining = remainingProductLabelsAfterPrintedCodes(order, [
      code, { ...code, id: 'code-b', order_product_id: 'position-b' },
    ])
    expect(remaining.map((item) => [item.productLabel.barcode, item.copies])).toEqual([['222', 1]])
  })
})
