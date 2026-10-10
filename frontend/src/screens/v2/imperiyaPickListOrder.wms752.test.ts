import { describe, expect, it } from 'vitest'
import type { FbsPickOptionProduct, FbsPickingContext, FbsWorkspace } from './fbsApi'
import type { FbsPickingListPrintRow } from './fbsUx'
import { imperiyaOrderUnits, imperiyaWalkRows } from './imperiyaPickListOrder'

// WMS-752, владелец 10.10.2026: «если тебе нужно 5 курток собрать, значит у тебя
// 5 QR-кодов». Лист Империи идёт маршрутом вкладки «Подбор», но каждая строка —
// место, из которого берём: «Взять» из этого места и стикеры именно этих штук.

const SORTING = 'loc-sorting'

type Box = { id: string; code: string; qty: number; picked?: number }
type Row = FbsPickingListPrintRow & { key: string }

function option(productId: string, plan: number, boxes: Box[]): FbsPickOptionProduct {
  return {
    product_id: productId,
    planned_qty: plan,
    picked_qty: boxes.reduce((sum, box) => sum + (box.picked ?? 0), 0),
    locations: [{
      storage_location_id: SORTING,
      location_code: 'Без ячеек',
      available: boxes.reduce((sum, box) => sum + box.qty, 0),
      sources: boxes.map((box) => ({
        quantity: box.qty,
        available: box.qty,
        picked: box.picked ?? 0,
        is_loose: false,
        source_label: `Короб ${box.code}`,
        container_path: [{ kind: 'box', id: box.id, code: box.code, label: `Короб ${box.code}` }],
      })),
    }],
  } as unknown as FbsPickOptionProduct
}

function context(productId: string, boxes: Box[]): FbsPickingContext {
  return {
    product_id: productId,
    inbound_supplies: [],
    locations: [],
    source_groups: boxes.map((box) => ({
      key: `inbound:${box.id}`,
      title: 'П: №000096',
      date: '02.10.2026',
      lines: [`Короб ${box.code} · INB-ABC123: ${box.qty} шт.`],
      line_keys: [`${SORTING}|${box.id}`],
    })),
  } as unknown as FbsPickingContext
}

function row(key: string, orders: string[], stickers: string[], required = orders.length): Row {
  return {
    key, name: key, size: null, imageUrl: null, identifiers: [], locations: [],
    required, picked: 0, wbOrders: orders, stickerCodes: stickers, marking: 'Не требуется',
  }
}

function wbOrder(id: string, productId: string, picked = false) {
  return { marketplace: 'wb', wb_order_id: Number(id), external_order_id: null, positions: [], product: { id: productId }, pick: { status: picked ? 'picked' : 'pending' } }
}

const orders = (list: unknown[]) => list as FbsWorkspace['orders']
const placeOf = (printed: Row) => printed.sourceGroups?.[0]?.lines[0] ?? printed.sourceGroups?.[0]?.title

describe('WMS-752: лист подбора Империи — строка = место, взять и стикеры этих штук', () => {
  it('товар в нескольких коробах печатается только там, откуда берём, у каждой строки свои стикеры', () => {
    // Как Chin-2329Black 54/56 у Фадина: нужно 2, лежит в трёх коробах по одной-две штуки.
    const boxes = [
      { id: 'b1', code: 'КР-000001', qty: 1 },
      { id: 'b2', code: 'КР-000016', qty: 2 },
      { id: 'b3', code: 'КР-000019', qty: 2 },
    ]
    const printed = imperiyaWalkRows(
      [row('jacket', ['5993208839', '5994493421'], ['5887779 6759', '5889887 0973'])],
      [option('jacket', 2, boxes)],
      [context('jacket', boxes)],
      imperiyaOrderUnits(orders([wbOrder('5993208839', 'jacket'), wbOrder('5994493421', 'jacket')])),
    )
    expect(printed.map((one) => [placeOf(one), one.required, one.wbOrders, one.stickerCodes])).toEqual([
      ['Короб КР-000001: 1 шт.', 1, ['5993208839'], ['5887779 6759']],
      ['Короб КР-000016: 2 шт.', 1, ['5994493421'], ['5889887 0973']],
    ])
    expect(printed.every((one) => one.marking === 'Не требуется')).toBe(true)
  })

  it('из короба берётся не больше, чем в нём лежит; сумма «Взять» и стикеров равна заказам', () => {
    // Как Chin-56005black 54: нужно 3, в первом коробе одна штука, во втором пять.
    const boxes = [
      { id: 'b15', code: 'КР-000015', qty: 1 },
      { id: 'b141', code: 'КР-000141', qty: 5 },
    ]
    const ids = ['5992468793', '5993537781', '5995552101']
    const printed = imperiyaWalkRows(
      [row('black54', ids, ['5885817 7865', '5888112 7379', '5889993 2576'])],
      [option('black54', 3, boxes)],
      [context('black54', boxes)],
      imperiyaOrderUnits(orders(ids.map((id) => wbOrder(id, 'black54')))),
    )
    expect(printed.map((one) => [placeOf(one), one.required, one.stickerCodes.length])).toEqual([
      ['Короб КР-000015: 1 шт.', 1, 1],
      ['Короб КР-000141: 5 шт.', 2, 2],
    ])
    expect(printed.flatMap((one) => one.wbOrders)).toEqual(ids)
  })

  it('уже подобранный заказ уходит в строку «Подобрано», в маршрут — только оставшиеся', () => {
    const boxes = [{ id: 'b7', code: 'КР-000007', qty: 4, picked: 1 }]
    const printed = imperiyaWalkRows(
      [row('coat', ['111', '222'], ['1000001 0001', '1000002 0002'])],
      [option('coat', 2, boxes)],
      [context('coat', boxes)],
      imperiyaOrderUnits(orders([wbOrder('111', 'coat', true), wbOrder('222', 'coat')])),
    )
    expect(printed.map((one) => [one.sourceGroups?.[0]?.title, one.required, one.wbOrders])).toEqual([
      ['П: №000096 от 02.10.2026', 1, ['222']],
      ['Подобрано', 1, ['111']],
    ])
  })

  it('нехватка на местах печатается строкой «Нет текущего остатка» со своими стикерами', () => {
    const boxes = [{ id: 'b9', code: 'КР-000009', qty: 1 }]
    const printed = imperiyaWalkRows(
      [row('scarf', ['301', '302'], ['3000001 0301', '3000002 0302'])],
      [option('scarf', 2, boxes)],
      [context('scarf', boxes)],
      imperiyaOrderUnits(orders([wbOrder('301', 'scarf'), wbOrder('302', 'scarf')])),
    )
    expect(printed.map((one) => [one.sourceGroups?.[0]?.title, one.required, one.stickerCodes])).toEqual([
      ['П: №000096 от 02.10.2026', 1, ['3000001 0301']],
      ['Нет текущего остатка', 1, ['3000002 0302']],
    ])
  })

  it('отправление Ozon с двумя штуками товара — один стикер на две штуки', () => {
    const boxes = [{ id: 'b3', code: 'КР-000003', qty: 6 }]
    const posting = {
      marketplace: 'ozon', wb_order_id: 9001, external_order_id: '0123-4567-1', product: { id: null }, pick: { status: 'pending' },
      positions: [{ product_id: 'mug', quantity: 2, picked_quantity: 0 }],
    }
    const printed = imperiyaWalkRows(
      [row('mug', ['0123-4567-1'], ['OZN-1'], 2)],
      [option('mug', 2, boxes)],
      [context('mug', boxes)],
      imperiyaOrderUnits(orders([posting])),
    )
    expect(printed.map((one) => [one.required, one.wbOrders, one.stickerCodes])).toEqual([
      [2, ['0123-4567-1'], ['OZN-1']],
    ])
  })
})
