// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsOrdersScreen } from './FfFbsOrdersScreen'
import {
  fetchFbsWorklist,
  type FbsWorklistOrder,
  type FbsWorklistPage,
} from './fbsApi'

// WMS-692: «Просрочены» убрана, просроченный WB-заказ остаётся в «Новых» с плашкой срока
// и выбираемой галкой. Экран подключён к сети через fbsApi, поэтому API подменяем целиком.
vi.mock('./fbsApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./fbsApi')>()
  return {
    ...actual,
    fetchFbsWorklist: vi.fn(),
    fetchFbsSupplyWorklist: vi.fn(async () => ({
      items: [],
      total: 0,
      next_cursor: null,
      server_now: '2026-10-09T10:00:00.000Z',
    })),
    fetchFbsAssemblyTasks: vi.fn(async () => ({ items: [] })),
    fetchFbsSellerWarehouses: vi.fn(async () => ({ items: [] })),
  }
})

// Срок считаем от текущих часов: и плашка, и блокировка галки сравнивают срок с реальным временем.
const SERVER_NOW = new Date().toISOString()
const OVERDUE = new Date(Date.now() - 60 * 60 * 1000).toISOString()

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

function order(overrides: Partial<FbsWorklistOrder> & Pick<FbsWorklistOrder, 'id'>): FbsWorklistOrder {
  return {
    marketplace: 'wb',
    external_order_id: null,
    wb_order_id: 800801,
    status: 'new',
    wb_status: 'new',
    supplier_status: 'new',
    seller: { id: 'seller-1', name: 'Селлер А' },
    wb_warehouse: { id: 501001, name: 'Коледино' },
    wms_warehouse: { id: 'wh-1', name: 'Основной склад' },
    product: {
      id: 'product-1',
      name: 'Футболка',
      image_url: null,
      seller_article: 'ART-692',
      wb_article: 692,
      barcode: 'BAR-692',
      sku: 'SKU-692',
      chrt_id: 692001,
      category: 'Футболки',
      color: 'белый',
      brand: 'Brand',
      composition: 'хлопок',
      size: 'L',
    },
    positions: [],
    inventory: { available_unpacked: 5, locations: [] },
    buyer_type: 'individual',
    cargo_type: 'mgt',
    can_pvz: true,
    delivery_route: null,
    metadata: { required: [], optional: [], states: [], delivery_allowed: true, last_checked_at: null },
    sticker: { code: null, status: 'not_requested', asset_url: null, applied_at: null },
    pick: { status: 'pending', location_code: null, picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: '2026-10-08T09:00:00.000Z',
    deadline_at: OVERDUE,
    supply_id: null,
    selection_blockers: [],
    ...overrides,
  }
}

function page(items: FbsWorklistOrder[]): FbsWorklistPage {
  return {
    total: items.length,
    items,
    next_cursor: null,
    server_now: SERVER_NOW,
    warehouse_options: [
      { id: '501001', name: 'Коледино', wb_warehouse: { id: 501001, name: 'Коледино' } },
    ],
  }
}

let root: Root | null = null
let host: HTMLDivElement | null = null

beforeEach(() => {
  vi.mocked(fetchFbsWorklist).mockReset()
})

afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
})

async function renderScreen(items: FbsWorklistOrder[]): Promise<void> {
  vi.mocked(fetchFbsWorklist).mockResolvedValue(page(items))
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(
      <MemoryRouter>
        <FfFbsOrdersScreen token="test-token" authHeaders={() => ({})} sellers={[]} />
      </MemoryRouter>,
    )
  })
}

async function waitForRow(id: string): Promise<HTMLElement> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    const row = document.querySelector<HTMLElement>(`[data-testid="fbs-order-${id}"]`)
    if (row) return row
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  }
  throw new Error(`Строка ${id} не появилась на экране`)
}

describe('WMS-692: вкладки «Заказы FBS»', () => {
  it('показывает пять вкладок и не показывает «Просрочены» с подсказкой FBS-03', async () => {
    await renderScreen([order({ id: 'wb-overdue' })])
    await waitForRow('wb-overdue')

    // Берём набор вкладок статусов заказов: в разделе есть ещё навигация по разделам ФБС.
    const statusTabs = [...document.querySelectorAll('[role="tablist"]')]
      .find((list) => list.textContent?.includes('Новые'))
    expect(statusTabs, 'набор вкладок статусов заказов не найден').toBeDefined()
    const labels = [...statusTabs!.querySelectorAll('[role="tab"]')]
      .map((tab) => tab.textContent?.trim())
    expect(labels).toEqual(['Новые', 'В работе', 'В доставке', 'Завершённые', 'Отменённые'])
    expect(document.querySelector('[data-task-id="FBS-03"]')).toBeNull()
  })
})

describe('WMS-692: просроченный заказ в «Новых»', () => {
  it('оставляет WB-заказ с прошедшим сроком выбираемым и показывает плашку «Просрочен»', async () => {
    await renderScreen([
      order({ id: 'wb-overdue' }),
      order({
        id: 'ozon-overdue',
        marketplace: 'ozon',
        external_order_id: 'ozon-692',
        wb_order_id: 900692,
        wb_warehouse: { id: 0, name: null },
      }),
    ])

    const wbRow = await waitForRow('wb-overdue')
    const wbCheckbox = wbRow.querySelector<HTMLInputElement>('input[type="checkbox"]')
    expect(wbCheckbox?.disabled).toBe(false)
    expect(wbRow.textContent).not.toContain('Срок сборки истёк')
    const wbPill = wbRow.querySelector('[data-testid="fbs-deadline-pill"]')
    expect(wbPill?.textContent).toBe('Просрочен')
    expect(wbPill?.getAttribute('data-overdue')).toBe('true')

    const ozonRow = await waitForRow('ozon-overdue')
    const ozonCheckbox = ozonRow.querySelector<HTMLInputElement>('input[type="checkbox"]')
    expect(ozonCheckbox?.disabled).toBe(false)
    expect(ozonRow.querySelector('[data-testid="fbs-deadline-pill"]')).toBeNull()
  })

  it('не выводит подпись маркировки у просроченного заказа в «Новых»', async () => {
    await renderScreen([
      order({
        id: 'wb-marking',
        metadata: {
          required: ['chz'],
          optional: [],
          states: [{ id: 'state-1', kind: 'chz', status: 'missing', reason: null }],
          delivery_allowed: false,
          last_checked_at: null,
        },
      }),
    ])

    const row = await waitForRow('wb-marking')
    expect(row.textContent).not.toContain('Не хватает честных знаков')
    expect(row.textContent).not.toContain('Отклонено WB')
    expect(row.querySelector('[data-testid="fbs-order-wb-marking-marking-issue"]')).toBeNull()
  })
})
