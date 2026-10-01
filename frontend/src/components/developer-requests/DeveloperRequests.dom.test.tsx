// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { BrowserRouter, MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DeveloperRequests } from './DeveloperRequests'
import { draftStorageKey } from './draft'
import type { RequestIdentity, RequestPayload } from './draft'

vi.setConfig({ testTimeout: 20000 })

const identity = { id: 'user-a', tenant_id: 'tenant-a', seller_id: 'shop-a' }
let root: Root
let host: HTMLDivElement
let fetcher: ReturnType<typeof vi.fn>
const initialPath = '/app/ff/fbs?private=do-not-send#private-fragment'
function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }) }
function record(payload: RequestPayload, id = 'saved-1') {
  return { id, ...payload, title: payload.description || payload.screen, status: 'review', created_at: '2026-10-01T12:00:00Z', updated_at: '2026-10-01T12:00:00Z' }
}
async function render(me: RequestIdentity = identity) {
  await act(async () => root.render(<MemoryRouter initialEntries={[initialPath]}><DeveloperRequests me={me} token="fixture-token" /></MemoryRouter>))
}
function button(text: string) {
  const matches = [...document.querySelectorAll('button')].filter((item) => item.textContent === text || item.getAttribute('aria-label') === text)
  const value = matches.find((item) => item.getAttribute('role') !== 'tab') ?? matches[0]
  expect(value, text).toBeTruthy()
  return value as HTMLButtonElement
}
async function click(text: string) { await act(async () => button(text).click()) }
function field(label: string) {
  const node = [...document.querySelectorAll('label')].find((item) => item.textContent?.startsWith(label))!
  expect(node, label).toBeTruthy()
  return document.getElementById(node.htmlFor) as HTMLInputElement | HTMLTextAreaElement
}
async function fill(label: string, value: string) {
  await act(async () => {
    const input = field(label)
    const prototype = input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function selectType(type: 'bug' | 'improvement') {
  await act(async () => {
    const select = document.querySelector('select')!
    select.value = type
    select.dispatchEvent(new Event('change', { bubbles: true }))
  })
}
function payloads(): RequestPayload[] { return fetcher.mock.calls.filter(([, init]) => init?.method === 'POST').map(([, init]) => JSON.parse(init.body)) }

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  localStorage.clear()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  fetcher = vi.fn(async (_url, init) => init?.method === 'POST' ? response(record(JSON.parse(init.body))) : response([]))
  vi.stubGlobal('fetch', fetcher)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); window.history.replaceState(null, '', '/'); vi.unstubAllGlobals() })

describe('WMS-624 developer requests', () => {
  it('restores both forms on close/remount and isolates clearing by tenant, user and effective seller', async () => {
    await render(); await click('Задача разработчикам'); await fill('Описание ошибки', 'Мой текст ошибки')
    await selectType('improvement'); await fill('Экран / процесс', 'Упаковка'); await fill('В чём сейчас проблема', 'Проблема'); await fill('Как можно улучшить', 'Предложение')
    await click('Отменить'); await click('Задача разработчикам')
    expect(field('Как можно улучшить').value).toBe('Предложение')
    await selectType('bug'); expect(field('Описание ошибки').value).toBe('Мой текст ошибки')
    const original = localStorage.getItem(draftStorageKey(identity))
    for (const other of [{ ...identity, id: 'user-b' }, { ...identity, tenant_id: 'tenant-b' }, { ...identity, active_seller_id: 'shop-b' }]) {
      await render(other); await click('Задача разработчикам'); expect(field('Описание ошибки').value).toBe('')
      await fill('Описание ошибки', 'Чужой текст'); await click('Очистить черновик')
      expect(localStorage.getItem(draftStorageKey(identity))).toBe(original)
    }
    await render(); await click('Задача разработчикам'); expect(field('Описание ошибки').value).toBe('Мой текст ошибки')
    await click('Мои заявки'); await click('Новая заявка'); expect(field('Описание ошибки').value).toBe('Мой текст ошибки')
    expect(payloads()).toHaveLength(0)
  })
  it('validates each improvement field inline; sends only active fields and pathname; clears after acknowledged save', async () => {
    await render(); await click('Задача разработчикам'); await fill('Описание ошибки', 'Не отправлять скрытое поле'); await selectType('improvement')
    await fill('Экран / процесс', '   '); await click('Отправить')
    expect(document.querySelectorAll('[aria-invalid="true"]').length).toBe(3); expect(payloads()).toHaveLength(0)
    await fill('Экран / процесс', 'Упаковка'); await fill('В чём сейчас проблема', 'Проблема'); await fill('Как можно улучшить', 'Улучшение'); await click('Отправить')
    expect(payloads()[0]).toMatchObject({ type: 'improvement', screen: 'Упаковка', problem: 'Проблема', proposal: 'Улучшение', page_url: '/app/ff/fbs' })
    expect(payloads()[0]).not.toHaveProperty('description')
    expect(document.body.textContent).toContain('Спасибо, ваше обращение зафиксировано')
    expect(localStorage.getItem(draftStorageKey(identity))).toBeNull()
  })
  it.each([
    { basename: '/seller', path: '/seller/products' },
    { basename: '/', path: '/app/ff/fbs' },
  ])('sends the complete browser pathname with basename $basename, excluding query and hash', async ({ basename, path }) => {
    window.history.replaceState(null, '', `${path}?private=do-not-send#private-fragment`)
    await act(async () => root.render(<BrowserRouter basename={basename}><DeveloperRequests me={identity} token="fixture-token" /></BrowserRouter>))
    await click('Задача разработчикам'); await fill('Описание ошибки', 'Контекст экрана'); await click('Отправить')
    expect(payloads()).toHaveLength(1)
    expect(payloads()[0].page_url).toBe(path)
  })
  it('retains the same UUID across 500, lost response and remount; a later intentional request uses a new UUID', async () => {
    fetcher.mockImplementationOnce(async () => response({}, 500))
    await render(); await click('Задача разработчикам'); await fill('Описание ошибки', 'Ошибка'); await click('Отправить')
    expect(field('Описание ошибки').value).toBe('Ошибка'); expect(button('Отправить').disabled).toBe(false)
    fetcher.mockImplementationOnce(async () => { throw new TypeError('lost response') })
    await click('Отправить')
    await act(async () => root.unmount()); root = createRoot(host)
    await render(); await click('Задача разработчикам'); await click('Отправить')
    expect(new Set(payloads().map((p) => p.idempotency_key)).size).toBe(1)
    expect(document.body.textContent).toContain('Спасибо, ваше обращение зафиксировано')
    await click('Новая заявка'); await fill('Описание ошибки', 'Второе обращение'); await click('Отправить')
    expect(payloads()[3].idempotency_key).not.toBe(payloads()[0].idempotency_key)
  })
  it('resolves a lost submission before sending changed content without silently creating a new request or losing edits', async () => {
    fetcher.mockImplementationOnce(async () => { throw new TypeError('response lost after saving') })
    await render(); await click('Задача разработчикам'); await fill('Описание ошибки', 'Первый текст'); await click('Отправить')
    await fill('Описание ошибки', 'Дополненный текст'); await click('Отправить')
    expect(field('Описание ошибки').value).toBe('Дополненный текст'); expect(button('Отправить').disabled).toBe(true)
    await click('Проверить отправку')
    expect(payloads()[1]).toEqual(payloads()[0])
    expect(payloads()).toHaveLength(2)
    await click('Продолжить черновик'); expect(field('Описание ошибки').value).toBe('Дополненный текст')
    await click('Отправить'); expect(payloads()[2].idempotency_key).not.toBe(payloads()[0].idempotency_key)
  })
  it('preserves all oversized text on known 422 and sends corrected content with the same key', async () => {
    fetcher.mockImplementationOnce(async () => response({ detail: { code: 'developer_request_description_too_long', message: 'Обращение слишком длинное для передачи разработчикам. Сократите текст и отправьте ещё раз.', max_length: 16384, actual_length: 18100 } }, 422))
    await render(); await click('Задача разработчикам'); await selectType('improvement')
    await fill('Экран / процесс', 'Упаковка'); await fill('В чём сейчас проблема', 'А'.repeat(9000)); await fill('Как можно улучшить', 'Б'.repeat(9000)); await click('Отправить')
    expect(document.body.textContent).toContain('Сократите текст и отправьте ещё раз.')
    expect(field('В чём сейчас проблема').value).toHaveLength(9000)
    expect(field('Как можно улучшить').value).toHaveLength(9000)
    expect(JSON.parse(localStorage.getItem(draftStorageKey(identity))!).attempt).toBeUndefined()
    await fill('В чём сейчас проблема', 'Проблема'); await fill('Как можно улучшить', 'Предложение'); await click('Отправить')
    expect(payloads()[1].idempotency_key).toBe(payloads()[0].idempotency_key)
    expect(payloads()[1]).toMatchObject({ problem: 'Проблема', proposal: 'Предложение' })
    expect(document.body.textContent).toContain('Спасибо, ваше обращение зафиксировано')
  })
  it('exits a persistent two-tab 409 only through an explicit new draft, preserving text and the already-saved request', async () => {
    const saved = new Map<string, RequestPayload>()
    fetcher.mockImplementation(async (_url, init) => {
      if (init?.method !== 'POST') return response([...saved.values()].map((payload, index) => record(payload, `saved-${index}`)))
      const payload: RequestPayload = JSON.parse(init.body)
      const existing = saved.get(payload.idempotency_key)
      if (existing && JSON.stringify(existing) !== JSON.stringify(payload)) return response({}, 409)
      saved.set(payload.idempotency_key, payload)
      return response(record(payload))
    })
    await render(); await click('Задача разработчикам'); await fill('Описание ошибки', 'Текст вкладки B')
    const draftKey = JSON.parse(localStorage.getItem(draftStorageKey(identity))!).key
    // Tab A has already saved a different body with the key that both tabs loaded.
    const fromTabA: RequestPayload = { idempotency_key: draftKey, type: 'bug', description: 'Текст вкладки A', page_url: '/app/ff/fbs' }
    saved.set(draftKey, fromTabA)
    await click('Отправить')
    expect(field('Описание ошибки').value).toBe('Текст вкладки B')
    expect(button('Отправить').disabled).toBe(true)
    expect(JSON.parse(localStorage.getItem(draftStorageKey(identity))!).key).toBe(draftKey)
    await click('Закрыть'); await click('Задача разработчикам'); await click('Отправить')
    expect(payloads()).toHaveLength(2)
    expect(saved.size).toBe(1) // The conflict is persistent, not a mock-once response.
    await click('Продолжить как новый черновик')
    expect(payloads()).toHaveLength(2) // The recovery action itself does not create a request.
    expect(field('Описание ошибки').value).toBe('Текст вкладки B')
    const next = JSON.parse(localStorage.getItem(draftStorageKey(identity))!)
    expect(next.key).not.toBe(draftKey); expect(next.attempt).toBeUndefined()
    expect(button('Отправить').disabled).toBe(false)
    await click('Отправить')
    expect(saved.size).toBe(2)
    expect(saved.get(draftKey)).toEqual(fromTabA)
    expect(saved.get(next.key)?.description).toBe('Текст вкладки B')
    expect(document.body.textContent).toContain('Спасибо, ваше обращение зафиксировано')
  })
  it('guards double submit and ignores an old-scope response without clearing the next scope draft', async () => {
    let resolve!: (res: Response) => void
    fetcher.mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done }))
    await render(); await click('Задача разработчикам'); await fill('Описание ошибки', 'Первый пользователь')
    await act(async () => { button('Отправить').click(); button('Отправить').click() })
    expect(payloads()).toHaveLength(1)
    const other = { ...identity, id: 'user-b' }
    await render(other); await click('Задача разработчикам'); await fill('Описание ошибки', 'Второй пользователь')
    await act(async () => { resolve(response(record(payloads()[0]))) })
    expect(field('Описание ошибки').value).toBe('Второй пользователь')
    expect(document.body.textContent).not.toContain('Спасибо, ваше обращение зафиксировано')
    expect(localStorage.getItem(draftStorageKey(other))).toContain('Второй пользователь')
  })
  it('shows newest requests first, all four statuses and complete improvement detail without losing a draft', async () => {
    const rows = ['review', 'queued', 'in_progress', 'completed'].map((status, i) => ({ ...record({ idempotency_key: 'x', type: 'improvement', screen: `Экран ${i}`, problem: 'Полная проблема', proposal: 'Полное предложение', page_url: '/app/ff/fbs' }, `r${i}`), status, created_at: `2026-10-0${i + 1}T12:00:00Z` }))
    fetcher.mockImplementation(async (url) => response(String(url).endsWith('/r3') ? rows[3] : rows))
    await render(); await click('Задача разработчикам'); await fill('Описание ошибки', 'Черновик'); await click('Мои заявки')
    for (const label of ['На рассмотрении', 'В очереди', 'В работе', 'Готово']) expect(document.body.textContent).toContain(label)
    const items = [...document.querySelectorAll('.MuiListItemButton-root')]
    expect(items[0].textContent).toContain('Экран 3')
    await act(async () => (items[0] as HTMLElement).click())
    expect(document.body.textContent).toContain('Полная проблема'); expect(document.body.textContent).toContain('Полное предложение')
    await click('К списку'); await click('Новая заявка'); expect(field('Описание ошибки').value).toBe('Черновик')
  })
})
