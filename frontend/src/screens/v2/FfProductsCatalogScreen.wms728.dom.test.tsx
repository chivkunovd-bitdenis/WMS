// @vitest-environment jsdom
// Decorative icon barrel exports thousands of SVGs; they are outside this contract.
vi.mock('@mui/icons-material', () => new Proxy({}, {
  has: () => true,
  get: (_target, key) => key === 'then' ? undefined : () => null,
}))
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { beforeAll, beforeEach, afterEach, expect, it, vi } from 'vitest'
import { FfProductsCatalogScreen } from './FfProductsCatalogScreen'

const authHeaders = () => ({ Authorization: 'Bearer test' })
const sellers = [{ id: 's1', name: 'Селлер 1' }, { id: 's2', name: 'Селлер 2' }]
const row = (id: string, category: string | null) => ({ id, seller_id: 's1', seller_name: 'Селлер 1', name: id, sku_code: id, wb_nm_id: 728, wb_subject_name: category, wb_primary_image_url: null, wb_barcodes: [], wb_primary_barcode: null, wb_size: null, wb_color: null, marketplaces: ['wildberries'], requires_honest_sign: false, has_packaging_instructions: false })
const largeData = [...Array.from({ length: 104 }, (_, i) => row(`A-${String(i).padStart(3, '0')}`, 'A')), row('B-one', 'B'), row('C-one', 'C'), row('NO-category', null)]
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
// D3 leaves transport to the developer. Decode repeated, plural, JSON or comma
// array query values instead of pinning the UI to one encoding.
function categories(params: URLSearchParams): string[] {
  return [...params.entries()].filter(([key]) => /^categor/i.test(key)).flatMap(([, value]) => {
    try { const parsed: unknown = JSON.parse(value); if (Array.isArray(parsed)) return parsed.map(String) } catch { /* plain query value */ }
    return value.split(',').filter(Boolean)
  })
}
let data: ReturnType<typeof row>[]
let sparsePages: boolean
let host: HTMLDivElement
let root: Root
let requests: URLSearchParams[]
let failure: 'catalog' | 'stock' | null
let delayCategory: string | null
let delayed: { resolve: (response: Response) => void; params: URLSearchParams; signal?: AbortSignal | null }[]
beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true })
function page(params: URLSearchParams) {
  const selected = categories(params)
  const items = data.filter(item => !selected.length || selected.includes(item.wb_subject_name ?? ''))
  const offset = Number(params.get('offset') ?? 0), limit = Number(params.get('limit') ?? 100)
  return { items: items.slice(offset, offset + limit).slice(0, sparsePages ? 2 : limit), total: items.length, scope_total: data.length, categories: params.get('seller_id') === 's2' ? ['D', 'E'] : ['A', 'B', 'C'], offset, limit }
}
beforeEach(() => {
  // Menu transitions and the search debounce belong to this test's clock.
  // A zero-delay real sleep left 195/225ms MUI transition callbacks pending.
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  data = [row('A-one', 'A'), row('A-two', 'A'), row('B-one', 'B'), row('C-one', 'C'), row('NO-category', null)]
  sparsePages = false
  requests = []; failure = null; delayCategory = null; delayed = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    expect(init?.method ?? 'GET').toBe('GET')
    const url = new URL(String(input), 'http://test')
    if (url.pathname.endsWith('/products/ff-catalog-page')) {
      const params = new URLSearchParams(url.search); requests.push(params)
      if (categories(params).join(',') === delayCategory) return new Promise<Response>(resolve => { delayed.push({ resolve, params, signal: init?.signal }) })
      if (failure === 'catalog') return json({ detail: 'Ошибка каталога 728' }, 500)
      return json(page(params))
    }
    if (url.pathname.endsWith('/inventory-balances/summary')) {
      if (failure === 'stock') return json({ detail: 'Ошибка остатков 728' }, 500)
      return json(url.searchParams.getAll('product_id').map(product_id => ({ product_id, quantity: 5, reserved: 5, available: 0 })))
    }
    return json([])
  }))
})
afterEach(async () => {
  try {
    await act(async () => {
      root.unmount()
      // Complete any deliberately delayed read after unmount has aborted it,
      // so its promise cannot continue against the next test's mutable data.
      for (const request of delayed) request.resolve(json(page(request.params)))
      await vi.runOnlyPendingTimersAsync()
    })
  } finally {
    host.remove()
    vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals()
  }
})
async function settle() {
  await act(async () => { await vi.runOnlyPendingTimersAsync() })
}
async function mount() {
  await act(async () => root.render(<MemoryRouter><FfProductsCatalogScreen token="test" authHeaders={authHeaders} sellers={sellers} warehouses={[]} /></MemoryRouter>))
  await settle()
}
const latest = () => requests.at(-1)!
async function choose(testId: string, label: string) {
  let option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find(el => el.textContent === label)
  if (!option) {
    const combo = host.querySelector(`[data-testid="${testId}"] [role="combobox"]`)
    expect(combo).not.toBeNull()
    await act(async () => combo!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 })))
    option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find(el => el.textContent === label)
  }
  expect(option, `available option ${label}`).toBeDefined()
  await act(async () => option!.click()); await settle()
}
async function chooseCategory(label: string) { await choose('ff-catalog-category-filter', label) }
function expectSelection(values: string[]) {
  expect([...new Set(categories(latest()))].sort()).toEqual([...values].sort())
  const text = host.querySelector('[data-testid="ff-catalog-category-filter"] [role="combobox"]')!.textContent
  for (const value of values) expect(text).toContain(value)
}
async function closeMenu() {
  const list = document.querySelector('[role="listbox"]')
  if (list) {
    await act(async () => list.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    await settle()
  }
}
function count(text: string) { expect(host.querySelector('[data-testid="ff-catalog-filter-count"]')?.textContent).toBe(text) }
async function click(testId: string) {
  const el = host.querySelector(`[data-testid="${testId}"]`)!
  expect(el).not.toBeNull()
  await act(async () => (el.querySelector('input') ?? el as HTMLElement).dispatchEvent(new MouseEvent('click', { bubbles: true })))
  await settle()
}
it('c1_selects_a_and_b_then_toggles_only_a_off', async () => {
  await mount(); await chooseCategory('A'); await chooseCategory('B')
  expectSelection(['A', 'B']); count('Найдено: 3 из 5')
  expect(host.textContent).not.toContain('C-one')
  await chooseCategory('A'); expectSelection(['B']); count('Найдено: 1 из 5')
  expect(host.querySelectorAll('[data-testid="ff-product-row"]')).toHaveLength(1)
  expect(host.textContent).toContain('B-one')
})
it('c3_last_category_and_all_categories_reset_only_category_and_allow_uncategorized', async () => {
  await mount(); await choose('ff-catalog-marketplace-filter', 'Wildberries')
  await chooseCategory('A'); await chooseCategory('B'); expectSelection(['A', 'B'])
  await chooseCategory('A'); await chooseCategory('B'); expectSelection([])
  expect(latest().get('marketplace')).toBe('wildberries'); count('Найдено: 5 из 5')
  expect(host.textContent).toContain('NO-category')
  await chooseCategory('A'); await chooseCategory('B'); await chooseCategory('Все категории'); expectSelection([])
  expect(host.querySelector('[data-testid="ff-catalog-category-filter"] [role="combobox"]')?.textContent).toContain('Все категории')
  await chooseCategory('A'); expectSelection(['A']); count('Найдено: 2 из 5')
})
it('c5_category_changes_reset_page_selection_and_seller_options_stay_scope_wide', async () => {
  // This DOM contract needs only two returned rows per HTTP page; SQL pagination
  // completeness is exercised by the backend C2 test. limit is an upper bound.
  data = largeData; sparsePages = true
  await mount(); await chooseCategory('A'); await closeMenu()
  const next = host.querySelector('[data-testid="ff-catalog-pagination"] button[aria-label="Go to next page"]') as HTMLButtonElement
  await act(async () => next.click()); await settle()
  expect(latest().get('offset')).toBe('100')
  await click('ff-catalog-select-A-100')
  expect(host.querySelector('[data-testid="ff-catalog-selection-count"]')?.textContent).toBe('Выбрано 1')
  await chooseCategory('B'); expectSelection(['A', 'B']); expect(latest().get('offset')).toBe('0'); await closeMenu()
  expect(host.querySelector('[data-testid="ff-catalog-selection-bar"]')).toBeNull()
  await click('ff-catalog-select-all')
  expect(host.querySelector('[data-testid="ff-catalog-selection-count"]')?.textContent).toBe('Выбрано 2')
  await act(async () => next.click()); await settle()
  expect(host.querySelector('[data-testid="ff-catalog-selection-bar"]')).toBeNull()
  await click('ff-catalog-select-all')
  await choose('ff-catalog-pagination', '50')
  expect(latest().get('limit')).toBe('50'); expect(latest().get('offset')).toBe('0')
  expect(host.querySelector('[data-testid="ff-catalog-selection-bar"]')).toBeNull()
  await choose('ff-catalog-seller-filter', 'Селлер 2'); expectSelection([])
  await chooseCategory('D'); expectSelection(['D'])
  // E remains available though no product in the current page has that category.
  const combo = host.querySelector('[data-testid="ff-catalog-category-filter"] [role="combobox"]')!
  if (!document.querySelector('[role="listbox"]')) await act(async () => combo.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 })))
  expect([...document.querySelectorAll('[role="option"]')].map(el => el.textContent)).toContain('E')
})
it('c6_old_a_response_cannot_replace_new_ab_result', async () => {
  await mount(); delayCategory = 'A'; await chooseCategory('A')
  expect(delayed).toHaveLength(1)
  await chooseCategory('B'); expectSelection(['A', 'B']); count('Найдено: 3 из 5')
  expect(delayed[0]!.signal?.aborted).toBe(true)
  await act(async () => delayed[0]!.resolve(json(page(delayed[0]!.params))))
  await settle(); count('Найдено: 3 из 5'); expectSelection(['A', 'B'])
})
it.each(['catalog', 'stock'] as const)('c6_error_%s_keeps_categories_editable_and_recovers_without_writes', async (source) => {
  await mount(); await chooseCategory('A'); failure = source; await chooseCategory('B'); expectSelection(['A', 'B'])
  expect(host.querySelector('[role="alert"]')?.textContent).toContain(source === 'catalog' ? 'Ошибка каталога 728' : 'Ошибка остатков 728')
  failure = null
  // Existing reload path is a filter change; it must retain the selected set.
  await closeMenu(); await click('ff-catalog-has-stock-filter'); expectSelection(['A', 'B']); count('Найдено: 3 из 5')
  expect(host.querySelector('[role="alert"]')).toBeNull()
  await chooseCategory('Все категории'); expectSelection([])
})
