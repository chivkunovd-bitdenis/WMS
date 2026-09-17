import { describe, expect, it } from 'vitest'

import {
  fbsAssignedPositionQuantities,
  fbsBoxPositionQuantityInput,
  fbsPositionRemainingQuantity,
  fbsSameStickerScan,
  fbsUnassignedPositionQuantity,
  supplyQrExpectedForStatus,
  fbsMarkingPresentation,
  fbsOrderMarkingAccepted,
} from './fbsUx'

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
    expect(fbsUnassignedPositionQuantity(positions, new Map([['first', 3]]))).toBe(7)
    expect(fbsUnassignedPositionQuantity(positions, new Map([['first', 3], ['second', 7]]))).toBe(0)
  })

  it('does not mistake a missing position identity for a complete order', () => {
    expect(fbsUnassignedPositionQuantity([{ id: null, quantity: 2 }], new Map())).toBe(2)
  })

  it('WMS-453: sums a position split across several boxes and leaves the rest to place', () => {
    const boxes = [
      { assigned_positions: [{ order_product_id: 'shirt', quantity: 10 }] },
      { assigned_positions: [{ order_product_id: 'shirt', quantity: 10 }, { order_product_id: 'hoodie', quantity: 6 }] },
      { assigned_positions: [] },
      {},
    ]
    const assigned = fbsAssignedPositionQuantities(boxes)
    expect([...assigned.entries()]).toEqual([['shirt', 20], ['hoodie', 6]])
    expect(fbsPositionRemainingQuantity({ id: 'shirt', quantity: 100 }, assigned)).toBe(80)
    expect(fbsPositionRemainingQuantity({ id: 'hoodie', quantity: 6 }, assigned)).toBe(0)
    expect(fbsUnassignedPositionQuantity([{ id: 'shirt', quantity: 100 }, { id: 'hoodie', quantity: 6 }], assigned)).toBe(80)
  })

  it('WMS-453: a position without an id is never counted as placed', () => {
    const assigned = fbsAssignedPositionQuantities([{ assigned_positions: [{ order_product_id: 'x', quantity: 5 }] }])
    expect(fbsPositionRemainingQuantity({ id: null, quantity: 4 }, assigned)).toBe(4)
    expect(fbsPositionRemainingQuantity({ quantity: 4 }, assigned)).toBe(4)
  })

  it('WMS-453: never reports a negative remainder when boxes hold more than the order', () => {
    const assigned = new Map([['shirt', 120]])
    expect(fbsPositionRemainingQuantity({ id: 'shirt', quantity: 100 }, assigned)).toBe(0)
  })
})

describe('WMS-453 box quantity input', () => {
  it('clamps typed values to 1…remaining like the WB box field clamps 0…orders', () => {
    expect(fbsBoxPositionQuantityInput('10', 60)).toBe('10')
    expect(fbsBoxPositionQuantityInput('60', 60)).toBe('60')
    expect(fbsBoxPositionQuantityInput('61', 60)).toBe('60')
    expect(fbsBoxPositionQuantityInput('999', 60)).toBe('60')
    expect(fbsBoxPositionQuantityInput('0', 60)).toBe('1')
    expect(fbsBoxPositionQuantityInput('-5', 60)).toBe('1')
    expect(fbsBoxPositionQuantityInput('5.9', 60)).toBe('5')
  })

  it('keeps the field empty while the operator has typed nothing usable', () => {
    expect(fbsBoxPositionQuantityInput('', 60)).toBe('')
    expect(fbsBoxPositionQuantityInput('   ', 60)).toBe('')
    expect(fbsBoxPositionQuantityInput('abc', 60)).toBe('')
  })
})


describe('WMS-086 marking verdict presentation', () => {
  it.each(['assigned', 'sending', 'pending', 'unknown', 'allowed_without_check'] as const)(
    'keeps %s neutral even with a code tail', (status) => {
      const state = { kind: 'sgtin', status, reason: null, value_tail: 'TAIL0086' }
      expect(fbsMarkingPresentation(state).tone).toBe('neutral')
      expect(fbsOrderMarkingAccepted({ required: [], optional: [], states: [state], delivery_allowed: false, last_checked_at: null })).toBe(false)
      expect(fbsOrderMarkingAccepted({ required: ['sgtin'], optional: [], states: [state], delivery_allowed: false, last_checked_at: null })).toBe(false)
    },
  )

  it('uses the actual acceptance, not just a tail', () => {
    const state = { kind: 'sgtin', status: 'accepted' as const, reason: null, value_tail: 'TAIL0086' }
    expect(fbsMarkingPresentation(state).tone).toBe('success')
    expect(fbsOrderMarkingAccepted({ required: ['sgtin'], optional: [], states: [state], delivery_allowed: false, last_checked_at: null })).toBe(true)
  })

  it.each(['rejected', 'replacement_required'] as const)('shows %s in red with the received reason', (status) => {
    const state = { kind: 'sgtin', status, reason: 'Код принадлежит другому товару', value_tail: 'TAIL0086' }
    expect(fbsMarkingPresentation(state)).toMatchObject({ tone: 'error', reason: 'Код принадлежит другому товару' })
  })

  it('translates the saved WB decision when WB supplied no reason', () => {
    expect(fbsMarkingPresentation({ kind: 'sgtin', status: 'rejected', decision: 'sgtinApplied', reason: null }).reason)
      .toContain('не введён в оборот')
    expect(fbsMarkingPresentation({ kind: 'sgtin', status: 'rejected', decision: 'sgtinRetired', reason: null }).reason).toContain('выведен из оборота')
    expect(fbsMarkingPresentation({ kind: 'sgtin', status: 'rejected', decision: 'invalid', reason: null }).reason).toBeNull()
  })

  it('does not show success when an accepted status has a refusal reason', () => {
    expect(fbsMarkingPresentation({ kind: 'sgtin', status: 'accepted', reason: 'sgtinNoGS' }))
      .toMatchObject({ tone: 'error', reason: expect.stringContaining('отсканируйте') })
  })
})


describe('WMS-394 repeated active sticker', () => {
  it('matches scanner whitespace, BOM and Russian keyboard layout', () => {
    expect(fbsSameStickerScan(' \ufeff*DVNdzDVg\r\n', '*ВМТвяВМп')).toBe(true)
    expect(fbsSameStickerScan('*ВМТвяВМп', '*DVNdzDVg')).toBe(true)
    expect(fbsSameStickerScan('*DVN dzDVg', '*DVNdzDVg')).toBe(true)
  })
  it('keeps case, punctuation, other orders and actual KIZ distinct', () => {
    expect(fbsSameStickerScan('*dvndzdvg', '*DVNdzDVg')).toBe(false)
    expect(fbsSameStickerScan('*DVNdzDVg', '*DU7aq2hE')).toBe(false)
    expect(fbsSameStickerScan('010460000000001821ABC', '*DU7aq2hE')).toBe(false)
    expect(fbsSameStickerScan('  ', '')).toBe(false)
    expect(fbsSameStickerScan('ABC/123', 'ABC?123')).toBe(false)
  })
})
