// @vitest-environment jsdom
import { act, type ReactElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { SellerProductsStockScreen } from './SellerProductsStockScreen'
import { SellerSettingsScreen } from './SellerSettingsScreen'

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})
let root: Root | null = null
let host: HTMLDivElement
const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` })
const products = (token = 'seller-a') => <SellerProductsStockScreen token={token} authHeaders={authHeaders} sellerId={token} sellerName={token} warehouses={[]} />
const settings = (token = 'seller-a') => <SellerSettingsScreen token={token} authHeaders={authHeaders} permissions={{ documents: true, products: true, honest_sign: false, settings: true, staff: false }} />
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
async function render(element: ReactElement) {
  if (!root) {
    host = document.createElement('div')
    document.body.appendChild(host)
    root = createRoot(host)
  }
  await act(async () => { root!.render(element) })
}
async function unmount() {
  if (root) await act(async () => { root!.unmount() })
  root = null
}
afterEach(async () => {
  await unmount()
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})
function element(id: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-testid="${id}"]`)
  expect(found, id).not.toBeNull()
  return found!
}
async function click(id: string) {
  await act(async () => { element(id).click() })
}
async function input(id: string, value: string) {
  await act(async () => {
    const field = element(id)
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, value)
    field.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function select(id: string, value: string) {
  await act(async () => {
    element(id).querySelector('[role="combobox"]')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
  })
  await act(async () => { document.querySelector<HTMLElement>(`[role="option"][data-value="${value}"]`)!.click() })
}
function normalResponse(url: string) {
  if (url.includes('/seller-catalog/page')) return json({ items: [], total: 100, scope_total: 100, categories: [] })
  if (url.endsWith('/tokens')) return json({ has_content_token: true })
  if (url.endsWith('/account')) return json({ connected: true, validation_status: 'valid', last_sync_error: null })
  return json([])
}

describe('catalog job lifecycle in actual seller screens', () => {
  it('reloads the current marketplace/search/page/fulfillment after an older job completes', async () => {
    const completion = deferred<Response>()
    const fetchMock = vi.fn((url: RequestInfo | URL) => {
      const path = String(url)
      if (path.includes('/background-jobs/')) return completion.promise
      if (path.endsWith('/sync-products')) return Promise.resolve(json({ id: 'wb-job', state: 'queued' }, 202))
      if (path.endsWith('/account')) return Promise.resolve(json({ connected: false }))
      return Promise.resolve(normalResponse(path))
    })
    vi.stubGlobal('fetch', fetchMock)
    await render(products())
    await click('seller-sync-products')
    await select('seller-catalog-marketplace-filter', 'ozon')
    await select('seller-catalog-fulfillment-filter', 'no')
    await input('seller-catalog-search', 'needle')
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 300)) })
    await act(async () => { document.querySelector<HTMLButtonElement>('button[title="Go to next page"]')!.click() })
    const before = fetchMock.mock.calls.filter(([url]) => String(url).includes('/seller-catalog/page')).length
    await act(async () => { completion.resolve(json({ state: 'succeeded' })) })
    const pages = fetchMock.mock.calls.filter(([url]) => String(url).includes('/seller-catalog/page'))
    expect(pages.length).toBe(before + 1)
    const params = new URL(String(pages.at(-1)![0]), 'http://local').searchParams
    expect(Object.fromEntries(params)).toMatchObject({ marketplace: 'ozon', search: 'needle', on_fulfillment: 'no', offset: '10' })
  })

  it.each(['wb', 'ozon'] as const)('retry %s starts and observes only that marketplace', async (mp) => {
    let failed = true
    const fetchMock = vi.fn((url: RequestInfo | URL) => {
      const path = String(url)
      if (path.includes('/background-jobs/')) return Promise.resolve(json({ state: failed ? 'failed' : 'succeeded', error_message: 'ozon_catalog_unavailable' }))
      if (path.endsWith('/sync-products')) return Promise.resolve(json({ id: path.includes('wildberries') ? 'wb-job' : 'ozon-job', state: 'queued' }, 202))
      return Promise.resolve(normalResponse(path))
    })
    vi.stubGlobal('fetch', fetchMock)
    await render(products())
    await click('seller-sync-products')
    expect(element(`seller-products-sync-${mp}-failed`).textContent).toContain('Не удалось загрузить каталог Ozon')
    fetchMock.mockClear()
    failed = false
    await click(`seller-products-sync-${mp}-retry`)
    const calls = fetchMock.mock.calls.map(([url]) => String(url))
    expect(calls.filter((url) => url.endsWith('/sync-products'))).toEqual([expect.stringContaining(mp === 'wb' ? '/wildberries/' : '/ozon/')])
    expect(calls.filter((url) => url.includes('/background-jobs/'))).toEqual([expect.stringContaining(`/${mp}-job`)])
  })

  it.each(['connection', 'start', 'retry'] as const)('ignores late %s response after unmount, including the second marketplace', async (phase) => {
    const late = deferred<Response>()
    let pause = phase !== 'retry'
    const fetchMock = vi.fn((url: RequestInfo | URL) => {
      const path = String(url)
      if (pause && path.includes('/wildberries/') && (phase === 'connection' ? path.endsWith('/tokens') : path.endsWith('/sync-products'))) return late.promise
      if (path.includes('/background-jobs/')) return Promise.resolve(json({ state: 'failed', error_message: 'failure' }))
      if (path.endsWith('/sync-products')) return Promise.resolve(json({ id: 'job', state: 'queued' }, 202))
      return Promise.resolve(normalResponse(path))
    })
    vi.stubGlobal('fetch', fetchMock)
    await render(products())
    await click('seller-sync-products')
    if (phase === 'retry') {
      pause = true
      await click('seller-products-sync-wb-retry')
    }
    await unmount()
    fetchMock.mockClear()
    await act(async () => { late.resolve(json(phase === 'connection' ? { has_content_token: true } : { id: 'late-job', state: 'queued' })) })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('ignores a late start after a seller session switch', async () => {
    const late = deferred<Response>()
    const fetchMock = vi.fn((url: RequestInfo | URL) => String(url).endsWith('/sync-products') ? late.promise : Promise.resolve(normalResponse(String(url))))
    vi.stubGlobal('fetch', fetchMock)
    await render(products())
    await click('seller-sync-products')
    await render(products('seller-b'))
    fetchMock.mockClear()
    await act(async () => { late.resolve(json({ id: 'old-seller-job', state: 'queued' })) })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(document.querySelector('[data-testid="seller-products-sync-wb-progress"]')).toBeNull()
  })

  it.each(['wb-save', 'ozon-save', 'retry', 'sync'] as const)('settings ignores late %s on unmount and never starts a watcher', async (operation) => {
    const late = deferred<Response>()
    const fetchMock = vi.fn((url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url)
      if (options?.method === 'POST' || options?.method === 'PUT') return late.promise
      if (path.endsWith('/account')) return Promise.resolve(json({ connected: operation === 'retry', validation_status: 'valid', last_sync_error: operation === 'retry' ? 'ozon_catalog_unavailable' : null }))
      return Promise.resolve(normalResponse(path))
    })
    vi.stubGlobal('fetch', fetchMock)
    await render(settings())
    if (operation === 'wb-save') {
      await click('seller-settings-add-key')
      await input('seller-settings-key-input', 'synthetic')
      await click('seller-settings-save')
    } else if (operation === 'ozon-save') {
      await input('seller-settings-ozon-client-id', 'synthetic')
      await input('seller-settings-ozon-api-key', 'synthetic')
      await click('seller-settings-ozon-connect')
    } else if (operation === 'retry') {
      expect(element('seller-settings-ozon-import-failed').textContent).toContain('Не удалось загрузить каталог Ozon')
      await click('seller-settings-ozon-import-retry')
    } else await click('seller-settings-sync-products')
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'POST' || options?.method === 'PUT')).toBe(true)
    await unmount()
    fetchMock.mockClear()
    await act(async () => { late.resolve(json({ id: 'late-job', state: 'queued', connected: true, validation_status: 'valid', validation_ok: true, catalog_job: { id: 'late-job', state: 'queued' } })) })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('keeps WB validation-unavailable error in the dialog with entered key intact', async () => {
    vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, options?: RequestInit) => Promise.resolve(options?.method === 'POST' ? json({ detail: 'wb_validation_unavailable' }, 503) : normalResponse(String(url)))))
    await render(settings())
    await click('seller-settings-add-key')
    await input('seller-settings-key-input', 'synthetic')
    await click('seller-settings-save')
    const dialog = document.querySelector('[role="dialog"]')!
    expect(dialog.textContent).toContain('Не удалось проверить ключ Wildberries. Попробуйте ещё раз позже.')
    expect(dialog.textContent).not.toContain('wb_validation_unavailable')
    expect((element('seller-settings-key-input') as HTMLInputElement).value).toBe('synthetic')
  })

  it('settings ignores a late WB save after switching seller sessions', async () => {
    const late = deferred<Response>()
    const fetchMock = vi.fn((url: RequestInfo | URL, options?: RequestInit) => options?.method === 'POST' ? late.promise : Promise.resolve(normalResponse(String(url))))
    vi.stubGlobal('fetch', fetchMock)
    await render(settings())
    await click('seller-settings-add-key')
    await input('seller-settings-key-input', 'synthetic')
    await click('seller-settings-save')
    await render(settings('seller-b'))
    fetchMock.mockClear()
    await act(async () => { late.resolve(json({ validation_ok: true, catalog_job: { id: 'old-seller-job', state: 'queued' } })) })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(document.querySelector('[data-testid="seller-settings-wb-import-progress"]')).toBeNull()
    expect(document.querySelector('[data-testid="seller-settings-ok"]')).toBeNull()
  })

  it.each(['products', 'settings'] as const)('%s stops an existing watcher when the seller session changes', async (screen) => {
    const late = deferred<Response>()
    const fetchMock = vi.fn((url: RequestInfo | URL) => {
      const path = String(url)
      if (path.includes('/background-jobs/')) return late.promise
      if (path.endsWith('/sync-products')) return Promise.resolve(json({ id: 'old-job', state: 'running' }, 202))
      return Promise.resolve(normalResponse(path))
    })
    vi.stubGlobal('fetch', fetchMock)
    const screenElement = screen === 'products' ? products : settings
    await render(screenElement())
    await click(screen === 'products' ? 'seller-sync-products' : 'seller-settings-sync-products')
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/background-jobs/'))).toBe(true)
    await render(screenElement('seller-b'))
    fetchMock.mockClear()
    await act(async () => { late.resolve(json({ state: 'succeeded' })) })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
