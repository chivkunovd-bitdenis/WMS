// @vitest-environment jsdom
import { act } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CardFixture, box, button, click, deferred, json, order, settle, workspace } from './fbsSupplyCard.contract-fixture'
vi.mock('../ff/FfPackagingPage', () => ({}))
vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
let f: CardFixture
beforeEach(() => { f = new CardFixture() })
afterEach(() => f.dispose())
const dialog = () => [...document.querySelectorAll('[role="dialog"]')].find(node => node.textContent?.includes('Добавить товары в короб'))

async function openBox(marketplace: 'wb' | 'ozon' = 'wb', supplyId = 'supply-a') {
  const positions = [{ id: 'p1', product_id: 'prod-o1', name: 'Позиция 1', quantity: 2, picked_quantity: 0 }]
  f.current = workspace(marketplace, [order('o1', { positions: marketplace === 'ozon' ? positions : [] })])
  f.current.supply.id = supplyId
  f.current.boxes = [box('box-a', 1)]
  await f.render('boxes')
  await click(button('Добавить товары'))
  await click(button('Добавить все', dialog()))
}

it.each(['wb', 'ozon'] as const)('WMS-727 %s refusal is visible inside the box dialog and keeps the draft for retry', async marketplace => {
  await openBox(marketplace)
  const values = () => [...dialog()!.querySelectorAll<HTMLInputElement>('input[type="number"],input[type="checkbox"]')].map(node => [node.value, node.checked])
  const draft = values()
  f.hook = async call => call.method === 'POST' && /\/boxes\/[^/]+\/orders$/.test(call.path)
    ? json({ detail: { message: 'Этот заказ уже назначен другому коробу' } }, 409) : undefined
  await click(button('Добавить', dialog()))
  expect(dialog()!.querySelector('[role="alert"]')?.textContent).toContain('Этот заказ уже назначен другому коробу')
  expect(values()).toEqual(draft)
  expect(button('Добавить', dialog())!.disabled).toBe(false)
  f.hook = undefined
  await click(button('Добавить', dialog()))
  // The existing MUI dialog leaves through its normal fade transition.
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 250)) })
  expect(dialog()).toBeUndefined()
})

it('WMS-727 late refusal from A never appears inside the newly opened box dialog of B', async () => {
  await openBox()
  const late = deferred<Response>()
  f.hook = async call => call.method === 'POST' ? late.promise : undefined
  await click(button('Добавить', dialog()))
  f.hook = undefined
  await openBox('wb', 'supply-b')
  late.resolve(json({ detail: { message: 'Ошибка старой поставки A' } }, 409))
  await settle()
  expect(dialog()).toBeTruthy()
  expect(dialog()!.textContent).not.toContain('Ошибка старой поставки A')
  expect(document.body.textContent).not.toContain('Ошибка старой поставки A')
})
