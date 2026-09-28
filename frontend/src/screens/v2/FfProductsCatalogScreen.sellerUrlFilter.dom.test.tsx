// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfProductsCatalogScreen } from './FfProductsCatalogScreen'

// WMS-491, правка F2 (перекрёстное ревью Astra №1, docs/reviews/artifacts/wms-491/review-astra-1.md).
// Переход из карточки селлера (?seller_id=<id>) выставлял фильтр «Селлер», но
// повторный клик по пункту меню «Каталог» на уже смонтированном экране его не
// сбрасывал — react-router не размонтирует компонент при переходе на тот же
// маршрут. Нарушение R9/C9. Тест монтирует настоящий компонент (createRoot,
// реальные эффекты, реальный клик по ссылке меню), не статический рендер.
//
// Правка F6 (ревью Astra №2, docs/reviews/artifacts/wms-491/review-astra-2.md):
// эффект сброса выше считал новым входом из меню любую смену location.key без
// ?seller_id=, а его создаёт и собственная чистка ?fbs_limit= каталогом (окно
// раскладки остатка по складам WB) — фильтр слетал сам, без участия оператора.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const sellers = [
  { id: 'seller-a', name: 'WMS-491 Селлер А' },
  { id: 'seller-b', name: 'WMS-491 Селлер Б' },
]
const authHeaders = () => ({ Authorization: 'Bearer test' })

let host: HTMLDivElement
let root: Root

function Nav() {
  const loc = useLocation()
  return <>
    <Link data-testid="menu-catalog" to="/app/ff/products">Каталог</Link>
    <span data-testid="location">{loc.pathname}{loc.search}</span>
  </>
}

function currentSearch(): string {
  return host.querySelector('[data-testid="location"]')?.textContent?.split('?')[1] ?? ''
}

function response(data: unknown): Response {
  return { ok: true, json: async () => data } as Response
}

async function flush() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}

/** Ждёт, пока в дереве появится выпадающий список «Селлер» (первый рендер тяжёлого экрана растянут на несколько тиков). */
async function waitForSellerFilter() {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (host.querySelector('[data-testid="ff-catalog-seller-filter"] input')) return
    await flush()
  }
  throw new Error('ff-catalog-seller-filter did not render in time')
}

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/products/ff-catalog-page')) {
        return response({ items: [], total: 0, scope_total: 0, categories: [] })
      }
      return response([])
    }),
  )
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

async function mount(entry: string) {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[entry]}>
        <Nav />
        <Routes>
          <Route
            path="/app/ff/products"
            element={
              <FfProductsCatalogScreen
                token="test"
                authHeaders={authHeaders}
                sellers={sellers}
                warehouses={[]}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    )
  })
  await flush()
}

function sellerFilterValue(): string {
  const input = host.querySelector('[data-testid="ff-catalog-seller-filter"] input') as HTMLInputElement | null
  return input?.value ?? ''
}

async function clickMenuCatalog() {
  await act(async () => {
    (host.querySelector('[data-testid="menu-catalog"]') as HTMLElement).click()
  })
  await flush()
}

describe('FfProductsCatalogScreen — filter applied from ?seller_id= survives only until a fresh menu entry', () => {
  it('menu click after entry via seller card link resets the filter to «Все селлеры»', async () => {
    await mount('/app/ff/products?seller_id=seller-a')
    await waitForSellerFilter()
    expect(sellerFilterValue()).toBe('seller-a')

    await clickMenuCatalog()
    expect(sellerFilterValue()).toBe('')
  })

  it('menu click does not revert a filter the operator picked manually', async () => {
    await mount('/app/ff/products')
    await waitForSellerFilter()
    expect(sellerFilterValue()).toBe('')

    await act(async () => {
      const combobox = host.querySelector('[data-testid="ff-catalog-seller-filter"] [role="combobox"]') as HTMLElement
      combobox.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }))
    })
    await flush()
    const option = Array.from(document.querySelectorAll('li[role="option"]')).find(
      (node) => node.textContent === 'WMS-491 Селлер Б',
    ) as HTMLElement
    await act(async () => option.click())
    await flush()
    expect(sellerFilterValue()).toBe('seller-b')

    await clickMenuCatalog()
    expect(sellerFilterValue()).toBe('seller-b')
  })

  it('the catalog own cleanup of ?fbs_limit= does not drop the ?seller_id= filter (F6)', async () => {
    // ff-catalog-page отдаёт один товар, чтобы у каталога было что раскладывать
    // по складам; fbs_limit ссылается на несуществующий товар — окно раскладки
    // не откроется, но эффект всё равно чистит параметр из адреса (это и есть
    // источник лишней смены location.key).
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/products/ff-catalog-page')) {
          return response({
            items: [{
              id: 'product-a', seller_id: 'seller-a', seller_name: 'WMS-491 Селлер А',
              name: 'Товар А', sku_code: 'SKU-A', wb_nm_id: null, wb_vendor_code: null,
              wb_subject_name: null, wb_primary_image_url: null, wb_barcodes: [],
              wb_primary_barcode: null, wb_size: null, wb_color: null, wb_brand: null,
              wb_composition: null, packaging_instructions: null,
              requires_honest_sign: false, has_packaging_instructions: false,
            }],
            total: 1, scope_total: 1, categories: [],
          })
        }
        if (url.includes('/operations/inventory-balances/summary')) return response([])
        return response([])
      }),
    )

    await mount('/app/ff/products?seller_id=seller-a&fbs_limit=missing-product')
    await waitForSellerFilter()
    expect(sellerFilterValue()).toBe('seller-a')

    // Дожидаемся, пока каталог загрузится и собственный эффект fbs_limit
    // почистит свой параметр из адреса — меню оператор не нажимал.
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const search = new URLSearchParams(currentSearch())
      if (!search.has('fbs_limit') && !search.has('seller_id')) break
      await flush()
    }

    expect(sellerFilterValue()).toBe('seller-a')
    const finalSearch = new URLSearchParams(currentSearch())
    expect(finalSearch.has('seller_id')).toBe(false)
    expect(finalSearch.has('fbs_limit')).toBe(false)

    // Меню всё ещё сбрасывает фильтр — техническая чистка адреса не должна
    // была «израсходовать» будущую способность эффекта отличать вход из меню.
    await clickMenuCatalog()
    expect(sellerFilterValue()).toBe('')
  })
})
