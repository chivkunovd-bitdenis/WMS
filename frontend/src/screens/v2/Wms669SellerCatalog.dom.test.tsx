// @vitest-environment jsdom
/** WMS-669 C4-C8 forever. Mount the real screen, mock only HTTP transport.
 * C11 (authorized visual/browser acceptance) is intentionally not claimed here.
 */
import { act, type ReactElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { SellerProductsStockScreen, type SellerCatalogItem } from './SellerProductsStockScreen'

beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
let root: Root | null = null
const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` })
const screen = (token = 'shop-a', sellerId = token) => <SellerProductsStockScreen
  token={token} authHeaders={authHeaders} sellerId={sellerId} sellerName={sellerId} warehouses={[]} />
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
const product = (id: string, overrides = {}): SellerCatalogItem => ({
  key: `product:${id}`, id, on_fulfillment: true, marketplace: 'wildberries',
  name: `Пуховик ${id}`, sku_code: `SKU-${id}`, wb_vendor_code: '2329блэк', wb_nm_id: 669,
  wb_subject_name: 'Пуховики', wb_size: '48', wb_primary_image_url: 'https://example.test/p.jpg',
  wb_barcodes: ['669000000001'], wb_primary_barcode: '669000000001',
  ozon_sku: null, ozon_offer_id: null, packaging_instructions: 'ТЗ',
  has_packaging_instructions: true, requires_honest_sign: true, ...overrides,
})
const card: SellerCatalogItem = {
  key: 'wb:669101', on_fulfillment: false, marketplace: 'wildberries', nm_id: 669101,
  vendor_code: '2329блэк', category: 'Пуховики', sizes: ['46', '48'], name: 'WB варианты',
  photo_url: null, barcodes: [],
}
const page = (items: SellerCatalogItem[], total = items.length) => ({
  items, total, scope_total: 31, categories: ['Пуховики', 'Футболки'],
})
function normal(url: string) {
  if (url.endsWith('/tokens')) return json({ has_content_token: false })
  if (url.endsWith('/account')) return json({ connected: false })
  if (url.endsWith('/summary')) return json([
    { product_id: 'a', quantity: 4, reserved: 4, available: 0 },
    { product_id: 'b', quantity: 2, reserved: 0, available: 2 },
  ])
  return json([])
}
async function render(element: ReactElement = screen()) {
  if (!root) {
    const host = document.createElement('div')
    document.body.appendChild(host)
    root = createRoot(host)
  }
  await act(async () => { root!.render(element) })
}
afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  root = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})
function element(id: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-testid="${id}"]`)
  expect(found, `Existing UI ${id}`).not.toBeNull()
  return found!
}
function field(label: string): HTMLInputElement {
  const found = [...document.querySelectorAll('label')].find((el) => el.textContent === label)
  expect(found, `Required visible filter: ${label}`).toBeDefined()
  const input = found!.htmlFor ? document.getElementById(found!.htmlFor) : found!.querySelector('input')
  expect(input, `Input for ${label}`).toBeInstanceOf(HTMLInputElement)
  return input as HTMLInputElement
}
async function enter(input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => { await new Promise((done) => setTimeout(done, 300)) })
}
async function select(id: string, value: string) {
  await act(async () => {
    element(id).querySelector('[role="combobox"]')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
  })
  const option = document.querySelector<HTMLElement>(`[role="option"][data-value="${value}"]`)
  expect(option).not.toBeNull()
  await act(async () => { option!.click() })
}
async function click(id: string) {
  await act(async () => { element(id).click() })
}
async function nextPage() {
  const button = document.querySelector<HTMLButtonElement>('button[title="Go to next page"]')
  expect(button).not.toBeNull()
  expect(button!.disabled).toBe(false)
  await act(async () => { button!.click() })
}
function dataRows() {
  return [...document.querySelectorAll<HTMLElement>('[data-testid="seller-product-row"]')]
}
function headers() {
  return [...element('seller-products-table').querySelectorAll<HTMLTableRowElement>('tbody tr')]
    .filter((row) => row.dataset.testid !== 'seller-product-row')
}
function assertGroups(category: string, article: string, size: string) {
  const rows = [...element('seller-products-table').querySelectorAll('tbody tr')]
  const groupRows = headers()
  expect(groupRows.length, 'Visible category/article/size subheadings').toBeGreaterThanOrEqual(3)
  const indexes = [category, article, size].map((label) => {
    const group = groupRows.find((row) => row.textContent?.trim().includes(label))
    expect(group, `Visible group ${label}`).toBeDefined()
    expect(group!.querySelector('input,button'), 'Group must not be selectable/actionable').toBeNull()
    return rows.indexOf(group!)
  })
  expect(indexes[0]).toBeLessThan(indexes[1])
  expect(indexes[1]).toBeLessThan(indexes[2])
  expect(indexes[2]).toBeLessThan(rows.indexOf(dataRows()[0] as HTMLTableRowElement))
}
function latestPage(fetchMock: ReturnType<typeof vi.fn>) {
  const calls = fetchMock.mock.calls.filter(([url]) => String(url).includes('/seller-catalog/page'))
  return new URL(String(calls.at(-1)![0]), 'http://test').searchParams
}

// Controls use exactly the same render/HTTP fixtures as RED contracts.
describe('WMS-669 seller catalog contract', () => {
  it('control: real rows, quantities, existing filters, paging and row actions render', async () => {
    const fetchMock = vi.fn((url: RequestInfo | URL) => Promise.resolve(String(url).includes('/seller-catalog/page')
      ? json(page([product('a'), product('b')], 21)) : normal(String(url))))
    vi.stubGlobal('fetch', fetchMock)
    await render()
    expect(dataRows()).toHaveLength(2)
    expect(element('seller-catalog-stock-on-hand-a').textContent).toBe('Остаток 4')
    expect(element('seller-catalog-stock-reserved-a').textContent).toBe('Резерв 4')
    expect(element('seller-catalog-stock-available-a').textContent).toBe('Доступно 0')
    expect(element('seller-packaging-edit-a').textContent).toBe('ТЗ')
    expect(element('seller-catalog-reserves-a').textContent).toBe('Резервы')
    await select('seller-catalog-category-filter', 'Пуховики')
    await select('seller-catalog-marketplace-filter', 'wildberries')
    await select('seller-catalog-fulfillment-filter', 'yes')
    await enter(element('seller-catalog-search') as HTMLInputElement, 'Пуховик')
    await nextPage()
    expect(Object.fromEntries(latestPage(fetchMock))).toMatchObject({
      category: 'Пуховики', marketplace: 'wildberries', on_fulfillment: 'yes', search: 'Пуховик', offset: '10', limit: '10',
    })
  })

  it.each(['Артикул', 'Размер', 'Только с остатком'])('C6 %s resets page and keeps all intersecting filters', async (changed) => {
    const fetchMock = vi.fn((url: RequestInfo | URL) => {
      const path = String(url)
      if (!path.includes('/seller-catalog/page')) return Promise.resolve(normal(path))
      const params = new URL(path, 'http://test').searchParams
      return Promise.resolve(json(page([product(params.get('offset') === '0' ? 'a' : 'b')], 21)))
    })
    vi.stubGlobal('fetch', fetchMock)
    await render()
    await select('seller-catalog-category-filter', 'Пуховики')
    await select('seller-catalog-marketplace-filter', 'wildberries')
    await select('seller-catalog-fulfillment-filter', 'yes')
    await enter(element('seller-catalog-search') as HTMLInputElement, 'Пуховик')
    if (changed !== 'Артикул') await enter(field('Артикул'), '2329блэк')
    if (changed !== 'Размер') await enter(field('Размер'), '48')
    if (changed !== 'Только с остатком') await act(async () => { field('Только с остатком').click() })
    await nextPage()
    expect(latestPage(fetchMock).get('offset')).toBe('10')
    if (changed === 'Артикул') await enter(field(changed), '2329блэк')
    else if (changed === 'Размер') await enter(field(changed), '48')
    else await act(async () => { field(changed).click() })
    expect(Object.fromEntries(latestPage(fetchMock))).toMatchObject({
      article: '2329блэк', size: '48', stock_only: 'true', category: 'Пуховики',
      search: 'Пуховик', marketplace: 'wildberries', on_fulfillment: 'yes',
      group_by: 'category_article_size', offset: '0', limit: '10',
    })
    expect(dataRows()).toHaveLength(1)
    expect(dataRows()[0].textContent).toContain('Пуховик a')
    expect(element('seller-catalog-filter-count').textContent).toContain('Найдено: 21 из 31')
    const paths = fetchMock.mock.calls.map(([url]) => String(url))
    expect(paths.some((url) => url.includes('/products/wb-catalog'))).toBe(false)
    expect(paths.some((url) => url.includes('/seller-catalog/keys'))).toBe(false)
  })

  it('C4/C7 groups keep separate rows, stock/actions and repeat context on the next page', async () => {
    const fetchMock = vi.fn((url: RequestInfo | URL) => {
      const path = String(url)
      if (!path.includes('/seller-catalog/page')) return Promise.resolve(normal(path))
      const offset = new URL(path, 'http://test').searchParams.get('offset')
      return Promise.resolve(json(page(offset === '0' ? [product('a'), product('b')] : [product('b')], 11)))
    })
    vi.stubGlobal('fetch', fetchMock)
    await render()
    assertGroups('Пуховики', '2329блэк', '48')
    expect(dataRows()).toHaveLength(2)
    expect(element('seller-catalog-stock-on-hand-a').textContent).toBe('Остаток 4')
    expect(element('seller-catalog-stock-on-hand-b').textContent).toBe('Остаток 2')
    expect(element('seller-products-table').querySelectorAll('tbody input[type="checkbox"]')).toHaveLength(2)
    expect(element('seller-packaging-edit-a')).toBeDefined()
    expect(element('seller-honest-sign-status-a')).toBeDefined()
    expect(dataRows()[0].querySelector('img')).not.toBeNull()
    await nextPage()
    assertGroups('Пуховики', '2329блэк', '48')
    expect(dataRows()).toHaveLength(1)
    expect(element('seller-products-pagination').textContent).toContain('11')
  })

  it('C5 groups missing values honestly and keeps imported size set in one row', async () => {
    vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => Promise.resolve(String(url).includes('/seller-catalog/page')
      ? json(page([product('a', { wb_subject_name: null, wb_vendor_code: null, wb_size: null }), card]))
      : normal(String(url)))))
    await render()
    assertGroups('Без категории', 'Без артикула', 'Без размера')
    expect(dataRows()).toHaveLength(2)
    const knownGroups = headers().map((row) => row.textContent?.trim())
    expect(knownGroups).toContain('46, 48')
    expect(dataRows().filter((row) => row.textContent?.includes('WB варианты'))).toHaveLength(1)
    expect(dataRows()[1].textContent).toContain('46, 48')
  })

  it('C7 selection survives pages and filters; bulk action sends only original product IDs', async () => {
    const fetchMock = vi.fn((url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url)
      if (path.includes('/seller-catalog/page')) {
        const p = new URL(path, 'http://test').searchParams
        return Promise.resolve(json(page([product(p.get('offset') === '0' ? 'a' : 'b')], 21)))
      }
      if (path.endsWith('/requires-honest-sign/bulk')) {
        expect(options?.method).toBe('PATCH')
        return Promise.resolve(json({ updated_count: 2 }))
      }
      return Promise.resolve(normal(path))
    })
    vi.stubGlobal('fetch', fetchMock)
    await render()
    await act(async () => { element('seller-product-select-a').querySelector<HTMLInputElement>('input')!.click() })
    await nextPage()
    await act(async () => { element('seller-product-select-b').querySelector<HTMLInputElement>('input')!.click() })
    expect(element('seller-catalog-selection-count').textContent).toBe('Выбрано 2')
    await enter(field('Артикул'), '2329блэк')
    expect(element('seller-catalog-selection-count').textContent).toBe('Выбрано 2')
    await click('seller-products-bulk-honest-sign')
    const request = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/requires-honest-sign/bulk'))
    expect(JSON.parse(String(request![1]?.body))).toEqual({ product_ids: ['a', 'b'], requires_honest_sign: true })
  })

  it('C8 ignores late old-filter page even when transport ignores AbortSignal', async () => {
    const late = deferred<Response>()
    let paused = false
    const fetchMock = vi.fn((url: RequestInfo | URL) => {
      const path = String(url)
      if (!path.includes('/seller-catalog/page')) return Promise.resolve(normal(path))
      const article = new URL(path, 'http://test').searchParams.get('article')
      if (article === 'old') { paused = true; return late.promise }
      return Promise.resolve(json(page([product(article === 'current' ? 'current' : 'initial')])))
    })
    vi.stubGlobal('fetch', fetchMock)
    await render()
    await enter(field('Артикул'), 'old')
    expect(paused).toBe(true)
    await enter(field('Артикул'), 'current')
    expect(dataRows()[0].textContent).toContain('Пуховик current')
    await act(async () => { late.resolve(json(page([product('stale')], 999))) })
    expect(dataRows()[0].textContent).toContain('Пуховик current')
    expect(document.body.textContent).not.toContain('Пуховик stale')
    expect(element('seller-catalog-filter-count').textContent).not.toContain('999')
  })

  it('C8 ignores late page and summary after the existing token-based shop switch', async () => {
    const latePage = deferred<Response>()
    const lateStock = deferred<Response>()
    let previous = true
    const fetchMock = vi.fn((url: RequestInfo | URL) => {
      const path = String(url)
      if (path.includes('/seller-catalog/page')) return previous ? latePage.promise : Promise.resolve(json(page([product('a')])))
      if (path.endsWith('/summary')) return previous ? lateStock.promise : Promise.resolve(normal(path))
      return Promise.resolve(normal(path))
    })
    vi.stubGlobal('fetch', fetchMock)
    await render(screen('shop-a', 'seller-a'))
    previous = false
    await render(screen('shop-b', 'seller-b'))
    expect(dataRows()).toHaveLength(1)
    expect(dataRows()[0].textContent).toContain('Пуховик a')
    await act(async () => {
      latePage.resolve(json(page([product('old-seller')], 999)))
      lateStock.resolve(json([{ product_id: 'a', quantity: 999, reserved: 999, available: 0 }]))
    })
    expect(document.body.textContent).not.toContain('Пуховик old-seller')
    expect(element('seller-catalog-stock-on-hand-a').textContent).toBe('Остаток 4')
    expect(element('seller-catalog-stock-reserved-a').textContent).toBe('Резерв 4')
  })


  it('C8 old search response cannot overwrite newer results even if cancellation is ignored', async () => {
    const late = deferred<Response>()
    let observedOldRequest = false
    vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => {
      const path = String(url)
      if (!path.includes('/seller-catalog/page')) return Promise.resolve(normal(path))
      const search = new URL(path, 'http://test').searchParams.get('search')
      if (search === 'old') { observedOldRequest = true; return late.promise }
      return Promise.resolve(json(page([product(search === 'current' ? 'current' : 'initial')])))
    }))
    await render()
    await enter(element('seller-catalog-search') as HTMLInputElement, 'old')
    expect(observedOldRequest).toBe(true)
    await enter(element('seller-catalog-search') as HTMLInputElement, 'current')
    expect(dataRows()[0].textContent).toContain('Пуховик current')
    await act(async () => { late.resolve(json(page([product('stale')], 999))) })
    expect(dataRows()[0].textContent).toContain('Пуховик current')
    expect(document.body.textContent).not.toContain('Пуховик stale')
    expect(element('seller-catalog-filter-count').textContent).not.toContain('999')
  })

  it('C8 clears previous seller rows and quantities while the new shop response is pending', async () => {
    const pendingPage = deferred<Response>()
    const pendingStock = deferred<Response>()
    let newShop = false
    vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => {
      const path = String(url)
      if (path.includes('/seller-catalog/page')) return newShop ? pendingPage.promise : Promise.resolve(json(page([product('a')])))
      if (path.endsWith('/summary')) return newShop ? pendingStock.promise : Promise.resolve(normal(path))
      return Promise.resolve(normal(path))
    }))
    await render(screen('shop-a'))
    expect(element('seller-catalog-stock-on-hand-a').textContent).toBe('Остаток 4')
    newShop = true
    await render(screen('shop-b'))
    expect(dataRows()).toHaveLength(0)
    expect(document.querySelector('[data-testid="seller-catalog-stock-on-hand-a"]')).toBeNull()
    await act(async () => {
      pendingPage.resolve(json(page([product('b')])))
      pendingStock.resolve(json([{ product_id: 'b', quantity: 2, reserved: 0, available: 2 }]))
    })
    expect(dataRows()[0].textContent).toContain('Пуховик b')
    expect(element('seller-catalog-stock-on-hand-b').textContent).toBe('Остаток 2')
  })

  it('control: empty result and request error use existing states and can be retried', async () => {
    let failed = true
    const fetchMock = vi.fn((url: RequestInfo | URL) => Promise.resolve(String(url).includes('/seller-catalog/page')
      ? failed ? json({ detail: 'Не удалось загрузить товары.' }, 503) : json(page([])) : normal(String(url))))
    vi.stubGlobal('fetch', fetchMock)
    await render()
    expect(element('seller-products-error').textContent).toContain('Не удалось загрузить товары.')
    failed = false
    await select('seller-catalog-fulfillment-filter', 'no')
    expect(document.body.textContent).toContain('Ничего не найдено.')
    expect(document.querySelector('[data-testid="seller-products-error"]')).toBeNull()
  })
})
