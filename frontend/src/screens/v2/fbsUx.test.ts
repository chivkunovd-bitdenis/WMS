import { describe, expect, it } from 'vitest'

import type { FbsOrderMetadata } from './fbsApi'
import { fbsOrderPrintDone, fbsSameStickerScan, fbsUnassignedPositionQuantity, supplyQrExpectedForStatus, fbsMarkingPresentation, fbsOrderMarkingAccepted } from './fbsUx'

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


describe('WMS-487: заказ напечатан', () => {
  const order = (states: FbsOrderMetadata['states'] = []) => ({
    sticker: { status: 'print_opened', applied_at: null },
    metadata: { required: [], optional: ['sgtin'], states, delivery_allowed: true, last_checked_at: null },
  })
  const accepted = { kind: 'sgtin', status: 'accepted' as const, reason: null, value_tail: 'TAIL0487' }

  it('не считает маркируемый заказ без кода напечатанным, даже если WB не требует ЧЗ', () => {
    expect(fbsOrderPrintDone(order(), true)).toBe(false)
    expect(fbsOrderPrintDone(order([{ ...accepted, value_tail: null }]), true)).toBe(false)
    expect(fbsOrderPrintDone(order([{ ...accepted, kind: 'uin' }]), true)).toBe(false)
  })

  it('считает напечатанным маркируемый заказ с принятым кодом и стикером', () => {
    expect(fbsOrderPrintDone(order([accepted]), true)).toBe(true)
  })

  it('считает немаркируемый заказ напечатанным по стикеру', () => {
    expect(fbsOrderPrintDone(order(), false)).toBe(true)
    expect(fbsOrderPrintDone({ ...order(), sticker: { status: 'applied', applied_at: null } }, false)).toBe(true)
    expect(fbsOrderPrintDone({ ...order(), sticker: { status: 'ready', applied_at: '2026-09-20' } }, false)).toBe(true)
  })

  it('сохраняет проверку маркировки при снятом требовании новых кодов через honest_sign_skipped', () => {
    expect(fbsOrderPrintDone(order(), false)).toBe(true)
    expect(fbsOrderPrintDone(order([accepted]), true)).toBe(true)
    expect(fbsOrderPrintDone({ ...order(), metadata: { ...order().metadata, required: ['sgtin'] } }, false)).toBe(false)
  })

  it('не засчитывает готовый к печати стикер или непринятый код', () => {
    expect(fbsOrderPrintDone({ ...order([accepted]), sticker: { status: 'ready', applied_at: null } }, true)).toBe(false)
    expect(fbsOrderPrintDone(order([{ ...accepted, status: 'pending' }]), true)).toBe(false)
    expect(fbsOrderPrintDone(order([{ ...accepted, reason: 'Код отклонён' }]), true)).toBe(false)
  })
})
