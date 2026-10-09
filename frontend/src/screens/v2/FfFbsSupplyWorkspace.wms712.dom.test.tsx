// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import type { FbsWorkspace } from './fbsApi'
import { saveFbsWorkspaceStage } from './fbsWorkspaceStage'
import * as packingScan from './fbsSequentialPacking'

// WMS-712: предупреждение о недоборе на вкладке «Упаковка и маркировка».
// Тесты читают только сохранённые ответы сервера (фикстуры ниже) и не открывают
// ни печать, ни запись. Любой не-GET запрос записывается и получает 503.

vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
vi.mock('../../utils/useMarkingCodePrint', () => ({ useMarkingCodePrint: () => ({ openPrint: vi.fn(), dialog: null }) }))
vi.mock('./FbsSupplyHistoryDialog', () => ({ FbsSupplyHistoryDialog: () => null }))
vi.mock('./FbsPrintPreviewDialog', () => ({ FbsPrintPreviewDialog: () => null }))
vi.mock('./FbsTransferSupplyDialog', () => ({ FbsTransferSupplyDialog: () => null, makeFbsTransferSupplyDeps: () => ({}) }))

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})

const SUPPLY_ID = 'supply-wms712'
const PACKAGING_TASK_ID = 'task-wms712'
const SHORTAGE_PREFIX = 'Не подобрана'

// Условные товары фикстуры. Названия и артикулы из клиентской переписки не используются (Q5).
const SHIRT = { id: 'product-shirt-712', name: 'Футболка белая', article: 'ART-A' }
const HOODIE = { id: 'product-hoodie-712', name: 'Худи серое', article: 'ART-B' }
const TROUSERS = { id: 'product-trousers-712', name: 'Брюки чёрные', article: 'ART-C' }
const MUG = { id: 'product-mug-712', name: 'Кружка керамическая', article: 'OZ-MUG' }
const SPOON = { id: 'product-spoon-712', name: 'Ложка чайная', article: 'OZ-SPOON' }

type Product = typeof SHIRT
type Line = { product: Product; quantity: number; picked: number }

const packagingTask = {
  id: PACKAGING_TASK_ID,
  document_number: 'PK-712',
  warehouse_id: 'warehouse-712',
  warehouse_name: 'Основной склад',
  status: 'in_progress',
  marketplace_unload_request_id: null,
  inbound_intake_request_id: null,
  is_complete: false,
  lines: [],
  events: [],
}

function order(index: number, marketplace: 'wb' | 'ozon', lines: Line[]) {
  const allPicked = lines.every((line) => line.picked === line.quantity)
  const first = lines[0].product
  return {
    id: `order-712-${index}`,
    marketplace,
    external_order_id: marketplace === 'ozon' ? `ozon-712-${index}` : null,
    wb_order_id: 712000 + index,
    status: 'assembling',
    wb_status: null,
    supplier_status: null,
    seller: { id: 'seller-712', name: 'ИП Тестовый' },
    wb_warehouse: { id: 507, name: 'Коледино' },
    wms_warehouse: { id: 'warehouse-712', name: 'Основной склад' },
    product: {
      id: first.id,
      name: first.name,
      image_url: null,
      seller_article: first.article,
      wb_article: null,
      barcode: null,
      sku: null,
      chrt_id: null,
      category: null,
      color: null,
      size: null,
    },
    positions: lines.map((line) => ({
      id: `position-712-${index}-${line.product.id}`,
      image_url: null,
      barcode: null,
      product_id: line.product.id,
      marketplace_bindings: [],
      name: line.product.name,
      seller_article: line.product.article,
      sku: null,
      size: null,
      color: null,
      brand: null,
      composition: null,
      quantity: line.quantity,
      reserved_quantity: line.quantity,
      picked_quantity: line.picked,
    })),
    inventory: { available_unpacked: 0, locations: [] },
    buyer_type: 'individual',
    cargo_type: 'mono',
    can_pvz: false,
    delivery_route: null,
    metadata: { required: [], optional: [], states: [] },
    sticker: { code: `STK-712-${index}`, status: 'ready', asset_url: null, applied_at: null },
    pick: { status: allPicked ? 'picked' : 'pending', location_code: null, picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: '2026-10-08T10:00:00+03:00',
    deadline_at: '2026-10-12T12:00:00+03:00',
    supply_id: SUPPLY_ID,
    selection_blockers: [],
    tape_order_index: index,
  }
}

// Прогресс считается так же, как на сервере: по позициям заказа.
function workspaceOf(marketplace: 'wb' | 'ozon', orders: ReturnType<typeof order>[]): FbsWorkspace {
  const positions = orders.flatMap((item) => item.positions)
  const total = positions.reduce((sum, position) => sum + position.quantity, 0)
  const picked = positions.reduce((sum, position) => sum + position.picked_quantity, 0)
  return {
    supply: {
      id: SUPPLY_ID,
      marketplace,
      wb_supply_id: marketplace === 'wb' ? 'WB-GI-712' : null,
      source: 'wms',
      name: 'Поставка WMS-712',
      status: 'assembling',
      delivery_type: 'warehouse_sc',
      seller: { id: 'seller-712', name: 'ИП Тестовый' },
      wb_warehouse: { id: 507, name: 'Коледино' },
      wms_warehouse: { id: 'warehouse-712', name: 'Основной склад' },
      planned_destination: null,
      planned_shipment_date: null,
      nearest_deadline_at: '2026-10-12T12:00:00+03:00',
      packaging_task_id: PACKAGING_TASK_ID,
      barcode_asset: null,
    },
    stage: picked < total ? 'picking' : 'packing',
    progress: { picked, packed: 0, metadata_ready: orders.length, stickers_ready: orders.length, total },
    // C4: навигационные блокеры сервер не публикует, список всегда пуст.
    blockers: [],
    orders,
    cargo_places: [],
    boxes: [],
    delivery_preflight: null,
    last_wb_sync_at: null,
    server_now: '2026-10-09T12:00:00+03:00',
  } as unknown as FbsWorkspace
}

function forAssembly(base: FbsWorkspace, supplyId: string, taskId: string): FbsWorkspace {
  return {
    ...base,
    supply: { ...base.supply, id: supplyId, name: `Поставка ${supplyId}`, packaging_task_id: taskId },
    orders: base.orders.map((item, index) => ({
      ...item,
      id: `${supplyId}-${index}`,
      supply_id: supplyId,
      positions: item.positions.map((position, positionIndex) => ({
        ...position,
        id: `${supplyId}-${index}-${positionIndex}`,
      })),
    })),
  }
}

// C1, C3, C7, C9: одна недостающая штука у одного товара.
const oneShortage = workspaceOf('wb', [
  order(0, 'wb', [{ product: SHIRT, quantity: 1, picked: 1 }]),
  order(1, 'wb', [{ product: SHIRT, quantity: 1, picked: 0 }]),
  order(2, 'wb', [{ product: HOODIE, quantity: 1, picked: 1 }]),
])

// C2: подбор полный.
const fullyPicked = workspaceOf('wb', [
  order(0, 'wb', [{ product: SHIRT, quantity: 1, picked: 1 }]),
  order(1, 'wb', [{ product: HOODIE, quantity: 1, picked: 1 }]),
])

// C5: товар в трёх заказах, один подобран (недобор 2); товар без недобора; товар с недобором 1.
// Итог 6, подобрано 3, сумма строк предупреждения должна быть 3.
const groupedShortage = workspaceOf('wb', [
  order(0, 'wb', [{ product: SHIRT, quantity: 1, picked: 1 }]),
  order(1, 'wb', [{ product: SHIRT, quantity: 1, picked: 0 }]),
  order(2, 'wb', [{ product: SHIRT, quantity: 1, picked: 0 }]),
  order(3, 'wb', [{ product: HOODIE, quantity: 1, picked: 1 }]),
  order(4, 'wb', [{ product: HOODIE, quantity: 1, picked: 1 }]),
  order(5, 'wb', [{ product: TROUSERS, quantity: 1, picked: 0 }]),
])

// C6: заказ Ozon с двумя позициями; недобрана только одна штука первой позиции.
const ozonTwoPositions = workspaceOf('ozon', [
  order(0, 'ozon', [
    { product: MUG, quantity: 3, picked: 2 },
    { product: SPOON, quantity: 1, picked: 1 },
  ]),
])

// C9: до сбоя — недобор 2, после повтора — недобор 1.
const staleShortage = workspaceOf('wb', [
  order(0, 'wb', [{ product: SHIRT, quantity: 1, picked: 0 }]),
  order(1, 'wb', [{ product: SHIRT, quantity: 1, picked: 0 }]),
])
const freshShortage = workspaceOf('wb', [
  order(0, 'wb', [{ product: SHIRT, quantity: 1, picked: 1 }]),
  order(1, 'wb', [{ product: SHIRT, quantity: 1, picked: 0 }]),
])

const originalFetch = globalThis.fetch
const authHeaders = (_token: string) => ({ Authorization: 'Bearer token-wms712' })
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json' },
})

let current: FbsWorkspace
let workspaceStatus: number
let requests: string[]
let host: HTMLDivElement
let root: Root

beforeEach(() => {
  window.sessionStorage.clear()
  window.localStorage.clear()
  requests = []
  workspaceStatus = 200
  current = oneShortage
  // Открываем сразу вкладку упаковки: сохранённый этап — то же, что выбрал бы оператор.
  saveFbsWorkspaceStage(SUPPLY_ID, 'packing')
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
    const method = (init?.method ?? 'GET').toUpperCase()
    const path = url.pathname.replace(/^\/api/, '')
    requests.push(`${method} ${path}`)
    if (method !== 'GET') return json({ detail: 'WMS-712 test: записи не ожидаются' }, 503)
    if (path.endsWith(`/fbs-supplies/${SUPPLY_ID}/workspace`)) {
      return workspaceStatus === 200 ? json(current) : json({ detail: 'WMS-712 test: сбой загрузки' }, workspaceStatus)
    }
    if (path.endsWith(`/packaging-tasks/${PACKAGING_TASK_ID}`)) return json(packagingTask)
    return json({ detail: 'WMS-712 test: неожиданное чтение' }, 503)
  }) as typeof fetch
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  globalThis.fetch = originalFetch
  Reflect.deleteProperty(document, 'visibilityState')
  vi.restoreAllMocks()
})

async function renderCard(options: { open?: boolean; initial?: FbsWorkspace | null; stage?: 'picking' | 'packing' } = {}) {
  if (options.stage) saveFbsWorkspaceStage(SUPPLY_ID, options.stage)
  await act(async () => {
    root.render(
      <FfFbsSupplyWorkspace
        token="token-wms712"
        authHeaders={authHeaders}
        supplyId={SUPPLY_ID}
        initialWorkspace={options.initial ?? null}
        open={options.open ?? true}
        onClose={() => undefined}
      />,
    )
  })
}

async function settle(ms = 0) {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)) })
}

async function waitForRows(count: number) {
  await vi.waitFor(() => {
    expect(document.querySelectorAll('[data-order-id]')).toHaveLength(count)
  }, { timeout: 5_000 })
}

// Строки предупреждения: самые внутренние элементы, текст которых начинается с «Не подобрана».
function shortageLines(): string[] {
  const hits = [...document.querySelectorAll<HTMLElement>('body *')]
    .filter((element) => (element.textContent ?? '').trim().startsWith(SHORTAGE_PREFIX))
  return hits
    .filter((element) => ![...element.querySelectorAll<HTMLElement>('*')]
      .some((child) => (child.textContent ?? '').trim().startsWith(SHORTAGE_PREFIX)))
    .map((element) => (element.textContent ?? '').trim())
}

function tab(label: string): HTMLElement {
  const found = [...document.querySelectorAll<HTMLElement>('[role="tab"]')]
    .find((element) => element.textContent?.startsWith(label))
  if (!found) throw new Error(`WMS-712 test: вкладка «${label}» не найдена`)
  return found
}

function buttonByTestId(testId: string): HTMLButtonElement | null {
  return document.querySelector<HTMLButtonElement>(`[data-testid="${testId}"]`)
}

function buttonByText(label: string): HTMLButtonElement | undefined {
  return [...document.querySelectorAll<HTMLButtonElement>('button')]
    .find((element) => element.textContent?.trim().startsWith(label))
}

describe('WMS-712 · предупреждение о недоборе на упаковке (веб-карточка)', () => {
  it('C1: при недоборе на упаковке видна строка «Не подобрана 1 штука» с названием и артикулом товара, строки всех заказов на месте', async () => {
    await renderCard()
    await waitForRows(3)

    expect(shortageLines()).toEqual(['Не подобрана 1 штука: Футболка белая, ART-A'])
    const line = [...document.querySelectorAll<HTMLElement>('body *')]
      .find((element) => element.textContent?.trim() === 'Не подобрана 1 штука: Футболка белая, ART-A')!
    const rows = document.querySelector('[data-testid="fbs-unified-packing-rows"]')!
    const firstRow = document.querySelector('[data-order-id]')!
    // Строка стоит внутри блока упаковки и выше первой строки заказа.
    expect(rows.contains(line)).toBe(true)
    expect(line.compareDocumentPosition(firstRow) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('C2: при полном подборе предупреждения о недоборе нет', async () => {
    current = fullyPicked
    await renderCard()
    await waitForRows(2)

    expect(shortageLines()).toEqual([])
    expect(document.body.textContent?.includes(SHORTAGE_PREFIX)).toBe(false)
  })

  // Тайм-аут 30 с: сценарий открывает разные вкладки подряд; на машине под нагрузкой
  // он не укладывается в стандартные 5 с. Проверки внутри не смягчены.
  it('C3: при недоборе вкладки, «Далее», печать и действия не заблокированы; записей при переходе нет', { timeout: 30_000 }, async () => {
    await renderCard({ stage: 'picking' })
    await vi.waitFor(() => {
      expect(buttonByTestId('fbs-pick-list-print')).not.toBeNull()
    }, { timeout: 5_000 })

    // Подбор: «Далее» ведёт к упаковке и не заблокирован.
    expect(buttonByTestId('fbs-stage-next-picking')?.disabled, 'Далее с подбора').toBe(false)
    expect(buttonByTestId('fbs-pick-list-print')?.disabled, 'печать листа подбора').toBe(false)
    await act(async () => tab('Упаковка и маркировка').click())
    await waitForRows(3)

    for (const label of ['Состав', 'Подбор', 'Упаковка и маркировка', 'Короба']) {
      const element = tab(label) as HTMLButtonElement
      expect(element.disabled, `вкладка «${label}» открыта`).toBe(false)
    }
    expect(buttonByTestId('fbs-stage-next-packing')?.disabled, 'Далее с упаковки').toBe(false)
    expect(buttonByText('Далее: Короба')?.disabled, 'кнопка «Далее: Короба»').toBe(false)

    // Переход назад и вперёд не должен писать на сервер.
    await act(async () => tab('Подбор').click())
    await act(async () => tab('Упаковка и маркировка').click())
    await settle(50)
    expect(requests.filter((request) => !request.startsWith('GET ')), 'записи при переходах').toEqual([])
  })

  it('C5: недобор товара суммируется по заказам; товар без недобора не выводится; сумма строк равна итог минус подобрано', async () => {
    current = groupedShortage
    await renderCard()
    await waitForRows(6)

    const lines = shortageLines()
    expect(lines).toHaveLength(2)
    expect(lines).toEqual(expect.arrayContaining([
      'Не подобрана 2 штуки: Футболка белая, ART-A',
      'Не подобрана 1 штука: Брюки чёрные, ART-C',
    ]))
    expect(lines.some((line) => line.includes('ART-B'))).toBe(false)
    const summed = lines.reduce((sum, line) => sum + Number(/^Не подобрана (\d+)/.exec(line)?.[1] ?? 0), 0)
    expect(summed).toBe(groupedShortage.progress.total - groupedShortage.progress.picked)
  })

  it('C6: заказ Ozon с двумя позициями — выводится только недобранная позиция', async () => {
    current = ozonTwoPositions
    await renderCard()
    await waitForRows(1)

    expect(shortageLines()).toEqual(['Не подобрана 1 штука: Кружка керамическая, OZ-MUG'])
  })

  // Тайм-аут 30 с: сценарий открывает карточку дважды; см. пояснение у C3.
  it('C7: блок есть до подбора и исчезает после подбора недостающей единицы и обновления', { timeout: 30_000 }, async () => {
    await renderCard()
    await waitForRows(3)
    expect(shortageLines()).toEqual(['Не подобрана 1 штука: Футболка белая, ART-A'])

    // Оператор подбирает недостающую штуку (на сервере появляется подбор), затем экран открывается заново.
    current = fullyPicked
    await renderCard({ open: false })
    await renderCard({ open: true })
    await waitForRows(2)

    expect(shortageLines()).toEqual([])
  })

  it('C8: в групповой сборке предупреждение есть только у поставки с недобором', async () => {
    const supplyIds = ['supply-wms712-short', 'supply-wms712-complete']
    const groupedWorkspaces = new Map([
      [supplyIds[0], forAssembly(oneShortage, supplyIds[0], 'task-wms712-short')],
      [supplyIds[1], forAssembly(fullyPicked, supplyIds[1], 'task-wms712-complete')],
    ])
    window.sessionStorage.setItem(`wms:fbs:assembly:${supplyIds.join(',')}:stage`, 'packing')
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
      const method = (init?.method ?? 'GET').toUpperCase()
      const path = url.pathname.replace(/^\/api/, '')
      requests.push(`${method} ${path}`)
      if (method !== 'GET') return json({ detail: 'WMS-712 C8: записи не ожидаются' }, 503)
      const supply = [...groupedWorkspaces].find(([id]) => path.endsWith(`/fbs-supplies/${id}/workspace`))
      if (supply) return json(supply[1])
      const taskId = [...groupedWorkspaces.values()].map((item) => item.supply.packaging_task_id)
        .find((id) => path.endsWith(`/packaging-tasks/${id}`))
      if (taskId) return json({ ...packagingTask, id: taskId })
      return json({ detail: 'WMS-712 C8: неожиданное чтение' }, 503)
    }) as typeof fetch

    await act(async () => {
      root.render(<FfFbsSupplyAssembly
        token="token-wms712"
        authHeaders={authHeaders}
        supplyIds={supplyIds}
        open
        onClose={() => undefined}
      />)
    })

    await vi.waitFor(() => {
      expect(document.querySelectorAll('[data-testid="fbs-unpicked-warning"]')).toHaveLength(1)
    }, { timeout: 5_000 })
    expect(shortageLines()).toEqual(['Не подобрана 1 штука: Футболка белая, ART-A'])
    expect(document.querySelectorAll('[data-order-id]')).toHaveLength(5)
    expect(requests.filter((request) => !request.startsWith('GET '))).toEqual([])
  })

  it('C9: после сбоя обновления старое предупреждение не остаётся, после повтора показаны новые числа', { timeout: 60_000 }, async () => {
    // Окно видимо: тихое обновление раз в 15 секунд работает только при видимой вкладке.
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
    current = staleShortage
    await renderCard()
    await waitForRows(2)
    expect(shortageLines()).toEqual(['Не подобрана 2 штуки: Футболка белая, ART-A'])

    // Следующее тихое обновление падает с ошибкой сервера.
    workspaceStatus = 500
    const workspaceReadsBefore = requests.filter((request) => request.endsWith(`/fbs-supplies/${SUPPLY_ID}/workspace`)).length
    await vi.waitFor(() => {
      expect(requests.filter((request) => request.endsWith(`/fbs-supplies/${SUPPLY_ID}/workspace`)).length)
        .toBeGreaterThan(workspaceReadsBefore)
    }, { timeout: 25_000, interval: 250 })
    await settle(50)
    expect(shortageLines().some((line) => line.startsWith('Не подобрана 2 штуки')), 'старое предупреждение после сбоя').toBe(false)

    // Повтор: сервер отвечает, экран открывается заново и получает новый снимок.
    workspaceStatus = 200
    current = freshShortage
    await renderCard({ open: false })
    await renderCard({ open: true })
    await waitForRows(2)

    expect(shortageLines()).toEqual(['Не подобрана 1 штука: Футболка белая, ART-A'])
  })

  it('C12: старый запрос завершился ошибкой после успешного более нового обновления — warning остаётся по данным нового workspace', async () => {
    // Наблюдаем существующий callback фонового обновления, переданный сканеру.
    // Сам callback и load(true) настоящие; сканирование не выполняем, таймеров не ждём.
    const scanDeps = vi.spyOn(packingScan, 'makePackingScanDeps')
    await renderCard({ initial: groupedShortage })
    expect(document.querySelectorAll('[data-order-id]')).toHaveLength(6)
    expect(shortageLines()).toHaveLength(2)
    const refresh = scanDeps.mock.calls.at(-1)?.[4]
    if (!refresh) throw new Error('WMS-712 C12: callback обновления workspace не зарегистрирован')

    // Управляем только границей чтения: оба запроса остаются незавершёнными,
    // пока тест явно не выдаст ответ. Остальные GET обслуживает прежняя обвязка.
    const fixtureFetch = globalThis.fetch
    const pendingLoads: Array<{
      resolve: (response: Response) => void
      reject: (cause: Error) => void
    }> = []
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
      const method = (init?.method ?? 'GET').toUpperCase()
      const path = url.pathname.replace(/^\/api/, '')
      if (method === 'GET' && path.endsWith(`/fbs-supplies/${SUPPLY_ID}/workspace`)) {
        requests.push(`${method} ${path}`)
        return new Promise<Response>((resolve, reject) => pendingLoads.push({ resolve, reject }))
      }
      return fixtureFetch(input, init)
    }) as typeof fetch

    // Callback начинает A сразу, затем refreshPackagingTask после своего GET
    // начинает B. Оба чтения workspace удерживаем до явного ответа теста.
    await act(async () => { refresh() })
    expect(pendingLoads).toHaveLength(2)

    await act(async () => { pendingLoads[1].resolve(json(freshShortage)) })
    // Шесть старых строк сменились двумя строками B, недобор теперь одна штука.
    expect(document.querySelectorAll('[data-order-id]')).toHaveLength(2)
    expect(shortageLines()).toEqual(['Не подобрана 1 штука: Футболка белая, ART-A'])

    await act(async () => { pendingLoads[0].reject(new Error('WMS-712 C12: запоздалая ошибка A')) })
    expect(document.querySelectorAll('[data-order-id]')).toHaveLength(2)
    expect(requests.filter((request) => !request.startsWith('GET '))).toEqual([])
    expect(shortageLines(), 'ошибка старого A не должна скрывать предупреждение свежего workspace B')
      .toEqual(['Не подобрана 1 штука: Футболка белая, ART-A'])
  })

  it('C11: на вкладке «Подбор» предупреждения о недоборе нет, кнопка печати листа подбора на месте', async () => {
    await renderCard({ stage: 'picking' })
    await vi.waitFor(() => {
      expect(buttonByTestId('fbs-pick-list-print')).not.toBeNull()
    }, { timeout: 5_000 })
    await settle(50)

    expect(shortageLines()).toEqual([])
    expect(document.body.textContent?.includes(SHORTAGE_PREFIX)).toBe(false)
  })
})
