import { describe, expect, it, vi } from 'vitest'

import {
  fbsAssignedPositionQuantities,
  fbsBoxPositionQuantityInput,
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
  // Модель сервера: строка «shirt» в коробе 1 и уже применённые ключи. Повтор
  // с известным ключом — пустая операция, как в _assign_ozon_positions.
  type Workspace = { boxes: Array<{ id: string; assigned_positions: Array<{ order_product_id: string; quantity: number }> }> }
  const makeServer = () => {
    const state = { shirt: 0, applied: new Set<string>() }
    const workspace = (): Workspace => ({ boxes: [{ id: 'box-1', assigned_positions: state.shirt > 0 ? [{ order_product_id: 'shirt', quantity: state.shirt }] : [] }] })
    const apply = (shipment: FbsBoxShipment): Workspace => {
      if (!state.applied.has(shipment.key)) {
        state.applied.add(shipment.key)
        state.shirt += shipment.positions[0].quantity
      }
      return workspace()
    }
    return { state, workspace, apply }
  }
  const networkFailure = () => new TypeError('Failed to fetch')
  const refusal = (error: unknown) => error instanceof Error && error.message.startsWith('409')
  const keys = () => {
    let n = 0
    return () => `key-${++n}`
  }
  const five = [{ order_product_id: 'shirt', quantity: 5 }]
  const ten = [{ order_product_id: 'shirt', quantity: 10 }]

  it('same-body comparison ignores order and catches a changed quantity', () => {
    expect(fbsSameBoxPositions(
      [{ order_product_id: 'a', quantity: 1 }, { order_product_id: 'b', quantity: 2 }],
      [{ order_product_id: 'b', quantity: 2 }, { order_product_id: 'a', quantity: 1 }],
    )).toBe(true)
    expect(fbsSameBoxPositions(five, ten)).toBe(false)
    expect(fbsSameBoxPositions(five, [])).toBe(false)
  })

  it('network failure → retry with unchanged input sends the same body and key; success closes', async () => {
    const server = makeServer()
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sent.push(shipment)
      if (sent.length === 1) throw networkFailure() // не дошло до сервера
      return server.apply(shipment)
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: five })
    expect(first.ok).toBe(false)
    expect(first.pending).toMatchObject({ key: 'key-1', boxId: 'box-1', positions: five })
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: five })
    expect(second.ok).toBe(true)
    expect(second.pending).toBeNull()
    expect(sent.map((item) => [item.key, item.positions])).toEqual([['key-1', five], ['key-1', five]])
    expect(server.state.shirt).toBe(5)
  })

  it('F3: A not delivered, B (other key) adds 5 meanwhile → A retry is not declared done by B data; both applied → 10', async () => {
    const server = makeServer()
    const sentByA: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sentByA.push(shipment)
      if (sentByA.length === 1) throw networkFailure() // запрос A не доставлен
      return server.apply(shipment)
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: five })
    expect(first.ok).toBe(false)
    // Оператор B успешно добавил свои 5 другим ключом.
    server.apply({ key: 'key-B', boxId: 'box-1', positions: five })
    expect(server.state.shirt).toBe(5)
    // Восстановление A: повтор своего тела своим ключом, а не вывод по приросту.
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: five })
    expect(second.ok).toBe(true)
    expect(sentByA.map((item) => item.key)).toEqual(['key-1', 'key-1'])
    expect(server.state.shirt).toBe(10)
  })

  it('F3 symmetric: A applied but response lost, B adds 5 → A retry is a no-op: 10, not 15', async () => {
    const server = makeServer()
    const sentByA: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sentByA.push(shipment)
      const result = server.apply(shipment)
      if (sentByA.length === 1) throw networkFailure() // сервер применил, ответ потерян
      return result
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: five })
    expect(first.ok).toBe(false)
    expect(server.state.shirt).toBe(5)
    server.apply({ key: 'key-B', boxId: 'box-1', positions: five })
    expect(server.state.shirt).toBe(10)
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: five })
    expect(second.ok).toBe(true)
    expect(sentByA.map((item) => item.key)).toEqual(['key-1', 'key-1'])
    expect(server.state.shirt).toBe(10)
  })

  it('F2: applied but response lost, operator changes 5 → 10: the pending is replayed with its own key (no-op) → resolved, modal stays open; next add is a new key', async () => {
    const server = makeServer()
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sent.push(shipment)
      const result = server.apply(shipment)
      if (sent.length === 1) throw networkFailure()
      return result
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: five })
    expect(first.ok).toBe(false)
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: ten })
    expect(second.ok).toBe('resolved')
    expect(second.pending).toBeNull()
    if (second.ok === 'resolved') expect(second.workspace).toEqual(server.workspace())
    expect(server.state.shirt).toBe(5)
    expect(sent.map((item) => [item.key, item.positions[0].quantity])).toEqual([['key-1', 5], ['key-1', 5]])
    const third = await sendFbsBoxShipment({ ...base, pending: second.pending, positions: ten })
    expect(third.ok).toBe(true)
    expect(sent.map((item) => [item.key, item.positions[0].quantity])).toEqual([['key-1', 5], ['key-1', 5], ['key-2', 10]])
    expect(server.state.shirt).toBe(15)
  })

  it('F2 with a not-delivered first request: changing 5 → 10 first replays 5/K (applies it) → resolved with 5, then 10 under a new key', async () => {
    const server = makeServer()
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sent.push(shipment)
      if (sent.length === 1) throw networkFailure()
      return server.apply(shipment)
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: five })
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: ten })
    expect(second.ok).toBe('resolved')
    expect(server.state.shirt).toBe(5)
    expect(sent.map((item) => [item.key, item.positions[0].quantity])).toEqual([['key-1', 5], ['key-1', 5]])
  })

  it('changed input, replay of the pending fails again with a network error → nothing else is sent, pending kept', async () => {
    const sent: FbsBoxShipment[] = []
    const send = vi.fn<(shipment: FbsBoxShipment) => Promise<Workspace>>(async (shipment) => {
      sent.push(shipment)
      throw networkFailure()
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: five })
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: ten })
    expect(second.ok).toBe(false)
    expect(second.pending).toBe(first.pending)
    expect(sent.map((item) => [item.key, item.positions[0].quantity])).toEqual([['key-1', 5], ['key-1', 5]])
  })

  it('changed input, replay of the pending is definitively refused (409) → pending dropped, changed input goes out under a new key', async () => {
    const server = makeServer()
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sent.push(shipment)
      if (sent.length === 1) throw networkFailure()
      if (sent.length === 2) throw new Error('409 ozon_box_quantity_exceeded')
      return server.apply(shipment)
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: [{ order_product_id: 'shirt', quantity: 70 }] })
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: [{ order_product_id: 'shirt', quantity: 60 }] })
    expect(second.ok).toBe(true)
    expect(second.pending).toBeNull()
    expect(sent.map((item) => [item.key, item.positions[0].quantity])).toEqual([['key-1', 70], ['key-1', 70], ['key-2', 60]])
  })

  it('definitive refusal (409) on a fresh send drops the pending; the corrected input goes out under a new key', async () => {
    const server = makeServer()
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sent.push(shipment)
      if (sent.length === 1) throw new Error('409 ozon_box_quantity_exceeded')
      return server.apply(shipment)
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: [{ order_product_id: 'shirt', quantity: 70 }] })
    expect(first.ok).toBe(false)
    expect(first.pending).toBeNull()
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: [{ order_product_id: 'shirt', quantity: 60 }] })
    expect(second.ok).toBe(true)
    expect(sent.map((item) => [item.key, item.positions[0].quantity])).toEqual([['key-1', 70], ['key-2', 60]])
  })

  it('F4: pending exists but the background refresh emptied the addable list (remainder 0) → unchanged typed input replays the pending → success, close', async () => {
    const server = makeServer()
    const hundred = [{ order_product_id: 'shirt', quantity: 100 }]
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sent.push(shipment)
      const result = server.apply(shipment)
      if (sent.length === 1) throw networkFailure() // сервер применил все 100, ответ потерян
      return result
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: hundred, typedPositions: hundred })
    expect(first.ok).toBe(false)
    expect(server.state.shirt).toBe(100)
    // Фоновое обновление: остаток 0, строка ушла из списка — новое тело пустое,
    // но ввод оператора (отмечено, 100) не менялся.
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: [], typedPositions: hundred })
    expect(second.ok).toBe(true)
    expect(second.pending).toBeNull()
    expect(sent.map((item) => [item.key, item.positions[0].quantity])).toEqual([['key-1', 100], ['key-1', 100]])
    expect(server.state.shirt).toBe(100)
  })

  it('F4 variant: pending exists, operator unchecked everything → the pending is still replayed first; resolved, nothing new sent', async () => {
    const server = makeServer()
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => {
      sent.push(shipment)
      if (sent.length === 1) throw networkFailure()
      return server.apply(shipment)
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: five, typedPositions: five })
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: [], typedPositions: [] })
    expect(second.ok).toBe('resolved')
    expect(sent.map((item) => item.key)).toEqual(['key-1', 'key-1'])
    expect(server.state.shirt).toBe(5)
  })

  it('pending replay definitively refused and no new body → the refusal is shown, nothing empty is sent', async () => {
    const sent: FbsBoxShipment[] = []
    const send = vi.fn<(shipment: FbsBoxShipment) => Promise<Workspace>>(async (shipment) => {
      sent.push(shipment)
      if (sent.length === 1) throw networkFailure()
      throw new Error('409 ozon_box_quantity_exceeded')
    })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: five })
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: [], typedPositions: [] })
    expect(second.ok).toBe(false)
    expect(second.pending).toBeNull()
    expect(sent).toHaveLength(2)
  })

  it('success clears the pending, so the next add is a new action with a new key', async () => {
    const server = makeServer()
    const sent: FbsBoxShipment[] = []
    const send = vi.fn(async (shipment: FbsBoxShipment) => { sent.push(shipment); return server.apply(shipment) })
    const base = { boxId: 'box-1', send, createKey: keys(), isDefinitiveRefusal: refusal }
    const first = await sendFbsBoxShipment({ ...base, pending: null, positions: five })
    expect(first.ok).toBe(true)
    expect(first.pending).toBeNull()
    const second = await sendFbsBoxShipment({ ...base, pending: first.pending, positions: five })
    expect(second.ok).toBe(true)
    expect(sent.map((item) => item.key)).toEqual(['key-1', 'key-2'])
    expect(server.state.shirt).toBe(10)
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
