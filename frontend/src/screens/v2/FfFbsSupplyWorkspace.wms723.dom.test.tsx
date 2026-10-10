// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CardFixture, button, click, deferred, json, order, settle, workspace } from './fbsSupplyCard.contract-fixture'
const { openPrint } = vi.hoisted(() => ({ openPrint: vi.fn() }))
vi.mock('../ff/FfPackagingPage', () => ({}))
vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
vi.mock('../../utils/useMarkingCodePrint', () => ({ useMarkingCodePrint: () => ({ openPrint, dialog: null }) }))
let f: CardFixture
beforeEach(() => { f = new CardFixture() })
afterEach(() => { f.dispose(); vi.restoreAllMocks() })

it.each(['wb', 'ozon'] as const)('C1 removes composition for %s and preserves order identities on refresh', async marketplace => {
  f.current = workspace(marketplace, [order('o1'), order('o2')])
  await f.render()
  expect([...document.querySelectorAll('[role="tab"]')].map(t => t.textContent?.replace(' ✓', ''))).toEqual(['Подбор', 'Упаковка и маркировка', 'Короба'])
  expect(document.body.textContent).not.toContain('Состав поставки')
  await f.render()
  expect(f.current.orders.map(o => o.id)).toEqual(['o1', 'o2'])
  expect(f.writes()).toEqual([])
})

it.each(['draft', 'assembling', 'packed'].flatMap(status => ['picking', 'packing', 'boxes'].map(stage => [status, stage])))('C2 adds from common actions in %s on %s without moving stage', async (status, stage) => {
  f.current.supply.status = status
  await f.render(stage)
  const add = button('Добавить заказы')
  expect(add, 'Добавление должно быть в общей части каждой вкладки').toBeTruthy()
  expect(add!.closest('[role="tablist"]')).toBeNull()
  await click(add)
  await click(document.querySelector('[data-testid="fbs-05-workspace-add-orders-table"] input[type="checkbox"]'))
  await click(document.querySelector('[data-testid="fbs-05-workspace-add-orders-submit"]'))
  expect(f.calls.filter(c => c.path.endsWith('/orders/batch')).map(c => c.body.order_ids)).toEqual([['new']])
  expect(f.current.orders.filter(o => o.id === 'new')).toHaveLength(1)
  expect(window.sessionStorage.getItem('wms:fbs:supply-a:stage')).toBe(stage)
  expect([...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')].every(t => !t.disabled)).toBe(true)
})

it.each(['wb', 'ozon'] as const)('C3 retains common history and picking-list contents for %s', async marketplace => {
  f.current = workspace(marketplace)
  if (marketplace === 'ozon') f.current.orders[0].positions = [{ id: 'position', product_id: 'product-o1', name: 'Товар o1', quantity: 3, picked_quantity: 0 }] as any
  const write = vi.fn()
  vi.spyOn(window, 'open').mockReturnValue({ opener: null, document: { write, open: vi.fn(), close: vi.fn() }, close: vi.fn(), focus: vi.fn(), print: vi.fn() } as any)
  for (const stage of ['packing', 'boxes']) {
    await f.render(stage)
    await click(document.querySelector('[data-testid="fbs-supply-history-open"]'))
    expect(f.calls.some(c => c.path === '/operations/fbs-supplies/supply-a/history')).toBe(true)
    await click(button('Закрыть', [...document.querySelectorAll('[role="dialog"]')].at(-1)!))
  }
  await f.render('picking')
  await click(button('Печать листа подбора'))
  expect(write.mock.calls.flat().join(' ')).toContain('Товар o1')
  const html = new DOMParser().parseFromString(write.mock.calls.at(-1)![0], 'text/html')
  expect(html.querySelector('tbody .quantity')?.textContent).toBe(marketplace === 'ozon' ? '3' : '1')
  expect(html.querySelector('tbody .orders')?.textContent).toContain(marketplace === 'ozon' ? 'o1' : '101')
})

it.each([null, 'composition', 'packing', 'boxes'])('C4 restores %s and keeps WB navigation through reread', async saved => {
  await f.render(saved ?? undefined)
  const expected = saved === null || saved === 'composition' ? 'picking' : saved
  const labels: Record<string, string> = { picking: 'Подбор', packing: 'Упаковка и маркировка', boxes: 'Короба' }
  expect(document.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(labels[expected])
  await f.render()
  expect(document.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(labels[expected])
  expect([...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')].every(t => !t.disabled)).toBe(true)
})

it.each(['packing', 'boxes', 'tracking'])('C4 retains late server stage %s without a saved choice', async stage => {
  f.current.stage = stage as any
  await f.render()
  expect(document.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(stage === 'packing' ? 'Упаковка и маркировка' : 'Короба')
})

it.each([['wb', 'in_delivery'], ['wb', 'done'], ['ozon', 'assembling']])('C5 does not offer working add-orders for %s %s', async (marketplace, status) => {
  f.current = workspace(marketplace as 'wb' | 'ozon')
  f.current.supply.status = status
  await f.render('composition')
  expect(button('Добавить заказы')?.disabled ?? true).toBe(true)
  expect(f.calls.some(c => c.path.endsWith('/orders/batch'))).toBe(false)
})

it('C6 retains rejected add selection and isolates a late response from another supply', async () => {
  await f.render('packing')
  await click(button('Добавить заказы'))
  await click(document.querySelector('[data-testid="fbs-05-workspace-add-orders-table"] input'))
  f.hook = async c => c.path.endsWith('/orders/batch') ? json({ detail: { message: 'Отказ добавления' } }, 409) : undefined
  await click(document.querySelector('[data-testid="fbs-05-workspace-add-orders-submit"]'))
  expect(document.querySelector<HTMLInputElement>('[data-testid="fbs-05-workspace-add-orders-table"] input')?.checked).toBe(true)
  expect(document.body.textContent).toContain('Отказ добавления')
  const late = deferred<Response>()
  f.hook = async c => c.path.endsWith('/orders/batch') ? late.promise : undefined
  await click(document.querySelector('[data-testid="fbs-05-workspace-add-orders-submit"]'))
  const old = structuredClone(f.current)
  f.current = workspace(); f.current.supply.id = 'supply-b'; f.current.supply.name = 'Поставка B'
  await f.render('boxes')
  late.resolve(json(old)); await settle()
  expect(document.body.textContent).toContain('Поставка B')
  expect(document.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain('Короба')
  expect(f.close).not.toHaveBeenCalled()
})
