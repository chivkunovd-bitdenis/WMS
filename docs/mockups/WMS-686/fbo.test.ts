import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  createBoxes, createFboState, kizFor, linkKiz, packUnit, pickUnit, products, removeUnitFromBox, returnPickedUnit,
  takeWhole, type FboState,
} from './fboModel.ts'
import { createMockFetch } from './mockApi.ts'

// WMS-686 · C33: проверки самого макета (не продукта). Продуктовый контракт —
// backend/tests/test_wms686_fbo_kiz_contract.py и *.wms686.dom.test.tsx.

const [p1, p2] = products
const total = (state: FboState, productId: string) =>
  state.stock.filter((line) => line.productId === productId).reduce((sum, line) => sum + line.qty, 0)
  + state.picks.filter((pick) => pick.productId === productId).reduce((sum, pick) => sum + pick.qty, 0)
const must = <T,>(result: { ok: true; value: T } | { ok: false; error: string }): T => {
  if (!result.ok) throw new Error(result.error)
  return result.value
}

test('C33: макет не ходит в сеть и не создаёт задания принтеру — неизвестный маршрут и WMS Print явно отказывают', async () => {
  const original = globalThis.fetch
  let network = 0
  globalThis.fetch = async () => { network++; throw new Error('real network is forbidden') }
  try {
    const fetcher = createMockFetch()
    const unknown = await fetcher('https://wms.sellerfocus.pro/api/operations/unknown', { method: 'POST', body: '{}' })
    assert.equal(unknown.ok, false)
    const printer = await fetcher('http://127.0.0.1:17843/print', { method: 'POST', body: '{}' })
    assert.equal(printer.ok, false)
    assert.match(await printer.text(), /WMS Print не вызывается/)
    assert.equal(network, 0)
  } finally {
    globalThis.fetch = original
  }
})

test('C33: модель макета — ШК +1 сразу, КИЗ не меняет количество, остаток не списывается подбором и упаковкой', () => {
  let state = createFboState()
  const before = total(state, p1.id)
  state = must(pickUnit(state, 'demo-shipment', p1.id, 'cell-a11', 'src-inb-1'))
  const linked = must(linkKiz(state, 'demo-shipment', kizFor(p1, 'P1A0001'), { productId: p1.id, cellId: 'cell-a11', sourceId: 'src-inb-1', boxId: null }))
  state = linked.state
  assert.equal(state.picks.reduce((sum, pick) => sum + pick.qty, 0), 1)
  const again = must(linkKiz(state, 'demo-shipment', kizFor(p1, 'P1A0001'), { productId: p1.id, cellId: 'cell-a11', sourceId: 'src-inb-1', boxId: null }))
  assert.equal(again.already, true)
  assert.equal(state.links.length, 1)
  state = createBoxes(state, 'demo-shipment', 1)
  state = must(packUnit(state, 'demo-shipment', 'box-1', p1.id))
  assert.equal(total(state, p1.id), before, 'остаток = свободное + подобранное, не уменьшился')
})

test('C33: модель макета — КИЗ после ШК другого товара отклоняется, цель не переходит на ранний товар (D16)', () => {
  let state = createFboState()
  state = must(pickUnit(state, 'demo-shipment', p1.id, 'cell-a11', 'src-inb-1'))
  state = must(pickUnit(state, 'demo-shipment', p2.id, 'cell-a11', 'src-inb-1'))
  const result = linkKiz(state, 'demo-shipment', kizFor(p1, 'P1A0001'), { productId: p2.id, cellId: 'cell-a11', sourceId: 'src-inb-1', boxId: null })
  assert.equal(result.ok, false)
  const verify = must(linkKiz(state, 'demo-shipment', kizFor(p1, 'P1A0001'), { productId: null, cellId: 'cell-a11', sourceId: 'src-inb-1', boxId: null }))
  assert.equal(verify.link.productId, p1.id)
})

test('C33: модель макета — известный код «точно», после снятия без кода — «возможно», «целиком» его не переносит (R30)', () => {
  let state = createFboState()
  state = must(pickUnit(state, 'demo-shipment', p1.id, 'cell-a11', 'src-inb-1'))
  state = must(linkKiz(state, 'demo-shipment', kizFor(p1, 'P1A0001'), { productId: p1.id, cellId: 'cell-a11', sourceId: 'src-inb-1', boxId: null })).state
  state = must(returnPickedUnit(state, 'demo-shipment', kizFor(p1, 'P1A0001'))).state
  assert.deepEqual(state.known[kizFor(p1, 'P1A0001')], { sourceId: 'src-inb-1', certain: true })
  state = must(pickUnit(state, 'demo-shipment', p1.id, 'cell-a11', 'src-inb-1'))
  assert.equal(state.known[kizFor(p1, 'P1A0001')].certain, false)
  state = must(takeWhole(state, 'demo-shipment-kazan', 'INB-DEMO-001', true))
  assert.equal(state.links.some((link) => link.cis === kizFor(p1, 'P1A0001')), false)
})

test('C33: модель макета — код с неизвестным источником требует выбранного места возврата (R28)', () => {
  let state = createFboState()
  state = must(pickUnit(state, 'demo-shipment', p1.id, 'cell-a11', 'src-inb-1'))
  state = must(pickUnit(state, 'demo-shipment', p1.id, 'cell-a11', 'src-inb-2'))
  state = createBoxes(state, 'demo-shipment', 1)
  state = must(packUnit(state, 'demo-shipment', 'box-1', p1.id))
  state = must(linkKiz(state, 'demo-shipment', kizFor(p1, 'P1X0009'), { productId: p1.id, cellId: null, sourceId: null, boxId: 'box-1' })).state
  const refused = removeUnitFromBox(state, 'demo-shipment', 'box-1', p1.id, kizFor(p1, 'P1X0009'), null)
  assert.equal(refused.ok, false)
  const done = must(removeUnitFromBox(state, 'demo-shipment', 'box-1', p1.id, kizFor(p1, 'P1X0009'), { cellId: 'cell-a11', sourceId: 'src-inb-2' }))
  assert.equal(done.sourceKnown, false)
  assert.deepEqual(done.returnedTo, { cellId: 'cell-a11', sourceId: 'src-inb-2' })
})
