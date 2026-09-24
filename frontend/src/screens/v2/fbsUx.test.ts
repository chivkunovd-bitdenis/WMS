import { describe, expect, it } from 'vitest'

import type { FbsOrderMetadata } from './fbsApi'
import { fbsOzonAutoBoxesPlan, fbsOzonLabelFailuresText, fbsSameStickerScan, fbsUnassignedPositionQuantity, supplyQrExpectedForStatus, fbsMarkingPresentation, fbsMarkingVerdictsSummary, fbsOrderMarkingAccepted } from './fbsUx'

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


describe('WMS-526 Ozon auto boxes plan', () => {
  const ready = { status: 'ready', preview_url: '/label.pdf' }
  const box = (id: string, number: number, orderId: string, positionIds: string[], qr: typeof ready | null = null) => ({
    id, box_number: number, assigned_order_ids: [orderId], assigned_order_product_ids: positionIds, qr_asset: qr,
  })

  it('asks one label per fully distributed order without a ready label', () => {
    const orders = [
      { id: 'two-goods', status: 'new', external_order_id: 'A-1', positions: [{ id: 'a1', quantity: 1 }, { id: 'a2', quantity: 1 }] },
      { id: 'labelled', status: 'new', external_order_id: 'B-1', positions: [{ id: 'b1', quantity: 2 }] },
      { id: 'partial', status: 'new', external_order_id: 'C-1', positions: [{ id: 'c1', quantity: 1 }, { id: 'c2', quantity: 1 }] },
      { id: 'cancelled', status: 'cancelled', external_order_id: 'D-1', positions: [{ id: 'd1', quantity: 1 }] },
    ]
    const boxes = [
      box('box-a2', 4, 'two-goods', ['a2']),
      box('box-a1', 3, 'two-goods', ['a1']),
      box('box-b1', 1, 'labelled', ['b1'], ready),
      box('box-c1', 2, 'partial', ['c1']),
    ]
    const plan = fbsOzonAutoBoxesPlan(orders, boxes)
    expect(plan.labelTargets).toEqual([{ orderId: 'two-goods', externalOrderId: 'A-1', boxId: 'box-a1' }])
    // c2 ещё не разложен; позиция отменённого заказа не считается.
    expect(plan.unassignedPositions).toBe(1)
  })

  it('has nothing to do when all positions are boxed and labelled', () => {
    const orders = [{ id: 'o', status: 'new', external_order_id: 'E-1', positions: [{ id: 'e1', quantity: 1 }] }]
    const plan = fbsOzonAutoBoxesPlan(orders, [box('b', 1, 'o', ['e1'], ready)])
    expect(plan).toEqual({ unassignedPositions: 0, labelTargets: [] })
  })

  it('names failed Ozon orders grouped by reason', () => {
    expect(fbsOzonLabelFailuresText([
      { externalOrderId: 'X-1', reason: 'Обмен с Ozon выключен настройкой.' },
      { externalOrderId: 'Y-1', reason: 'Обмен с Ozon выключен настройкой.' },
      { externalOrderId: 'Z-1', reason: 'Таймаут' },
    ])).toBe('Без этикетки заказов: 3. Ozon №X-1, №Y-1 — Обмен с Ozon выключен настройкой; Ozon №Z-1 — Таймаут.')
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
