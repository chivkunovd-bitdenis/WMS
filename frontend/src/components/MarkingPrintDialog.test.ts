import { describe, expect, it } from 'vitest'

import {
  mapConcurrentlyInOrder,
  resolveFbsFallbackLabelCopies,
  resolveProductTapeBarcodeError,
  resolveTapeCounts,
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
