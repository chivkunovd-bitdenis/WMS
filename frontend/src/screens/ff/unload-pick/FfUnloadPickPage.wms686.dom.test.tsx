// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfUnloadPickPage } from './FfUnloadPickPage'

// WMS-686 · контракт вкладки «Подбор» отгрузки FBO (docs/requirements/WMS-686.md,
// разделы 5, 9 и 10). Настоящий FfUnloadPickPage с настоящим экраном подбора;
// подменена только сеть: globalThis.fetch отвечает подставным сервером этого
// файла по формам ответов API (раздел 9). Сканер — «клавиатурный»: символы и
// Enter туда, где сейчас фокус, как в UnloadPickScreen.scan.dom.test.tsx.
// Неизвестный маршрут получает 404 с телом и записывается — каждый тест в конце
// проверяет, что таких обращений не было, чтобы 404 не маскировал ошибку.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const REQUEST_ID = 'mp-686'
const BASE = `/operations/marketplace-unload-requests/${REQUEST_ID}`
const SELLER_ID = 'seller-686'

const PRODUCT = {
  id: 'p-a',
  sku: 'SKU-686-A',
  name: 'Футболка хлопковая 48',
  barcode: '4600000000011',
  gtin: '04600000000011',
  plan: 5,
}
const CELL = { id: 'loc-1', code: 'А-1-1' }
const BOX_K1 = { id: 'box-k1', code: 'INB-000123' }
const BOX_K2 = { id: 'box-k2', code: 'INB-000124' }
/** Сколько единиц товара лежит в каждом источнике ячейки А-1-1 до подбора. */
const CONTENT: Record<string, number> = { [BOX_K1.id]: 3, [BOX_K2.id]: 3, loose: 2 }
/** КИЗ формата GS1: 01 + GTIN-14 + 21 + серийный номер (D1). */
const KIZ_1 = `01${PRODUCT.gtin}21AbCdEf000001`
/** КИЗ с GTIN, которого нет в карточках селлера. */
const KIZ_UNKNOWN_GTIN = '010469999999999021ZzZz000009'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const isKiz = (code: string) => /^01\d{14}21/.test(code) || /^\(01\)\d{14}\(21\)/.test(code)

type Recorded = {
  method: string
  path: string
  body: Record<string, unknown> | null
  /** Когда экран отправил запрос (performance.now()). */
  sentAt: number
  /** Когда подставной сервер отдал ответ; null — ответ ещё не отдан. */
  answeredAt: number | null
}
type MarkingLink = {
  marking_code_id: string
  cis_code: string
  product_id: string
  storage_location_id: string | null
  container_id: string | null
  box_id: string | null
  intake_document_number: string | null
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/**
 * Подставной сервер отгрузки: состояние подбора и связи КИЗ живут здесь, а не в экране.
 * productScanDelayMs — задержка ответа на снятие по ШК товара (сеть медленнее сканера);
 * initialPicks — сколько уже снято из источника до открытия экрана.
 */
function createPickServer({
  productScanDelayMs = 0,
  initialPicks = {},
}: { productScanDelayMs?: number; initialPicks?: Record<string, number> } = {}) {
  const requests: Recorded[] = []
  const unknown: string[] = []
  const picks = new Map<string, number>([BOX_K1.id, BOX_K2.id, 'loose'].map((key) => [key, initialPicks[key] ?? 0]))
  const links: MarkingLink[] = []
  const replies = new Map<string, unknown>()
  let pickSetFailure: { status: number; detail: string } | null = null

  const totalPicked = () => [...picks.values()].reduce((sum, qty) => sum + qty, 0)
  const boxOf = (sourceKey: string) => [BOX_K1, BOX_K2].find((box) => box.id === sourceKey) ?? null

  const detail = () => ({
    id: REQUEST_ID,
    marketplace: 'wb',
    name: null,
    document_number: '000686',
    display_number: '000686',
    warehouse_name: 'Склад ФФ',
    status: 'collecting',
    seller_id: SELLER_ID,
    seller_name: 'ИП Тестовый',
    planned_shipment_date: '2026-10-09',
    lines: [{
      id: 'line-a',
      product_id: PRODUCT.id,
      sku_code: PRODUCT.sku,
      product_name: PRODUCT.name,
      quantity: PRODUCT.plan,
      picked_qty: totalPicked(),
    }],
  })

  const pickSource = (sourceKey: string) => {
    const box = boxOf(sourceKey)
    const picked = picks.get(sourceKey) ?? 0
    const left = CONTENT[sourceKey] - picked
    return {
      quantity: left,
      available: left,
      is_loose: box === null,
      source_label: box ? `Короб ${box.code}` : 'Россыпью',
      picked,
      container_path: box ? [{ kind: 'box', id: box.id, code: box.code, label: `Короб ${box.code}` }] : [],
    }
  }

  const pickOptions = () => {
    const sources = [BOX_K1.id, BOX_K2.id, 'loose'].map(pickSource)
    const left = sources.reduce((sum, source) => sum + source.quantity, 0)
    return [{
      product_id: PRODUCT.id,
      sku_code: PRODUCT.sku,
      product_name: PRODUCT.name,
      seller_article: null,
      barcode: null,
      planned_qty: PRODUCT.plan,
      picked_qty: totalPicked(),
      locations: [{
        storage_location_id: CELL.id,
        location_code: CELL.code,
        quantity: left,
        reserved: 0,
        available: left,
        picked: totalPicked(),
        sources,
      }],
    }]
  }

  const catalog = [{
    id: PRODUCT.id,
    name: PRODUCT.name,
    sku_code: PRODUCT.sku,
    seller_name: 'ИП Тестовый',
    wb_nm_id: 100686001,
    wb_vendor_code: 'ART-686-A',
    wb_subject_name: 'Футболки',
    wb_primary_image_url: null,
    wb_barcodes: [PRODUCT.barcode],
    wb_primary_barcode: PRODUCT.barcode,
    wb_size: '48',
    wb_color: null,
    marketplaces: ['wb'],
    marketplace_bindings: [],
  }]

  const sourceReply = (sourceKey: string) => {
    const box = boxOf(sourceKey)
    return {
      storage_location_id: CELL.id,
      location_code: CELL.code,
      container_kind: box ? 'box' : null,
      container_id: box ? box.id : null,
      container_code: box ? box.code : null,
    }
  }

  const productByGtin = (code: string) => {
    const gtin = code.replace(/[()]/g, '').slice(2, 16)
    return gtin.replace(/^0+/, '') === PRODUCT.barcode.replace(/^0+/, '') ? PRODUCT.id : null
  }

  function pickScan(body: Record<string, unknown>): Response {
    const barcode = String(body.barcode ?? '')
    const mutationId = typeof body.mutation_id === 'string' ? body.mutation_id : null
    // R10: повтор того же ключа операции возвращает исходный ответ без второго снятия.
    if (mutationId && replies.has(mutationId)) return json(replies.get(mutationId))
    const remember = (reply: unknown) => {
      if (mutationId) replies.set(mutationId, reply)
      return json(reply)
    }
    if (barcode === CELL.code) {
      return json({
        kind: 'location', storage_location_id: CELL.id, location_code: CELL.code, product_id: null,
        sku_code: null, product_name: null, picked_qty: null, allocation_quantity: null,
        container_kind: null, container_id: null, container_code: null,
      })
    }
    const box = [BOX_K1, BOX_K2].find((one) => one.code === barcode)
    if (box) {
      return json({
        kind: 'container', ...sourceReply(box.id), product_id: null, sku_code: null,
        product_name: null, picked_qty: null, allocation_quantity: null,
      })
    }
    const sourceKey = typeof body.container_id === 'string' ? body.container_id : 'loose'
    if (!picks.has(sourceKey)) return json({ detail: 'pick_source_not_found' }, 422)
    if (isKiz(barcode)) {
      // Раздел 9 п.1, D16: КИЗ не меняет количеств. product_id в теле — товар последнего
      // ШК (контекст единицы); без product_id — контекст проверки источника по GTIN.
      const byGtin = productByGtin(barcode)
      const unitContext = typeof body.product_id === 'string' ? body.product_id : null
      if (unitContext && byGtin && byGtin !== unitContext) return json({ detail: 'marking_code_other_product' }, 422)
      const productId = unitContext ?? byGtin
      if (!productId) return json({ detail: 'marking_product_unknown' }, 422)
      const existing = links.find((link) => link.cis_code === barcode)
      if (existing) {
        return remember({
          kind: 'marking', ...sourceReply(sourceKey), product_id: existing.product_id, sku_code: null,
          product_name: null, marking_code_id: existing.marking_code_id, cis_code: barcode,
          already_linked: true, picked_qty: totalPicked(), allocation_quantity: picks.get(sourceKey),
        })
      }
      const pickedHere = picks.get(sourceKey) ?? 0
      if (pickedHere === 0) return json({ detail: 'marking_unit_not_in_source' }, 422)
      const linkedHere = links.filter((link) => (link.container_id ?? 'loose') === sourceKey).length
      if (linkedHere >= pickedHere) return json({ detail: 'marking_quantity_exceeded' }, 422)
      const link: MarkingLink = {
        marking_code_id: `mc-${links.length + 1}`,
        cis_code: barcode,
        product_id: productId,
        storage_location_id: CELL.id,
        container_id: boxOf(sourceKey)?.id ?? null,
        box_id: null,
        intake_document_number: null,
      }
      links.push(link)
      return remember({
        kind: 'marking', ...sourceReply(sourceKey), product_id: productId, sku_code: null,
        product_name: null, marking_code_id: link.marking_code_id, cis_code: barcode,
        already_linked: false, picked_qty: totalPicked(), allocation_quantity: picks.get(sourceKey),
      })
    }
    if (barcode !== PRODUCT.barcode && barcode !== PRODUCT.sku) return json({ detail: 'barcode_unknown' }, 422)
    const before = picks.get(sourceKey) ?? 0
    if (before >= CONTENT[sourceKey]) return json({ detail: 'insufficient_available' }, 422)
    picks.set(sourceKey, before + 1)
    return remember({
      kind: 'product', ...sourceReply(sourceKey), product_id: PRODUCT.id, sku_code: PRODUCT.sku,
      product_name: PRODUCT.name, picked_qty: totalPicked(), allocation_quantity: before + 1,
    })
  }

  function pickSet(body: Record<string, unknown>): Response {
    if (pickSetFailure) {
      const failure = pickSetFailure
      pickSetFailure = null
      return json({ detail: failure.detail }, failure.status)
    }
    const sourceKey = typeof body.container_id === 'string' ? body.container_id : 'loose'
    const quantity = Number(body.quantity)
    if (!picks.has(sourceKey) || !Number.isInteger(quantity) || quantity < 0 || quantity > CONTENT[sourceKey]) {
      return json({ detail: 'insufficient_available' }, 422)
    }
    picks.set(sourceKey, quantity)
    return json({
      id: `alloc-${sourceKey}`, product_id: PRODUCT.id, sku_code: PRODUCT.sku, product_name: PRODUCT.name,
      storage_location_id: CELL.id, location_code: CELL.code, quantity,
    })
  }

  function attach(body: Record<string, unknown>): Response {
    const box = [BOX_K1, BOX_K2].find((one) => one.code === body.barcode)
    if (!box) return json({ detail: 'box_not_found' }, 422)
    const left = CONTENT[box.id] - (picks.get(box.id) ?? 0)
    if (left <= 0) return json({ detail: 'box_empty' }, 422)
    // Целый короб уходит в отгрузку: всё его содержимое считается снятым (R7, C12).
    picks.set(box.id, CONTENT[box.id])
    return json({
      id: `unload-${box.id}`,
      box_preset: typeof body.box_preset === 'string' ? body.box_preset : '60_40_40',
      internal_barcode: box.code,
      closed_at: '2026-10-08T09:00:00Z',
      lines: [{ id: `unload-line-${box.id}`, product_id: PRODUCT.id, sku_code: PRODUCT.sku, product_name: PRODUCT.name, quantity: left }],
    }, 201)
  }

  const handle = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(raw, 'http://wms.test')
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    const path = url.pathname.replace(/^\/api/, '')
    let body: Record<string, unknown> | null = null
    if (typeof init?.body === 'string' && init.body) {
      try {
        body = JSON.parse(init.body) as Record<string, unknown>
      } catch {
        body = { __raw: init.body }
      }
    }
    const record: Recorded = { method, path, body, sentAt: performance.now(), answeredAt: null }
    requests.push(record)
    if (productScanDelayMs > 0 && method === 'POST' && path === `${BASE}/pick/scan` && body?.barcode === PRODUCT.barcode) {
      await new Promise((resolve) => setTimeout(resolve, productScanDelayMs))
    }
    const response = route(url, method, path, body)
    record.answeredAt = performance.now()
    return response
  }

  function route(url: URL, method: string, path: string, body: Record<string, unknown> | null): Response {
    if (url.origin === 'http://wms.test') {
      if (method === 'GET' && path === BASE) return json(detail())
      if (method === 'GET' && path === `${BASE}/pick-options`) return json(pickOptions())
      if (method === 'GET' && path === '/products/linked-wb-catalog') return json(catalog)
      if (method === 'GET' && path === `${BASE}/marking-codes`) return json(links)
      const removal = /^\/operations\/marketplace-unload-requests\/mp-686\/marking-codes\/([^/]+)$/.exec(path)
      if (method === 'DELETE' && removal) {
        const index = links.findIndex((link) => link.marking_code_id === removal[1])
        if (index >= 0) links.splice(index, 1)
        return json({ removed: index >= 0 })
      }
      if (method === 'POST' && path === `${BASE}/pick/scan`) return pickScan(body ?? {})
      if (method === 'POST' && path === `${BASE}/pick/set`) return pickSet(body ?? {})
      if (method === 'POST' && path === `${BASE}/boxes/attach`) return attach(body ?? {})
    }
    unknown.push(`${method} ${url.origin === 'http://wms.test' ? path : url.href}`)
    return json({ detail: `Неизвестный маршрут подставного сервера: ${method} ${path}` }, 404)
  }

  return {
    fetch: handle as typeof fetch,
    requests,
    unknown,
    picks,
    links,
    failNextPickSet(status: number, detail: string) {
      pickSetFailure = { status, detail }
    },
    /** Запросы pick/scan в порядке прихода. */
    pickScans: () => requests.filter((one) => one.method === 'POST' && one.path === `${BASE}/pick/scan`),
    /** Только снятия товара по его ШК — без сканов места, тары и КИЗ. */
    productScans: () => requests.filter((one) =>
      one.method === 'POST' && one.path === `${BASE}/pick/scan` && one.body?.barcode === PRODUCT.barcode),
    pickSets: () => requests.filter((one) => one.method === 'POST' && one.path === `${BASE}/pick/set`),
    attaches: () => requests.filter((one) => one.method === 'POST' && one.path === `${BASE}/boxes/attach`),
    /** Удаления связей КИЗ: DELETE …/marking-codes/{id}. */
    markingDeletes: () => requests.filter((one) => one.method === 'DELETE' && one.path.startsWith(`${BASE}/marking-codes/`)),
  }
}

type PickServer = ReturnType<typeof createPickServer>

const originalFetch = globalThis.fetch
const originalScrollIntoView = Element.prototype.scrollIntoView
let host: HTMLDivElement
let root: Root

beforeEach(() => {
  try {
    window.localStorage.clear()
    window.sessionStorage.clear()
  } catch {
    // Хранилище браузера — не часть контракта; его отсутствие тест не ломает.
  }
  // jsdom не прокручивает; новая строка КИЗ может попросить прокрутку к себе.
  Element.prototype.scrollIntoView = () => undefined
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  document.body.innerHTML = ''
  globalThis.fetch = originalFetch
  Element.prototype.scrollIntoView = originalScrollIntoView
})

async function settle(ms = 20) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms))
  })
}

/** Ждёт состояние, которое экран показывает после асинхронного действия; иначе — последняя ошибка проверки. */
async function waitFor(assertion: () => void, timeoutMs = 1500) {
  const started = Date.now()
  for (;;) {
    try {
      assertion()
      return
    } catch (error) {
      if (Date.now() - started > timeoutMs) throw error
    }
    await settle(10)
  }
}

function keyCode(key: string) {
  if (/^\d$/.test(key)) return `Digit${key}`
  if (/^[a-z]$/i.test(key)) return `Key${key.toUpperCase()}`
  return key
}

/** «Клавиатурный» сканер: символы подряд и Enter — туда, где сейчас фокус. */
function scan(code: string) {
  const target = document.activeElement ?? document.body
  act(() => {
    for (const key of code) {
      target.dispatchEvent(new KeyboardEvent('keydown', {
        key, code: keyCode(key), shiftKey: /^[A-Z]$/.test(key), bubbles: true, cancelable: true,
      }))
    }
    target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
}

type PickPage = typeof FfUnloadPickPage

async function renderPage(server: PickServer, Page: PickPage = FfUnloadPickPage) {
  globalThis.fetch = server.fetch
  await act(async () => {
    root.render(
      <MemoryRouter>
        <Page token="contract-token" requestId={REQUEST_ID} hideHeader />
      </MemoryRouter>,
    )
  })
  await waitFor(() => expect(document.querySelector('[data-testid="pick-table"]'), 'экран подбора открылся').not.toBeNull())
  await waitFor(() => expect(server.requests.some((one) => one.path === '/products/linked-wb-catalog')).toBe(true))
  await settle(30)
  blurToBody()
}

function blurToBody() {
  act(() => (document.activeElement as HTMLElement | null)?.blur())
}

const byTestId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`)
/** Строка «Снимаем с:»; пустая строка — источник не показан. */
const sourceText = () => byTestId('pick-source')?.textContent ?? ''
const leftQty = () => byTestId('pick-left-qty')?.textContent ?? null
const placeQty = (sourceKey: string) =>
  document.querySelector<HTMLInputElement>(`input[data-testid="pick-place-qty-${PRODUCT.id}-${sourceKey}"]`)

async function selectBox(box: { code: string }) {
  scan(box.code)
  await waitFor(() => expect(sourceText(), `«Снимаем с:» показывает ${box.code}`).toContain(box.code))
}

const screenText = () => (byTestId('unload-pick-screen')?.textContent ?? '').replace(/\s+/g, ' ')

function expectNoUnknownRoutes(server: PickServer) {
  expect(server.unknown, 'обращения к маршрутам вне контракта получили 404 подставного сервера').toEqual([])
}

describe('WMS-686 · «Подбор» FBO: короб, ШК и необязательный КИЗ', () => {
  it('c01 C1/R1: скан короба K1 держит источник для серии ШК; скан короба K2 меняет его', async () => {
    const server = createPickServer()
    await renderPage(server)
    expect(leftQty()).toBe('5')

    await selectBox(BOX_K1)
    scan(PRODUCT.barcode)
    await waitFor(() => expect(server.productScans()).toHaveLength(1))
    await waitFor(() => expect(leftQty()).toBe('4'))
    expect(sourceText(), '«Снимаем с: K1» на месте после первого ШК').toContain(BOX_K1.code)

    scan(PRODUCT.barcode)
    await waitFor(() => expect(server.productScans()).toHaveLength(2))
    await waitFor(() => expect(leftQty()).toBe('3'))
    expect(sourceText(), '«Снимаем с: K1» на месте после второго ШК').toContain(BOX_K1.code)

    const [first, second] = server.productScans()
    expect(first.body?.container_id, 'первое снятие — из короба K1').toBe(BOX_K1.id)
    expect(second.body?.container_id, 'второе снятие — из того же короба K1').toBe(BOX_K1.id)
    expect(placeQty(`obj:${BOX_K1.id}`)?.value, 'в строке K1 снято 2').toBe('2')
    expect(placeQty(`cell:${CELL.id}`)?.value, 'россыпь ячейки не тронута').toBe('0')
    expect(server.picks.get('loose')).toBe(0)

    await selectBox(BOX_K2)
    scan(PRODUCT.barcode)
    await waitFor(() => expect(server.productScans()).toHaveLength(3))
    expect(server.productScans()[2].body?.container_id, 'после скана K2 следующий ШК снимается из K2').toBe(BOX_K2.id)
    await waitFor(() => expect(placeQty(`obj:${BOX_K2.id}`)?.value).toBe('1'))
    expect(sourceText()).toContain(BOX_K2.code)
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c02 C2/R1: после ответа 500 на ручную правку «Снять» короб K1 остаётся источником, ШК уходит с K1, после перезагрузки — снова K1', async () => {
    const server = createPickServer()
    await renderPage(server)
    await selectBox(BOX_K1)

    // Ручная правка «Снять» в строке K1 — сервер отвечает 500.
    server.failNextPickSet(500, 'Сервер временно недоступен (WMS-686 C2)')
    const input = placeQty(`obj:${BOX_K1.id}`)
    expect(input, 'поле «Снять» в строке короба K1').not.toBeNull()
    act(() => input!.focus())
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
    await act(async () => {
      setter.call(input, '1')
      input!.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await waitFor(() => expect(server.pickSets()).toHaveLength(1), 3000)
    expect(server.pickSets()[0].body?.container_id).toBe(BOX_K1.id)
    await waitFor(() =>
      expect(byTestId('unload-pick-error')?.textContent, 'ошибка сервера показана').toContain('Сервер временно недоступен'))
    await settle(50)

    expect(sourceText(), 'после ошибки pick/set строка «Снимаем с:» всё ещё K1').toContain(BOX_K1.code)

    blurToBody()
    scan(PRODUCT.barcode)
    await waitFor(() => expect(server.productScans(), 'следующий ШК ушёл на сервер').toHaveLength(1))
    expect(server.productScans()[0].body?.container_id, 'следующий ШК снимается из того же короба K1').toBe(BOX_K1.id)
    await waitFor(() => expect(sourceText()).toContain(BOX_K1.code))

    // Восстановление: перезагрузка страницы документа (модули экрана читаются заново).
    act(() => root.unmount())
    root = createRoot(host)
    vi.resetModules()
    const reloaded = await import('./FfUnloadPickPage')
    await renderPage(server, reloaded.FfUnloadPickPage)
    await waitFor(() =>
      expect(sourceText(), 'после перезагрузки документа строка источника снова K1').toContain(BOX_K1.code))
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c05 C5/R3/R11: короб → ШК → КИЗ подряд: третий pick/scan несёт КИЗ, товар и короб; строка КИЗ новая; «осталось» не меняется от КИЗ', async () => {
    const server = createPickServer()
    await renderPage(server)
    expect(leftQty()).toBe('5')

    // Подряд, не дожидаясь ответов: очередь сканов обрабатывает их по порядку.
    scan(BOX_K1.code)
    scan(PRODUCT.barcode)
    scan(KIZ_1)
    await waitFor(() => expect(server.pickScans(), 'три запроса pick/scan: короб, ШК, КИЗ').toHaveLength(3))

    const [boxScan, productScan, kizScan] = server.pickScans()
    expect(boxScan.body?.barcode).toBe(BOX_K1.code)
    expect(productScan.body?.barcode).toBe(PRODUCT.barcode)
    expect(kizScan.body?.barcode, 'третий запрос — КИЗ').toBe(KIZ_1)
    expect(kizScan.body?.product_id, 'КИЗ уходит с product_id отсканированного товара').toBe(PRODUCT.id)
    expect(kizScan.body?.container_id, 'КИЗ уходит с коробом-источником').toBe(BOX_K1.id)

    await waitFor(() => {
      const table = byTestId('pick-table')
      expect(
        table?.querySelector('[data-testid="pick-kiz-row"][data-kiz-state="new"]') ?? null,
        'под источником появилась новая строка КИЗ',
      ).not.toBeNull()
    })
    expect(server.links).toHaveLength(1)
    await settle(50)
    expect(leftQty(), '«осталось» уменьшилось только от ШК, КИЗ не посчитан единицей').toBe('4')
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c12 C12/R7: после скана короба кнопка «Забрать целиком» отправляет присоединение этого короба', async () => {
    const server = createPickServer()
    await renderPage(server)
    await selectBox(BOX_K1)

    const takeWhole = byTestId('pick-source-take-whole')
    expect(takeWhole, 'в строке «Снимаем с:» есть «Забрать целиком»').not.toBeNull()
    await act(async () => takeWhole!.click())

    await waitFor(() => expect(server.attaches(), 'отправлен POST …/boxes/attach').toHaveLength(1))
    expect(server.attaches()[0].body?.barcode, 'присоединяется именно отсканированный короб').toBe(BOX_K1.code)
    expect(server.productScans(), 'единицы не пересканируются').toHaveLength(0)
    await waitFor(() => expect(leftQty(), 'после ответа подобрано на весь состав короба (3 шт.)').toBe('2'))
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c17 C17/R10: каждый скан ШК в pick/scan несёт свой mutation_id, у двух сканов ключи разные', async () => {
    const server = createPickServer()
    await renderPage(server)
    await selectBox(BOX_K1)

    scan(PRODUCT.barcode)
    await waitFor(() => expect(server.productScans()).toHaveLength(1))
    scan(PRODUCT.barcode)
    await waitFor(() => expect(server.productScans()).toHaveLength(2))

    const keys = server.productScans().map((one) => one.body?.mutation_id)
    for (const key of keys) {
      expect(typeof key, 'запрос pick/scan несёт mutation_id').toBe('string')
      expect(key as string, 'mutation_id — UUID (раздел 9 п.1)').toMatch(UUID_RE)
    }
    expect(new Set(keys).size, 'у двух физических сканов разные ключи').toBe(2)
    await waitFor(() => expect(leftQty()).toBe('3'))
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c52 C52/R11/R33г: ответ на ШК задержан 300 мс — КИЗ, считанный раньше ответа, уходит после него и с product_id этого товара', async () => {
    const server = createPickServer({ productScanDelayMs: 300 })
    await renderPage(server)

    // Короб, ШК и КИЗ подряд, пока ответ на ШК ещё в пути.
    scan(BOX_K1.code)
    scan(PRODUCT.barcode)
    scan(KIZ_1)
    await waitFor(() => expect(server.pickScans(), 'три запроса pick/scan: короб, ШК, КИЗ').toHaveLength(3), 3000)

    const [, productScan, kizScan] = server.pickScans()
    expect(productScan.body?.barcode).toBe(PRODUCT.barcode)
    expect(kizScan.body?.barcode).toBe(KIZ_1)
    await waitFor(() => expect(productScan.answeredAt, 'ответ на ШК отдан').not.toBeNull())
    expect(productScan.answeredAt! - productScan.sentAt, 'ответ на ШК действительно задержан').toBeGreaterThanOrEqual(290)
    expect(kizScan.sentAt, 'запрос КИЗ отправлен только после ответа на ШК').toBeGreaterThanOrEqual(productScan.answeredAt!)
    expect(kizScan.body?.product_id, 'КИЗ уходит с product_id товара, отсканированного перед ним').toBe(PRODUCT.id)
    await waitFor(() => expect(server.links).toHaveLength(1))
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c53 C53/R9г: ШК → КИЗ → «Отменить последнее снятие» удаляет связь КИЗ, «осталось» прежнее', async () => {
    const server = createPickServer()
    await renderPage(server)
    await selectBox(BOX_K1)

    scan(PRODUCT.barcode)
    await waitFor(() => expect(server.productScans()).toHaveLength(1))
    await waitFor(() => expect(leftQty()).toBe('4'))
    scan(KIZ_1)
    await waitFor(() => expect(server.pickScans(), 'КИЗ отправлен').toHaveLength(3))
    await waitFor(() => expect(server.links, 'сервер связал КИЗ с единицей').toHaveLength(1))
    const markingCodeId = server.links[0].marking_code_id
    await settle(50)
    expect(leftQty()).toBe('4')

    const undo = byTestId(`pick-undo-${PRODUCT.id}`)
    expect(undo, 'кнопка «Отменить последнее снятие» у товара').not.toBeNull()
    await act(async () => undo!.click())

    await waitFor(() =>
      expect(server.markingDeletes(), 'отмена последнего скана (КИЗ) отправляет DELETE …/marking-codes/{код}').toHaveLength(1))
    expect(server.markingDeletes()[0].path).toBe(`${BASE}/marking-codes/${markingCodeId}`)
    await settle(600)
    expect(leftQty(), '«осталось» не изменилось: отменён КИЗ, а не снятие единицы').toBe('4')
    expect(server.pickSets(), 'единица не возвращается в короб').toHaveLength(0)
    expect(server.picks.get(BOX_K1.id)).toBe(1)
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c54 C54/R6б/D16 (подбор): короб → КИЗ без ШК — pick/scan с КИЗ и коробом без product_id, привязка к уже снятой единице без +1; неизвестный GTIN — «Сначала отсканируйте ШК товара»', async () => {
    // Из K1 уже снята одна A без КИЗ.
    const server = createPickServer({ initialPicks: { [BOX_K1.id]: 1 } })
    await renderPage(server)
    expect(leftQty()).toBe('4')

    await selectBox(BOX_K1)
    scan(KIZ_1)
    await waitFor(() => expect(server.pickScans(), 'два запроса pick/scan: короб и КИЗ').toHaveLength(2))
    const kizScan = server.pickScans()[1]
    expect(kizScan.body?.barcode, 'второй запрос — КИЗ').toBe(KIZ_1)
    expect(kizScan.body?.product_id ?? null, 'после скана короба КИЗ уходит без product_id (контекст проверки)').toBeNull()
    expect(kizScan.body?.container_id, 'КИЗ проверяется в отсканированном коробе').toBe(BOX_K1.id)
    expect(server.productScans(), 'КИЗ без ШК не снимает единицу').toHaveLength(0)

    await waitFor(() => {
      const table = byTestId('pick-table')
      expect(
        table?.querySelector('[data-testid="pick-kiz-row"][data-kiz-state="new"]') ?? null,
        'код привязан к уже снятой единице — строка КИЗ под источником',
      ).not.toBeNull()
    })
    expect(server.links.map((link) => link.container_id)).toEqual([BOX_K1.id])
    expect(leftQty(), '«осталось» прежнее').toBe('4')

    scan(KIZ_UNKNOWN_GTIN)
    await waitFor(() =>
      expect(screenText(), 'код с неизвестным GTIN в контексте проверки').toContain('Сначала отсканируйте ШК товара'))
    expect(server.links, 'неизвестный код не привязан').toHaveLength(1)
    expect(leftQty()).toBe('4')
    expectNoUnknownRoutes(server)
  }, 20_000)
})
