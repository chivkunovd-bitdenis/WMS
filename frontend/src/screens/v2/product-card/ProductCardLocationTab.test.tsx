// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { ProductCardLocationTab } from './ProductCardLocationTab'
import type { WarehouseMapData } from '../../ff/warehouse-map/WarehouseMapTypes'

// WMS-490 R10, R11: вкладка «Расположение» — то же дерево «Карты склада»
// (`WarehouseMapTree` + `buildRows`), отфильтрованное сервером по одному
// товару. Здесь проверяется только подключение к серверу и переключатель
// складов на данных-заглушке; сам вид дерева и его действия — предмет тестов
// «Карты склада» (WarehouseMapRows.test.ts) и проверки глазами (см. отчёт
// куска D5).

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const PRODUCT_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const WH_A = { id: 'wh-a', name: 'Основной склад' }
const WH_B = { id: 'wh-b', name: 'Второй склад' }

function mapData(cellCode: string, qty: number): WarehouseMapData {
  return {
    warehouses: [],
    sellers: ['ИП Иванов'],
    categories: ['Футболки'],
    cells: [
      {
        id: `cell-${cellCode}`,
        code: cellCode,
        barcode: null,
        qty,
        children: [
          {
            kind: 'product',
            id: `bal-${cellCode}`,
            product_id: PRODUCT_ID,
            name: 'Футболка мужская Basic, белая, р.M',
            seller_name: 'ИП Иванов',
            category: 'Футболки',
            seller_article: 'TSHIRT-1',
            barcode: '1234567890123',
            photo_url: null,
            qty,
          },
        ],
      },
    ],
    unassigned: [],
    journal: [],
  }
}

const EMPTY_MAP: WarehouseMapData = {
  warehouses: [],
  sellers: [],
  categories: [],
  cells: [],
  unassigned: [],
  journal: [],
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function stubFetch(byWarehouse: Record<string, WarehouseMapData>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      const match = url.match(/\/warehouses\/([^/]+)\/map/)
      if (match) {
        const data = byWarehouse[match[1]!]
        return data ? jsonResponse(200, data) : jsonResponse(404, { detail: 'warehouse_not_found' })
      }
      return jsonResponse(200, {})
    }),
  )
}

// Стабильная ссылка: в настоящем приложении `authHeaders` приходит от App.tsx
// один раз и не создаётся заново на каждый рендер. Инлайновая стрелочная
// функция здесь заставляла бы `load` (useCallback от authHeaders) менять
// идентичность на каждый `renderTab`, а «всегда грузить» эффект — читать
// заново независимо от `active`, что не соответствует настоящему поведению.
const authHeaders = () => ({ Authorization: 'Bearer t' })

let root: Root | null = null
let host: HTMLDivElement | null = null
async function renderTab(locationWarehouses: Array<{ id: string; name: string }>, active: boolean) {
  await act(async () => {
    root!.render(
      <ProductCardLocationTab
        productId={PRODUCT_ID}
        token="t"
        authHeaders={authHeaders}
        locationWarehouses={locationWarehouses}
        onNotFound={() => {}}
        onStockChanged={() => {}}
        stockVersion={0}
        active={active}
      />,
    )
  })
}
async function mount(locationWarehouses: Array<{ id: string; name: string }>, active = true) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await renderTab(locationWarehouses, active)
}
afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

const maybe = (testId: string) => document.querySelector(`[data-testid="${testId}"]`)

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
}

describe('WMS-490 R10: вкладка «Расположение» на одном складе', () => {
  it('дерево показывает место и штуки товара, переключателя складов нет', async () => {
    stubFetch({ [WH_A.id]: mapData('А-1.1', 3) })
    await mount([WH_A])
    await flush()

    expect(maybe('warehouse-map-warehouses')).toBeNull()
    expect(maybe('warehouse-map-table')?.textContent).toContain('А-1.1')
    expect(maybe('warehouse-map-table')?.textContent).toContain('Футболка мужская Basic, белая, р.M')
  })
})

describe('WMS-490 R10: вкладка «Расположение» на нескольких складах', () => {
  it('переключатель складов виден и переключает дерево на данные другого склада', async () => {
    stubFetch({ [WH_A.id]: mapData('А-1.1', 3), [WH_B.id]: mapData('Б-2.4', 1) })
    await mount([WH_A, WH_B])
    await flush()

    expect(maybe('warehouse-map-warehouses')).not.toBeNull()
    expect(maybe('warehouse-map-table')?.textContent).toContain('А-1.1')
    expect(maybe('warehouse-map-table')?.textContent).not.toContain('Б-2.4')

    await act(async () => {
      document
        .querySelector<HTMLElement>(`[data-testid="warehouse-map-warehouse-${WH_B.id}"]`)
        ?.click()
    })
    await flush()

    expect(maybe('warehouse-map-table')?.textContent).toContain('Б-2.4')
    expect(maybe('warehouse-map-table')?.textContent).not.toContain('А-1.1')
  })
})

describe('WMS-490 R10: товар без размещения', () => {
  it('пустое состояние «Товара нет на складе» без запроса к серверу', async () => {
    stubFetch({})
    await mount([])
    await flush()

    expect(maybe('warehouse-map-warehouses')).toBeNull()
    expect(maybe('warehouse-map-table')?.textContent).toContain('Товара нет на складе')
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('карта склада пуста после фильтра — то же пустое состояние', async () => {
    stubFetch({ [WH_A.id]: EMPTY_MAP })
    await mount([WH_A])
    await flush()

    expect(maybe('warehouse-map-table')?.textContent).toContain('Товара нет на складе')
  })
})

describe('ревью №1 F2: сбой загрузки и возврат на вкладку', () => {
  it('ошибка остаётся при уходе с вкладки и повторяет запрос при возврате; переключатель остаётся виден', async () => {
    let call = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        call += 1
        if (call === 1) return jsonResponse(500, { detail: 'boom' })
        return jsonResponse(200, mapData('А-1.1', 3))
      }),
    )
    await mount([WH_A, WH_B], true)
    await flush()
    expect(maybe('product-card-location-error')).not.toBeNull()
    // Переключатель остаётся доступен даже при ошибке — раньше ранний return
    // прятал его вместе со всей вкладкой (ревью №1 F2).
    expect(maybe('warehouse-map-warehouses')).not.toBeNull()

    // Уход с вкладки: ошибка остаётся (второй запрос не улетает сам по себе).
    await renderTab([WH_A, WH_B], false)
    await flush()
    expect(call).toBe(1)

    // Возврат на вкладку повторяет запрос без явного действия оператора.
    await renderTab([WH_A, WH_B], true)
    await flush()
    expect(call).toBe(2)
    expect(maybe('product-card-location-error')).toBeNull()
    expect(maybe('warehouse-map-table')?.textContent).toContain('А-1.1')
  })
})
