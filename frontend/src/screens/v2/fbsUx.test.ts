import { describe, expect, it } from 'vitest'

import { fbsUnassignedPositionQuantity, supplyQrExpectedForStatus } from './fbsUx'

describe('supplyQrExpectedForStatus', () => {
  it('does not count a future supply QR while cargo-place QR codes are printed', () => {
    expect(supplyQrExpectedForStatus('draft')).toBe(false)
    expect(supplyQrExpectedForStatus('assembling')).toBe(false)
    expect(supplyQrExpectedForStatus('packed')).toBe(false)
  })

  it('requests the supply QR after handoff', () => {
    expect(supplyQrExpectedForStatus('in_delivery')).toBe(true)
    expect(supplyQrExpectedForStatus('done')).toBe(true)
  })
})


describe('Ozon position distribution', () => {
  it('requires every position, including multiple units in one position', () => {
    const positions = [{ id: 'first', quantity: 3 }, { id: 'second', quantity: 7 }]
    expect(fbsUnassignedPositionQuantity(positions, new Set(['first']))).toBe(7)
    expect(fbsUnassignedPositionQuantity(positions, new Set(['first', 'second']))).toBe(0)
  })

  it('does not mistake a missing position identity for a complete order', () => {
    expect(fbsUnassignedPositionQuantity([{ id: null, quantity: 2 }], new Set())).toBe(2)
  })
})
