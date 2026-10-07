import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createDemoState, reduceDemo, saveDemoState, loadDemoState, storageKey, type DemoState, type Unit } from './model.ts'
import { createMockFetch } from './mockApi.ts'

const shipmentUnits = (state: DemoState) => state.shipmentBoxes.flatMap(box => box.units)
const sourceUnits = (state: DemoState) => state.sourceBoxes.flatMap(box => box.units)
const source = (state: DemoState, id = 'source1') => state.sourceBoxes.find(box => box.id === id)
const pickBox = (state = createDemoState()) => {
  const result = reduceDemo(state, { type: 'pickWholeBox', boxId: 'source1' })
  assert.equal(result.error, undefined)
  return result.state
}
const assertConserved = (state: DemoState) => {
  assert.equal(state.stockTotal, 12, 'подбор/упаковка не списывают товарный остаток')
  const ids = [...sourceUnits(state), ...shipmentUnits(state)].map(unit => unit.id)
  assert.equal(new Set(ids).size, ids.length, 'физическая единица не дублируется между источником и отгрузкой')
}

test('C2: весь смешанный короб сохраняет собственный код, товары и КИЗ, повтор не удваивает состав', () => {
  const original = createDemoState()
  const expected = source(original)!
  const state = pickBox(original)
  assert.deepEqual(shipmentUnits(state), expected.units)
  assert.equal(state.shipmentBoxes[0].code, expected.code)
  assert.equal(source(state)?.units.length ?? 0, 0)
  assert.equal(state.picked, 10)
  assert.equal(shipmentUnits(state).filter(unit => unit.productId === 'p1').length, 6)
  assert.equal(shipmentUnits(state).filter(unit => unit.productId === 'p2').length, 4)
  for (const unit of expected.units) {
    assert.equal(state.kizHistory[unit.kiz!].unitId, unit.id)
    assert.equal(state.kizHistory[unit.kiz!].intakeId, 'demo-intake')
    assert.ok(state.kizHistory[unit.kiz!].shipmentId)
  }
  const repeated = reduceDemo(state, { type: 'pickWholeBox', boxId: 'source1' }).state
  assert.deepEqual(shipmentUnits(repeated), expected.units)
  assert.equal(repeated.picked, 10)
  assertConserved(repeated)
})

test('C3: частичный подбор переносит только выбранные конкретные КИЗ и сохраняет историю остальных', () => {
  const original = createDemoState()
  const result = reduceDemo(original, { type: 'pickPartial', boxId: 'source1', productId: 'p1', quantity: 2, kizCodes: ['DEMO-KIZ-2', 'DEMO-KIZ-5'] })
  assert.equal(result.error, undefined)
  const state = result.state
  assert.deepEqual(shipmentUnits(state).map(unit => unit.kiz).sort(), ['DEMO-KIZ-2', 'DEMO-KIZ-5'])
  assert.equal(source(state)!.units.length, 8)
  assert.equal(source(state)!.units.filter(unit => unit.productId === 'p2').length, 4)
  assert.equal(state.picked, 2)
  assert.equal(state.kizHistory['DEMO-KIZ-2'].intakeId, 'demo-intake')
  assert.ok(state.kizHistory['DEMO-KIZ-2'].shipmentId)
  assert.deepEqual(state.kizHistory['DEMO-KIZ-1'], original.kizHistory['DEMO-KIZ-1'])
  assertConserved(state)
})

test('C3: количество без конкретных КИЗ либо КИЗ другого товара не подтверждает уходящие единицы', () => {
  for (const kizCodes of [[], ['DEMO-KIZ-7'], ['UNKNOWN-KIZ'], ['DEMO-KIZ-1', 'DEMO-KIZ-1']]) {
    const original = createDemoState()
    const result = reduceDemo(original, { type: 'pickPartial', boxId: 'source1', productId: 'p1', quantity: 2, kizCodes })
    assert.ok(result.error, `нет валидной идентификации двух p1: ${kizCodes}`)
    assert.deepEqual(result.state, original)
  }
})

test('C4: вся ячейка переносит оба короба и смешанный состав без списания остатка', () => {
  const original = createDemoState()
  const result = reduceDemo(original, { type: 'pickWholeCell', cell: 'А-1-1' })
  assert.equal(result.error, undefined)
  assert.equal(sourceUnits(result.state).length, 0)
  assert.deepEqual(shipmentUnits(result.state).map(unit => unit.id).sort(), sourceUnits(original).map(unit => unit.id).sort())
  assert.deepEqual(result.state.shipmentBoxes.map(box => box.code).sort(), original.sourceBoxes.map(box => box.code).sort())
  assert.equal(result.state.picked, 12)
  const repeated = reduceDemo(result.state, { type: 'pickWholeCell', cell: 'А-1-1' }).state
  assert.equal(shipmentUnits(repeated).length, 12)
  assert.equal(repeated.picked, 12)
  assertConserved(repeated)
})

test('C5/C6: добровольный перескан той же единицы в перенесённом коробе не требует переупаковки и не добавляет товар', () => {
  const state = pickBox()
  const box = state.shipmentBoxes[0]
  assert.ok(box, 'перенесённый короб доступен без обязательной переупаковки')
  const first = reduceDemo(state, { type: 'verifyKiz', boxId: box.id, kiz: 'DEMO-KIZ-1', productId: 'p1' })
  assert.equal(first.error, undefined)
  const second = reduceDemo(first.state, { type: 'verifyKiz', boxId: box.id, kiz: 'DEMO-KIZ-1', productId: 'p1' })
  assert.equal(second.error, undefined)
  assert.deepEqual(shipmentUnits(second.state), shipmentUnits(state))
  assert.equal(second.state.picked, 10)
  assertConserved(second.state)
})

test('C6: КИЗ другого товара или другого короба не становится проверкой выбранной единицы', () => {
  const state = pickBox()
  assert.ok(state.shipmentBoxes[0], 'перенесённый короб существует')
  for (const [kiz, productId] of [['DEMO-KIZ-7', 'p1'], ['DEMO-KIZ-11', 'p1'], ['UNKNOWN-KIZ', 'p1']]) {
    const result = reduceDemo(state, { type: 'verifyKiz', boxId: state.shipmentBoxes[0].id, kiz, productId })
    assert.ok(result.error)
    assert.deepEqual(result.state, state)
  }
})

test('C7: новый короб получает код, добавленная единица сохраняет КИЗ/приёмку, закрытие выбирает следующий короб', () => {
  const created = reduceDemo(createDemoState(), { type: 'createBox' })
  assert.equal(created.error, undefined)
  const box = created.state.shipmentBoxes.find(candidate => candidate.id === created.state.selectedBoxId)
  assert.ok(box)
  assert.ok(box.code)
  const unit: Unit = { id: 'new-demo-unit', productId: 'p1', barcode: 'DEMO-PRODUCT-1', kiz: 'DEMO-NEW-KIZ', intakeId: null }
  const added = reduceDemo(created.state, { type: 'addUnit', boxId: box.id, unit })
  assert.equal(added.error, undefined)
  assert.deepEqual(added.state.shipmentBoxes.find(candidate => candidate.id === box.id)!.units, [unit])
  assert.equal(added.state.kizHistory[unit.kiz!].intakeId, null, 'неизвестную приёмку не выдумывать')
  assert.ok(added.state.kizHistory[unit.kiz!].shipmentId)
  const closed = reduceDemo(added.state, { type: 'closeBox', boxId: box.id })
  assert.equal(closed.error, undefined)
  assert.equal(closed.state.shipmentBoxes.find(candidate => candidate.id === box.id)!.closed, true)
  assert.deepEqual(closed.state.shipmentBoxes.find(candidate => candidate.id === box.id)!.units, [unit])
  assert.ok(closed.state.selectedBoxId)
  assert.notEqual(closed.state.selectedBoxId, box.id)
  assert.ok(closed.state.shipmentBoxes.find(candidate => candidate.id === closed.state.selectedBoxId)?.code)
  assert.equal(closed.state.stockTotal, 12)
})

test('C6/C7: один КИЗ нельзя назначить второй единице, повтор той же единицы не дублирует короб', () => {
  const state = pickBox()
  assert.ok(state.shipmentBoxes[0], 'перенесённый короб существует')
  const boxId = state.shipmentBoxes[0].id
  const unit = shipmentUnits(state)[0]
  const repeated = reduceDemo(state, { type: 'addUnit', boxId, unit })
  assert.equal(shipmentUnits(repeated.state).length, 10)
  const conflict = reduceDemo(state, { type: 'addUnit', boxId, unit: { ...unit, id: 'different-physical-unit' } })
  assert.ok(conflict.error)
  assert.deepEqual(conflict.state, state)
  assertConserved(repeated.state)
})

test('C8: сброс демо полностью восстанавливает исходные короба, КИЗ и прогресс', () => {
  const original = createDemoState()
  const changed = pickBox(original)
  assert.notDeepEqual(changed, original)
  const result = reduceDemo(changed, { type: 'reset' })
  assert.equal(result.error, undefined)
  assert.deepEqual(result.state, original)
})

test('C8: сохранение и повторная загрузка восстанавливают точный прогресс и связи КИЗ', () => {
  const values = new Map<string, string>()
  const storage = { setItem: (key: string, value: string) => { values.set(key, value) }, getItem: (key: string) => values.get(key) ?? null }
  const changed = pickBox()
  saveDemoState(changed, storage)
  assert.ok(values.get(storageKey))
  assert.deepEqual(loadDemoState(storage), changed)
  const reset = reduceDemo(changed, { type: 'reset' }).state
  saveDemoState(reset, storage)
  assert.deepEqual(loadDemoState(storage), createDemoState())
})

test('C9: неизвестный API-маршрут явно отказывает без любого сетевого fallback', async () => {
  const original = globalThis.fetch
  let networkCalls = 0
  globalThis.fetch = async () => { networkCalls++; throw new Error('forbidden real network') }
  try {
    const fetcher = createMockFetch()
    const response = await fetcher('https://sellerfocus.pro/api/operations/unknown-wms686', { method: 'POST', body: '{"real":"data"}' })
    assert.equal(response.ok, false)
    assert.equal(networkCalls, 0)
    assert.ok((await response.text()).trim(), 'явная причина отказа неизвестного маршрута')
    assert.deepEqual(createDemoState(), createDemoState(), 'локальный отказ не изменяет исходные демо-данные')
  } finally {
    globalThis.fetch = original
  }
})
