// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CardFixture, button, click, deferred, json, order, settle, workspace } from './fbsSupplyCard.contract-fixture'
vi.mock('../ff/FfPackagingPage', () => ({}))
vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
let f: CardFixture
beforeEach(() => { f = new CardFixture() })
afterEach(() => f.dispose())

it.each(['wb', 'ozon'] as const)('C1 deletes an empty %s card from every working stage and closes after success', async marketplace => {
  f.current = workspace(marketplace, [])
  for (const stage of ['picking', 'packing', 'boxes']) {
    await f.render(stage)
    expect(button('Удалить поставку'), 'Действие удаления пустой поставки отсутствует').toBeTruthy()
  }
  f.hook = async c => c.method === 'DELETE' && c.path === '/operations/fbs-supplies/supply-a'
    ? new Response(null, { status: 204 }) : undefined
  await click(button('Удалить поставку'))
  expect(f.calls.filter(c => c.method === 'DELETE').map(c => c.path)).toEqual(['/operations/fbs-supplies/supply-a'])
  expect(f.close).toHaveBeenCalledTimes(1)
})

it.each(['new', 'packed', 'cancelled'])('C3 disables deletion with a linked %s order', async status => {
  f.current = workspace('wb', [order('o1', { status })])
  await f.render('boxes')
  expect(button('Удалить поставку'), 'Нужна видимая недоступная кнопка непустой поставки').toBeTruthy()
  expect(button('Удалить поставку')!.disabled).toBe(true)
  expect(f.calls.some(c => c.method === 'DELETE')).toBe(false)
})

it('C6 preserves card on refusal and confirms missing card after a lost successful reply', async () => {
  f.current = workspace('wb', [])
  await f.render('boxes')
  let deleted = false
  f.hook = async c => {
    if (c.method === 'DELETE') return json({ detail: { message: 'Удаление отказало' } }, 409)
    return undefined
  }
  await click(button('Удалить поставку'))
  expect(document.body.textContent).toContain('Удаление отказало')
  expect(f.close).not.toHaveBeenCalled()
  f.hook = async c => {
    if (c.method === 'DELETE') { deleted = true; throw new TypeError('Ответ потерян') }
    if (deleted && c.path.endsWith('/workspace')) return json({ detail: 'not found' }, 404)
    if (deleted && c.path.endsWith('/worklist')) return json({ items: [], total: 0 })
    return undefined
  }
  const sinceLostReply = f.calls.length
  await click(button('Удалить поставку'))
  expect(f.calls.slice(sinceLostReply).some(c => c.method === 'GET' && /workspace|worklist/.test(c.path))).toBe(true)
  expect(f.close).toHaveBeenCalledTimes(1)
})

it('C6 late deletion of A cannot close or change B', async () => {
  f.current = workspace('wb', [])
  await f.render('boxes')
  const late = deferred<Response>()
  f.hook = async c => c.method === 'DELETE' ? late.promise : undefined
  await click(button('Удалить поставку'))
  f.current.supply.id = 'supply-b'; f.current.supply.name = 'Поставка B'
  await f.render('packing')
  late.resolve(new Response(null, { status: 204 })); await settle()
  expect(f.close).not.toHaveBeenCalled()
  expect(document.body.textContent).toContain('Поставка B')
})
