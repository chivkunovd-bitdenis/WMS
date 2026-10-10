// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CardFixture, box, button, click, deferred, input, json, order, settle, workspace } from './fbsSupplyCard.contract-fixture'
vi.mock('../ff/FfPackagingPage', () => ({}))
vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
let f: CardFixture
beforeEach(() => { f = new CardFixture(); vi.spyOn(window, 'confirm').mockReturnValue(true) })
afterEach(() => { f.dispose(); vi.restoreAllMocks() })
const dialog = () => [...document.querySelectorAll('[role="dialog"]')].find(n => n.textContent?.includes('Добавить товары в короб'))!
const quantities = () => [...dialog().querySelectorAll<HTMLInputElement>('input[type="number"]')]
const search = () => dialog().querySelector<HTMLInputElement>('input:not([type="number"]):not([type="checkbox"])')!
const checkedPositions = () => [...dialog().querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].filter(n => n.checked).map(n => n.closest('[data-testid]')!.getAttribute('data-testid')!.replace('fbs-box-assign-position-', ''))
async function openBox() {
  await f.render('boxes')
  await click(button('Добавить товары'))
  expect(dialog()).toBeTruthy()
}
async function all() { await click(button('Добавить все', dialog())) }
const assigned = () => f.calls.filter(c => /\/boxes\/[^/]+\/orders$/.test(c.path) && c.method === 'POST')
function wb() {
  const p = order('o1').product
  f.current = workspace('wb', [order('o1'), order('o2', { product: p }), order('o3', { product: p }), order('o4'), order('o5')])
  f.current.boxes = [box('box-a', 1, ['o3']), box('box-b', 2, ['o5'])]
}
function ozon(existing = true) {
  const positions = (id: string) => [1, 2, 3].map(n => ({ id: `${id}-p${n}`, product_id: `prod-${id}-${n}`, name: `${id} позиция ${n}`, sku: `${id}-${n}`, quantity: n + 1, picked_quantity: 0 }))
  f.current = workspace('ozon', [order('o1', { positions: positions('o1') }), order('o2', { positions: positions('o2') })])
  f.current.boxes = [box('box-a', 1, existing ? ['o1'] : [], existing ? ['o1-p1'] : []), box('box-b', 2, ['o2'], ['o2-p3'])]
}

it('C1 WB fills full unassigned maxima twice despite a partial draft and search, without writes', async () => {
  wb(); await openBox()
  await input(quantities()[0], '1'); await input(search(), 'Товар o1')
  const before = structuredClone(f.current); const writes = f.writes().length
  await all(); await all()
  expect(search().value).toBe('')
  expect(quantities().map(n => n.value)).toEqual(['2', '1'])
  expect(dialog()).toBeTruthy(); expect(f.current).toEqual(before); expect(f.writes()).toHaveLength(writes)
})

it('C2 WB confirms only edited full draft and recalculates remaining without changing packing metadata', async () => {
  wb(); const before = structuredClone(f.current.orders)
  await openBox(); await all(); await input(quantities()[0], '1')
  await click(button('Добавить', dialog()))
  expect(assigned().map(c => c.body)).toEqual([{ order_ids: ['o1', 'o4'] }])
  expect(f.current.boxes[0].assigned_order_ids).toEqual(['o3', 'o1', 'o4'])
  expect(f.current.orders).toEqual(before)
  await openBox(); expect(quantities().map(n => n.max)).toEqual(['1'])
})

it('C3 cancelling the filled dialog does not save or print and reopening starts empty', async () => {
  wb(); await openBox(); const before = structuredClone(f.current); const writes = f.writes().length
  await all()
  await click(dialog().closest('.MuiDialog-root')!.querySelector('.MuiBackdrop-root'))
  expect(f.current).toEqual(before); expect(f.writes()).toHaveLength(writes)
  await openBox(); expect(quantities().every(n => n.value === '')).toBe(true)
})

it('C4 Ozon uses the existing shipment even while searching for the other shipment', async () => {
  ozon(); await openBox(); await input(search(), 'o2'); const before = structuredClone(f.current)
  await all()
  expect(search().value).toBe(''); expect(checkedPositions()).toEqual(['o1-p2', 'o1-p3'])
  expect(f.current).toEqual(before)
  await click(button('Добавить', dialog()))
  expect(assigned()[0].body).toMatchObject({ order_ids: [], order_product_ids: ['o1-p2', 'o1-p3'] })
  expect(f.current.boxes[1]).toEqual(before.boxes[1])
})

it.each([true, false])('C5 empty Ozon box honors current selection or original first order, manual=%s', async manual => {
  ozon(false); await openBox()
  if (manual) await click(dialog().querySelector('[data-testid="fbs-box-assign-position-o2-p1"] input'))
  await input(search(), manual ? 'o1' : 'o2'); await all()
  expect(search().value).toBe('')
  expect(checkedPositions()).toEqual(manual ? ['o2-p1', 'o2-p2'] : ['o1-p1', 'o1-p2', 'o1-p3'])
})

it('C5 already assembled Ozon shipment is never made assignable by add-all', async () => {
  ozon(false); f.current.boxes[1].ozon_assembled = true
  await openBox(); await click(dialog().querySelector('[data-testid="fbs-box-assign-position-o2-p1"] input'))
  await all()
  expect(checkedPositions().some(id => id.startsWith('o2'))).toBe(false)
  expect(f.writes()).toEqual([])
})

it.each(['empty', 'distributed', 'unknown-products'])('C6 %s neither saves an empty set nor merges unrelated unknown products', async state => {
  wb()
  if (state === 'empty') f.current.orders = []
  if (state === 'distributed') f.current.boxes[0].assigned_order_ids = f.current.orders.map(o => o.id)
  if (state === 'unknown-products') f.current.orders = [order('o1', { product: { ...order('o1').product, id: null } }), order('o2', { product: { ...order('o2').product, id: null } })]
  await openBox(); await all()
  expect(f.writes()).toEqual([])
  if (state === 'unknown-products') expect(quantities().map(n => n.value)).toEqual(['1', '1'])
  else expect(button('Добавить', dialog())!.disabled).toBe(true)
  expect(f.current.boxes).toHaveLength(2)
})

it('C8 refusal retains draft and late response cannot replace another supply', async () => {
  wb(); await openBox(); await all()
  f.hook = async c => /\/boxes\/[^/]+\/orders$/.test(c.path) ? json({ detail: { message: 'Назначение отказало' } }, 409) : undefined
  await click(button('Добавить', dialog()))
  expect(document.body.textContent).toContain('Назначение отказало')
  expect(quantities().map(n => n.value)).toEqual(['2', '1'])
  const late = deferred<Response>(); const old = structuredClone(f.current)
  f.hook = async c => /\/boxes\/[^/]+\/orders$/.test(c.path) ? late.promise : undefined
  await click(button('Добавить', dialog()))
  f.current = workspace(); f.current.supply.id = 'supply-b'; f.current.supply.name = 'Поставка B'; f.current.boxes = [box('new-box', 9)]
  await f.render('boxes'); late.resolve(json(old)); await settle()
  expect(document.body.textContent).toContain('Поставка B'); expect(document.body.textContent).not.toContain('Добавить товары в короб 1')
})
