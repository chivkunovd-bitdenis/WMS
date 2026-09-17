import { describe, expect, it, vi } from 'vitest'

import {
  fbsAssignedPositionQuantities,
  fbsBoxPositionQuantities,
  fbsBoxPositionQuantityInput,
  fbsBoxShipmentApplied,
  fbsPositionRemainingQuantity,
  fbsSameBoxPositions,
  fbsSameStickerScan,
  fbsUnassignedPositionQuantity,
  sendFbsBoxShipment,
  supplyQrExpectedForStatus,
  fbsMarkingPresentation,
  fbsOrderMarkingAccepted,
  type FbsBoxShipment,
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

describe('WMS-453 box shipment lifecycle (R6/R9)', () => {
  type Boxes = Array<{ id: string; assigned_positions?: Array<{ order_product_id: string; quantity: number }> }>
  type Workspace = { boxes: Boxes }
  const workspace = (shirtInBox1: number): Workspace => ({
    boxes: [
      { id: 'box-1', assigned_positions: shirtInBox1 > 0 ? [{ order_product_id: 'shirt', quantity: shirtInBox1 }] : [] },
      { id: 'box-2', assigned_positions: [] },
    ],
  })
  const networkFailure = () => new TypeError('Failed to fetch')
  const refusal = (error: unknown) => error instanceof Error && error.message.startsWith('409')
  const keys = () => {
    let n = 0
    return () => `key-${++n}`
  }

  it('helpers: quantities of one box, same-body comparison, applied check', () => {
    expect([...fbsBoxPositionQuantities(workspace(5).boxes, 'box-1').entries()]).toEqual([['shirt', 5]])
    expect(fbsBoxPositionQuantities(workspace(5).boxes, 'box-9').size).toBe(0)
    expect(fbsSameBoxPositions(
      [{ order_product_id: 'a', quantity: 1 }, { order_product_id: 'b', quantity: 2 }],
      [{ order_product_id: 'b', quantity: 2 }, { order_product_id: 'a', quantity: 1 }],
    )).toBe(true)
    expect(fbsSameBoxPositions([{ order_product_id: 'a', quantity: 5 }], [{ order_product_id: 'a', quantity: 10 }])).toBe(false)
    expect(fbsSameBoxPositions([{ order_product_id: 'a', quantity: 5 }], [])).toBe(false)
    const shipment: FbsBoxShipment = { key: 'k', boxId: 'box-1', positions: [{ order_product_id: 'shirt', quantity: 5 }], before: new Map([['shirt', 20]]) }
    expect(fbsBoxShipmentApplied(workspace(25).boxes, shipment)).toBe(true)
    expect(fbsBoxShipmentApplied(workspace(20).boxes, shipment)).toBe(false)
    expect(fbsBoxShipmentApplied(workspace(23).boxes, shipment)).toBe(false)
  })

  it('network failure, reload cannot confirm → retry sends the same body and the same key', async () => {
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sent.push(shipment)
      if (sent.length === 1) throw networkFailure()
      return workspace(5)
    })
    const reload = vi.fn(async () => workspace(0))
    const base = { boxId: 'box-1', boxes: workspace(0).boxes, send, reload, createKey: keys(), isDefinitiveRefusal: refusal }
    const positions = [{ order_product_id: 'shirt', quantity: 5 }]

    const first = await sendFbsBoxShipment({ ...base, pending: null, positions })
    expect(first.ok).toBe(false)
    expect(first.pending).toMatchObject({ key: 'key-1', boxId: 'box-1', positions })
    expect(reload).toHaveBeenCalledTimes(1)

    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions })
    expect(second.ok).toBe(true)
    expect(second.pending).toBeNull()
    expect(sent.map((item) => [item.key, item.positions])).toEqual([['key-1', positions], ['key-1', positions]])
  })

  it('network failure but the reload right after shows the box grew by the sent amount → success, no retry', async () => {
    const send = vi.fn(async () => { throw networkFailure() })
    const reload = vi.fn(async () => workspace(5))
    const result = await sendFbsBoxShipment({
      pending: null, boxId: 'box-1', positions: [{ order_product_id: 'shirt', quantity: 5 }], boxes: workspace(0).boxes,
      send, reload, createKey: keys(), isDefinitiveRefusal: refusal,
    })
    expect(result.ok).toBe(true)
    expect(result.pending).toBeNull()
    if (result.ok) expect(result.workspace).toEqual(workspace(5))
  })

  it('F2: first shipment actually applied, operator changes 5 → 10 → reload shows it applied, changed input never goes out under the old key', async () => {
    const sent: FbsBoxShipment[] = []
    const send = vi.fn<(shipment: FbsBoxShipment) => Promise<Workspace>>(async (shipment) => {
      sent.push(shipment)
      throw networkFailure()
    })
    let serverState = workspace(0)
    const reload = vi.fn(async () => serverState)
    const base = { boxId: 'box-1', boxes: workspace(0).boxes, send, reload, createKey: keys(), isDefinitiveRefusal: refusal }

    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: [{ order_product_id: 'shirt', quantity: 5 }] })
    expect(first.ok).toBe(false)
    expect(first.pending?.key).toBe('key-1')

    // Сервер на самом деле сохранил 5 — это видно только при следующей перечитке.
    serverState = workspace(5)
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: [{ order_product_id: 'shirt', quantity: 10 }] })
    // Ничего не отправлено: модалка остаётся открытой со свежим остатком, старая отправка снята.
    expect(second.ok).toBe('resolved')
    expect(second.pending).toBeNull()
    if (second.ok === 'resolved') expect(second.workspace).toEqual(workspace(5))
    expect(sent).toHaveLength(1)
    expect(sent[0]).toMatchObject({ key: 'key-1', positions: [{ order_product_id: 'shirt', quantity: 5 }] })

    // Следующее «Добавить» с 10 — уже новое действие с новым ключом.
    send.mockImplementationOnce(async (shipment: FbsBoxShipment) => { sent.push(shipment); return workspace(15) })
    const third = await sendFbsBoxShipment({ ...base, pending: second.pending, boxes: workspace(5).boxes, positions: [{ order_product_id: 'shirt', quantity: 10 }] })
    expect(third.ok).toBe(true)
    expect(sent.map((item) => [item.key, item.positions[0].quantity])).toEqual([['key-1', 5], ['key-2', 10]])
  })

  it('changed input while the earlier shipment turned out NOT applied → new key, new body, old pending dropped', async () => {
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sent.push(shipment)
      if (sent.length === 1) throw networkFailure()
      return workspace(10)
    })
    const reload = vi.fn(async () => workspace(0))
    const base = { boxId: 'box-1', boxes: workspace(0).boxes, send, reload, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: [{ order_product_id: 'shirt', quantity: 5 }] })
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: [{ order_product_id: 'shirt', quantity: 10 }] })
    expect(second.ok).toBe(true)
    expect(sent.map((item) => [item.key, item.positions[0].quantity])).toEqual([['key-1', 5], ['key-2', 10]])
  })

  it('changed input but the reload itself fails → nothing is sent, pending and its key stay for a later retry', async () => {
    const send = vi.fn(async () => { throw networkFailure() })
    const reload = vi.fn(async () => { throw networkFailure() })
    const base = { boxId: 'box-1', boxes: workspace(0).boxes, send, reload, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: [{ order_product_id: 'shirt', quantity: 5 }] })
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: [{ order_product_id: 'shirt', quantity: 10 }] })
    expect(second.ok).toBe(false)
    expect(second.pending).toBe(first.pending)
    expect(send).toHaveBeenCalledTimes(1)
  })

  it('definitive refusal (409) drops the pending; the corrected input goes out under a new key', async () => {
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sent.push(shipment)
      if (sent.length === 1) throw new Error('409 ozon_box_quantity_exceeded')
      return workspace(60)
    })
    const reload = vi.fn(async () => workspace(0))
    const base = { boxId: 'box-1', boxes: workspace(0).boxes, send, reload, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: [{ order_product_id: 'shirt', quantity: 70 }] })
    expect(first.ok).toBe(false)
    expect(first.pending).toBeNull()
    expect(reload).not.toHaveBeenCalled()
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: [{ order_product_id: 'shirt', quantity: 60 }] })
    expect(second.ok).toBe(true)
    expect(sent.map((item) => [item.key, item.positions[0].quantity])).toEqual([['key-1', 70], ['key-2', 60]])
  })

  it('success clears the pending, so the next add is a new action with a new key', async () => {
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => { sent.push(shipment); return workspace(5) })
    const base = { boxId: 'box-1', boxes: workspace(0).boxes, send, reload: vi.fn(), createKey: keys(), isDefinitiveRefusal: refusal }
    const positions = [{ order_product_id: 'shirt', quantity: 5 }]
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions })
    expect(first.ok).toBe(true)
    expect(first.pending).toBeNull()
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions })
    expect(second.ok).toBe(true)
    expect(sent.map((item) => item.key)).toEqual(['key-1', 'key-2'])
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
