import { describe, expect, it } from 'vitest'

import type { FbsOrderMetadata } from './fbsApi'
import { fbsSameStickerScan, fbsUnassignedPositionQuantity, supplyQrExpectedForStatus, fbsMarkingPresentation, fbsMarkingVerdictsSummary, fbsOrderMarkingAccepted } from './fbsUx'

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


describe('WMS-477 «Проверено в WB: подтверждено X из Y»', () => {
  type State = FbsOrderMetadata['states'][number]
  const order = (...states: Array<Partial<State>>) => ({
    metadata: {
      required: ['sgtin'],
      optional: [],
      states: states.map((state) => ({ kind: 'sgtin', status: 'pending', reason: null, ...state } as State)),
      delivery_allowed: false,
      last_checked_at: null,
    },
  })

  it('counts an order as checked only when WB accepted every code in it', () => {
    expect(fbsMarkingVerdictsSummary([
      order({ status: 'accepted', value_tail: 'ff00ee11' }),
      order({ status: 'allowed_without_check', value_tail: 'ab12cd34' }),
      order({ status: 'pending', value_tail: 'o~|#tail' }),
      order({ status: 'rejected', value_tail: 'bad00001' }),
    ])).toEqual({ confirmed: 2, withCode: 4 })
  })

  it('counts by the entered code, not by the status WB sent back', () => {
    // Сервер ставит `missing` и сохранённой записи, когда WB отвечает «required»
    // с пустым значением, но по кнопке такой заказ он всё равно сверяет.
    expect(fbsMarkingVerdictsSummary([order({ status: 'missing', value_tail: 'aa11bb22' })]))
      .toEqual({ confirmed: 0, withCode: 1 })
  })

  it('leaves out orders where no Честный знак was entered at all', () => {
    expect(fbsMarkingVerdictsSummary([
      order({ status: 'missing', value_tail: null }),
      order({ status: 'missing' }),
      order({ status: 'pending', value_tail: '' }),
      order(),
    ])).toEqual({ confirmed: 0, withCode: 0 })
  })

  it('ignores non-sgtin metadata and an empty packing tab', () => {
    expect(fbsMarkingVerdictsSummary([order({ kind: 'uin', status: 'accepted', value_tail: 'ff00ee11' })]))
      .toEqual({ confirmed: 0, withCode: 0 })
    expect(fbsMarkingVerdictsSummary([])).toEqual({ confirmed: 0, withCode: 0 })
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
