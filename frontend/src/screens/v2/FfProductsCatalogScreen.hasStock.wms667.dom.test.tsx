// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { FfProductsCatalogScreen } from './FfProductsCatalogScreen'

// Real component, effects and DOM events. Only HTTP responses are fixtures.
// Contract: «С остатком», data-testid=ff-catalog-has-stock-filter, has_stock=true.
const sellers = [{ id: 'seller-a', name: 'Селлер А' }, { id: 'seller-b', name: 'Селлер Б' }]
const authHeaders = () => ({ Authorization: 'Bearer test' })
let host: HTMLDivElement
let root: Root
let requests: URLSearchParams[]
let emptyStock: boolean

const row = (id: string) => ({
  id, seller_id: 'seller-a', seller_name: 'Селлер А', name: `Товар ${id}`,
  sku_code: `NEEDLE-${id}`, wb_nm_id: 667, wb_vendor_code: null,
  wb_subject_name: 'X', wb_primary_image_url: null, wb_barcodes: [],
  wb_primary_barcode: null, wb_size: null, wb_color: null, wb_brand: null,
  wb_composition: null, packaging_instructions: null, marketplaces: ['wildberries'],
  requires_honest_sign: false, has_packaging_instructions: false,
})
const response = (data: unknown) => ({ ok: true, json: async () => data }) as Response

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})
beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  requests = []
  emptyStock = false
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    expect(init?.method ?? 'GET').toBe('GET')
    const url = new URL(String(input), 'http://test')
    if (url.pathname.endsWith('/products/ff-catalog-page')) {
      requests.push(new URLSearchParams(url.search))
      const stock = url.searchParams.get('has_stock') === 'true'
      // A positive row beyond the previous server page. No local stock filtering.
      return response({
        items: stock ? (emptyStock ? [] : [row('late-positive')]) : [row('ordinary-zero')],
        total: stock ? (emptyStock ? 0 : 1) : 101,
        scope_total: 120, categories: ['X', 'Y'],
      })
    }
    if (url.pathname.endsWith('/operations/inventory-balances/summary')) {
      return response(url.searchParams.getAll('product_id').map((product_id) => ({
        product_id, quantity: product_id === 'late-positive' ? 5 : 0,
        reserved: product_id === 'late-positive' ? 5 : 0, available: 0,
      })))
    }
    return response([])
  }))
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})
async function settle() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
}
async function waitUntil(check: () => boolean) {
  for (let attempt = 0; attempt < 35; attempt += 1) {
    if (check()) return
    await settle()
  }
  expect(check(), 'component/request did not settle').toBe(true)
}
async function mount() {
  await act(async () => root.render(
    <MemoryRouter initialEntries={['/app/ff/products']}>
      <FfProductsCatalogScreen token="test" authHeaders={authHeaders}
        sellers={sellers} warehouses={[]} />
    </MemoryRouter>,
  ))
  await waitUntil(() => host.querySelector('[data-testid="ff-product-row"]') !== null)
}
async function select(testId: string, label: string) {
  const combobox = host.querySelector(`[data-testid="${testId}"] [role="combobox"]`)
  expect(combobox).not.toBeNull()
  await act(async () => combobox!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 })))
  await settle()
  const option = Array.from(document.querySelectorAll('[role="option"]')).find((node) => node.textContent === label)
  expect(option, `option ${label}`).toBeDefined()
  await act(async () => (option as HTMLElement).click())
  await settle()
}
function latest() { return requests[requests.length - 1] }
async function toggleStock() {
  const control = host.querySelector('[data-testid="ff-catalog-has-stock-filter"]')
  expect(control, 'C8/C9: existing filters need a «С остатком» control').not.toBeNull()
  expect(host.querySelector('[data-testid="ff-catalog-filters"]')?.contains(control)).toBe(true)
  expect(control?.textContent || control?.closest('label')?.textContent).toContain('С остатком')
  const input = control?.matches('input') ? control : control?.querySelector('input')
  await act(async () => ((input ?? control) as HTMLElement).click())
  await settle()
}

it('c8_toggle_resets_page_preserves_filters_and_renders_server_selection', async () => {
  await mount()
  await select('ff-catalog-seller-filter', 'Селлер А')
  await select('ff-catalog-marketplace-filter', 'Wildberries')
  await select('ff-catalog-stock-publication-filter', 'Выключена на обеих')
  await select('ff-catalog-category-filter', 'X')
  const search = host.querySelector('[data-testid="ff-catalog-search"]') as HTMLInputElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(search, 'NEEDLE')
    search.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await waitUntil(() => latest().get('search') === 'NEEDLE')
  const next = host.querySelector('[data-testid="ff-catalog-pagination"] button[aria-label="Go to next page"]') as HTMLButtonElement
  expect(next).not.toBeNull()
  await act(async () => next.click())
  await waitUntil(() => Number(latest().get('offset')) > 0)
  const start = requests.length
  await toggleStock()
  await waitUntil(() => latest().get('has_stock') === 'true')
  const stockRequests = requests.slice(start).filter((params) => params.get('has_stock') === 'true')
  expect(stockRequests.length).toBeGreaterThan(0)
  for (const params of stockRequests) {
    expect(Object.fromEntries(params)).toMatchObject({
      has_stock: 'true', offset: '0', seller_id: 'seller-a', marketplace: 'wildberries',
      category: 'X', search: 'NEEDLE', stock_publication: 'none',
    })
  }
  expect(host.querySelector('[data-testid="ff-catalog-filter-count"]')?.textContent).toBe('Найдено: 1 из 120')
  const rows = host.querySelectorAll('[data-testid="ff-product-row"]')
  expect(rows).toHaveLength(1)
  expect(rows[0].textContent).toContain('late-positive')
  expect(host.textContent).not.toContain('ordinary-zero')
  await toggleStock()
  await waitUntil(() => latest().get('has_stock') !== 'true')
  expect(Object.fromEntries(latest())).toMatchObject({
    offset: '0', seller_id: 'seller-a', marketplace: 'wildberries', category: 'X',
    search: 'NEEDLE', stock_publication: 'none',
  })
  expect(host.querySelector('[data-testid="ff-catalog-filter-count"]')?.textContent).toBe('Найдено: 101 из 120')
  expect(host.querySelector('[data-testid="ff-product-row"]')?.textContent).toContain('ordinary-zero')
})

it('c9_empty_stock_result_can_be_disabled_without_remount', async () => {
  emptyStock = true
  await mount()
  await toggleStock()
  await waitUntil(() => latest().get('has_stock') === 'true')
  expect(host.querySelectorAll('[data-testid="ff-product-row"]')).toHaveLength(0)
  expect(host.querySelector('[data-testid="ff-products-empty"]')?.textContent).toBe('Ничего не найдено.')
  expect(host.querySelector('[data-testid="ff-catalog-filter-count"]')?.textContent).toBe('Найдено: 0 из 120')
  expect(host.querySelector('[data-testid="ff-catalog-pagination"]')?.textContent).toContain('0–0 из 0')
  await toggleStock()
  await waitUntil(() => latest().get('has_stock') !== 'true')
  expect(host.querySelector('[data-testid="ff-products-empty"]')).toBeNull()
  expect(host.querySelector('[data-testid="ff-product-row"]')?.textContent).toContain('ordinary-zero')
})

it('regression_real_dom_follows_unfiltered_server_page_and_count', async () => {
  await mount()
  expect(latest().get('has_stock')).toBeNull()
  expect(host.querySelector('[data-testid="ff-product-row"]')?.textContent).toContain('ordinary-zero')
  expect(host.querySelector('[data-testid="ff-catalog-filter-count"]')?.textContent).toBe('Найдено: 101 из 120')
})
