// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfUnloadPickPage } from './FfUnloadPickPage'

// ── Подставной сервер подбора отгрузки FBO ─────────────────────────────────────────────
// Отвечает по формам ответов настоящего API: документ, pick-options, pick/scan, pick/set,
// boxes/attach и ручки КИЗ marking-codes. Состояние живёт здесь, а не на экране, поэтому
// тест видит то, что увидел бы сервер.

const FAKE_REQUEST_ID = 'doc-686'
const FAKE_BASE = `/operations/marketplace-unload-requests/${FAKE_REQUEST_ID}`

type FakeProduct = { id: string; sku: string; name: string; barcode: string; gtin: string; plan: number }
type FakeSource = {
  id: string
  /** null — россыпь на ячейке. */
  box: { id: string; code: string } | null
  cell: { id: string; code: string }
  content: Record<string, number>
}
type FakeKiz = { id: string; cis: string; productId: string; intake: string | null }

const FAKE_PRODUCTS: FakeProduct[] = [
  { id: 'p-a', sku: 'SKU-A', name: 'Футболка хлопковая 48', barcode: '4600000000011', gtin: '04600000000011', plan: 6 },
  { id: 'p-b', sku: 'SKU-B', name: 'Худи оверсайз серое, L', barcode: '4600000000028', gtin: '04600000000028', plan: 3 },
]
const CELL_A = { id: 'loc-a', code: 'А-1-1' }
const CELL_B = { id: 'loc-b', code: 'Б-2-1' }

const FAKE_SOURCES: FakeSource[] = [
  { id: 'box-1', box: { id: 'box-1', code: 'INB-000101' }, cell: CELL_A, content: { 'p-a': 3 } },
  { id: 'box-2', box: { id: 'box-2', code: 'INB-000102' }, cell: CELL_A, content: { 'p-a': 4 } },
  { id: 'loose-a', box: null, cell: CELL_A, content: { 'p-a': 2 } },
  { id: 'box-3', box: { id: 'box-3', code: 'INB-000103' }, cell: CELL_B, content: { 'p-b': 2, 'p-a': 1 } },
]

const KIZ_RE = /^01(\d{14})21/

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

type FakeRequest = { method: string; path: string; body: Record<string, unknown> | null }

function createFboPickFakeServer({ delayMs = 0 }: { delayMs?: number } = {}) {
  const requests: FakeRequest[] = []
  const unexpected: string[] = []
  /** taken[sourceId][productId] — сколько штук уже снято из источника. */
  const taken: Record<string, Record<string, number>> = {}
  const kiz: FakeKiz[] = []
  let kizSeq = 0
  /** Отказ следующего pick/set: имитация ошибки сохранения. */
  let failNextPickSet = false
  /** КИЗ, которые сервер «отвязал» при следующей правке подбора (R19). */
  let nextUnlinked: string[] = []
  const attached = new Set<string>()

  const takenOf = (sourceId: string, productId: string) => taken[sourceId]?.[productId] ?? 0
  const totalTaken = (productId: string) => FAKE_SOURCES.reduce((sum, source) => sum + takenOf(source.id, productId), 0)
  const productById = (id: string) => FAKE_PRODUCTS.find((one) => one.id === id)
  const setTaken = (sourceId: string, productId: string, qty: number) => {
    taken[sourceId] = { ...(taken[sourceId] ?? {}), [productId]: qty }
  }

  const pickOptions = () =>
    FAKE_PRODUCTS.map((product) => {
      const locations = [CELL_A, CELL_B].flatMap((cell) => {
        const sources = FAKE_SOURCES.filter((source) => source.cell.id === cell.id && (source.content[product.id] ?? 0) > 0)
        if (sources.length === 0) return []
        return [{
          storage_location_id: cell.id,
          location_code: cell.code,
          quantity: sources.reduce((sum, source) => sum + (source.content[product.id] ?? 0), 0),
          reserved: 0,
          available: sources.reduce((sum, source) => sum + (source.content[product.id] ?? 0) - takenOf(source.id, product.id), 0),
          picked: sources.reduce((sum, source) => sum + takenOf(source.id, product.id), 0),
          sources: sources.map((source) => ({
            quantity: source.content[product.id] ?? 0,
            available: (source.content[product.id] ?? 0) - takenOf(source.id, product.id),
            is_loose: source.box === null,
            source_label: source.box ? `Короб ${source.box.code}` : 'Россыпью',
            picked: takenOf(source.id, product.id),
            container_path: source.box
              ? [{ kind: 'box', id: source.box.id, code: source.box.code, label: `Короб ${source.box.code}` }]
              : [],
          })),
        }]
      })
      return {
        product_id: product.id,
        sku_code: product.sku,
        product_name: product.name,
        seller_article: null,
        barcode: product.barcode,
        planned_qty: product.plan,
        picked_qty: totalTaken(product.id),
        locations,
      }
    })

  const detail = () => ({
    id: FAKE_REQUEST_ID,
    marketplace: 'wb',
    name: null,
    document_number: '000686',
    display_number: '000686',
    warehouse_name: 'Склад ФФ',
    status: 'collecting',
    seller_id: 'seller-1',
    seller_name: 'ИП Тестовый',
    planned_shipment_date: '2026-10-09',
    lines: FAKE_PRODUCTS.map((product) => ({
      id: `line-${product.id}`,
      product_id: product.id,
      sku_code: product.sku,
      product_name: product.name,
      quantity: product.plan,
      picked_qty: totalTaken(product.id),
      requires_honest_sign: product.id === 'p-a',
    })),
  })

  const kizItems = () =>
    kiz.map((one) => ({
      marking_code_id: one.id,
      cis_code: one.cis,
      product_id: one.productId,
      line_id: `line-${one.productId}`,
      status: 'applied',
      intake_document_number: one.intake,
      linked_at: '2026-10-09T01:00:00Z',
      has_label_artifact: false,
    }))

  function pickScan(body: Record<string, unknown>): Response {
    const barcode = String(body.barcode ?? '')
    const cell = [CELL_A, CELL_B].find((one) => one.code === barcode)
    if (cell) {
      return json({
        kind: 'location', storage_location_id: cell.id, location_code: cell.code,
        product_id: null, sku_code: null, product_name: null, picked_qty: null, allocation_quantity: null,
        container_kind: null, container_id: null, container_code: null,
      })
    }
    const box = FAKE_SOURCES.find((one) => one.box?.code === barcode)
    if (box?.box) {
      return json({
        kind: 'container', storage_location_id: box.cell.id, location_code: box.cell.code,
        product_id: null, sku_code: null, product_name: null, picked_qty: null, allocation_quantity: null,
        container_kind: 'box', container_id: box.box.id, container_code: box.box.code,
      })
    }
    const product = FAKE_PRODUCTS.find((one) => one.barcode === barcode || one.sku === barcode)
    if (!product) return json({ detail: 'barcode_unknown' }, 422)
    const containerId = typeof body.container_id === 'string' ? body.container_id : null
    const source = FAKE_SOURCES.find((one) =>
      containerId ? one.box?.id === containerId : one.box === null && one.cell.id === body.storage_location_id,
    )
    if (!source || (source.content[product.id] ?? 0) - takenOf(source.id, product.id) <= 0) {
      return json({ detail: 'В выбранном месте нет товара' }, 422)
    }
    if (totalTaken(product.id) >= product.plan) {
      return json({ detail: { code: 'plan_limit_exceeded', message: 'Нельзя подобрать больше, чем в плане отгрузки.' } }, 422)
    }
    setTaken(source.id, product.id, takenOf(source.id, product.id) + 1)
    return json({
      kind: 'product', storage_location_id: source.cell.id, location_code: null,
      product_id: product.id, sku_code: product.sku, product_name: product.name,
      picked_qty: totalTaken(product.id), allocation_quantity: takenOf(source.id, product.id),
      container_kind: null, container_id: null, container_code: null,
    })
  }

  function kizScan(body: Record<string, unknown>): Response {
    const code = String(body.code ?? '')
    const match = KIZ_RE.exec(code)
    if (!match) return json({ detail: 'marking_code_invalid' }, 422)
    const byGtin = FAKE_PRODUCTS.find((one) => one.gtin === match[1])
    const hint = typeof body.product_id === 'string' ? productById(body.product_id) : undefined
    const product = hint ?? byGtin
    if (!product) return json({ detail: 'marking_product_unknown' }, 422)
    if (byGtin && byGtin.id !== product.id) return json({ detail: 'marking_code_other_product' }, 422)
    const existing = kiz.find((one) => one.cis === code)
    const count = () => kiz.filter((one) => one.productId === product.id).length
    if (existing) {
      if (existing.productId !== product.id) return json({ detail: 'marking_code_other_product' }, 422)
      return json({
        marking_code_id: existing.id, cis_code: code, product_id: product.id, line_id: `line-${product.id}`,
        already_linked: true, kiz_count: count(), picked_qty: totalTaken(product.id),
      })
    }
    if (count() >= totalTaken(product.id)) return json({ detail: 'marking_quantity_exceeded' }, 422)
    kizSeq += 1
    kiz.push({ id: `kiz-${kizSeq}`, cis: code, productId: product.id, intake: null })
    return json({
      marking_code_id: `kiz-${kizSeq}`, cis_code: code, product_id: product.id, line_id: `line-${product.id}`,
      already_linked: false, kiz_count: count(), picked_qty: totalTaken(product.id),
    })
  }

  function attach(body: Record<string, unknown>): Response {
    const source = FAKE_SOURCES.find((one) => one.box?.code === body.barcode)
    if (!source) return json({ detail: 'box_barcode_unknown' }, 422)
    if (attached.has(source.id)) return json({ detail: 'box_already_attached' }, 409)
    const items: Array<{ product_id: string; in_box: number; left: number }> = []
    for (const [productId, qty] of Object.entries(source.content)) {
      const product = productById(productId)
      const left = (product?.plan ?? 0) - totalTaken(productId)
      if (qty > left) items.push({ product_id: productId, in_box: qty, left })
    }
    if (items.length > 0) {
      const first = items[0]
      const name = productById(first.product_id)?.name ?? first.product_id
      return json({
        detail: {
          code: 'plan_limit_exceeded',
          message: `Количество товаров в коробе больше, чем осталось подобрать: ${name} — в коробе ${first.in_box}, осталось ${first.left}. Откройте короб и подберите поштучно`,
          items,
        },
      }, 422)
    }
    for (const [productId, qty] of Object.entries(source.content)) setTaken(source.id, productId, qty)
    attached.add(source.id)
    return json({ id: 'mp-box-1', box_preset: '60_40_40', lines: [] }, 201)
  }

  async function handle(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
    const path = url.pathname.replace(/^\/api/, '')
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null
    requests.push({ method, path, body })
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs))
    if (path === '/products/linked-wb-catalog') return json([])
    if (path === FAKE_BASE && method === 'GET') return json(detail())
    if (path === `${FAKE_BASE}/pick-options`) return json(pickOptions())
    if (path === `${FAKE_BASE}/pick/scan` && body) return pickScan(body)
    if (path === `${FAKE_BASE}/pick/set` && body) {
      if (failNextPickSet) {
        failNextPickSet = false
        return json({ detail: 'Не удалось сохранить снятое количество' }, 422)
      }
      const source = FAKE_SOURCES.find((one) =>
        body.container_id ? one.box?.id === body.container_id : one.box === null && one.cell.id === body.storage_location_id,
      )
      if (source) setTaken(source.id, String(body.product_id), Number(body.quantity))
      const unlinked = nextUnlinked
      nextUnlinked = []
      return json({ ok: true, unlinked_marking_codes: unlinked })
    }
    if (path === `${FAKE_BASE}/marking-codes` && method === 'GET') return json({ items: kizItems() })
    if (path === `${FAKE_BASE}/marking-codes/scan` && body) return kizScan(body)
    const removal = new RegExp(`^${FAKE_BASE}/marking-codes/([^/]+)$`).exec(path)
    if (removal && method === 'DELETE') {
      const index = kiz.findIndex((one) => one.id === removal[1])
      if (index >= 0) kiz.splice(index, 1)
      return json({ removed: index >= 0 })
    }
    if (path === `${FAKE_BASE}/boxes/attach` && body) return attach(body)
    unexpected.push(`${method} ${path}`)
    return json({ detail: `unexpected ${method} ${path}` }, 404)
  }

  return {
    handle,
    requests,
    unexpected,
    kiz,
    totalTaken,
    takenOf,
    /** Положить уже существующий КИЗ (для проверки списка). */
    seedKiz(cis: string, productId: string, intake: string | null = null) {
      kizSeq += 1
      kiz.push({ id: `kiz-${kizSeq}`, cis, productId, intake })
    },
    seedTaken: setTaken,
    failNextPickSet() {
      failNextPickSet = true
    },
    unlinkOnNextPickSet(codes: string[]) {
      nextUnlinked = codes
    },
  }
}

type FboPickFakeServer = ReturnType<typeof createFboPickFakeServer>

// WMS-686 · подбор отгрузки FBO: настоящий FfUnloadPickPage с настоящим экраном, сеть подменена
// подставным сервером (fboPickFakeServer.ts). Сканер — «клавиатурный»: символы и Enter.

const printed = vi.hoisted(() => ({ keys: [] as string[], failNext: 0 }))
vi.mock('../../../utils/czLabelPng', () => ({ renderCzLabelPng: async () => 'data:image/png;base64,AAAA' }))
vi.mock('../../../utils/printPreparedQr', () => ({
  printPreparedQr: async (input: { idempotencyKey: string }) => {
    printed.keys.push(input.idempotencyKey)
    if (printed.failNext > 0) {
      printed.failNext -= 1
      throw new Error('Нет ответа WMS Print.')
    }
  },
}))

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const originalFetch = globalThis.fetch
let host: HTMLDivElement
let root: Root
let server: FboPickFakeServer
let changed: number
/** Сдвиг часов performance.now(): между сканами «проходит время» без ожидания. */
let clockShift = 0

const KIZ_A1 = '010460000000001121AbCd000001'
const KIZ_A2 = '010460000000001121AbCd000002'
const KIZ_A3 = '010460000000001121AbCd000003'
const KIZ_B1 = '010460000000002821ZzZz000001'
const PRODUCT_A = '4600000000011'

beforeEach(() => {
  server = createFboPickFakeServer()
  changed = 0
  clockShift = 0
  printed.keys = []
  printed.failNext = 0
  const realNow = performance.now.bind(performance)
  vi.spyOn(performance, 'now').mockImplementation(() => realNow() + clockShift)
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => server.handle(input, init)) as typeof fetch
  window.sessionStorage.clear()
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  document.body.innerHTML = ''
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

async function settle(ms = 0) {
  const steps = Math.max(1, Math.ceil(ms / 10))
  for (let step = 0; step < steps; step += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, Math.min(ms || 10, 10)))
    })
  }
}

function page() {
  return (
    <MemoryRouter>
      <FfUnloadPickPage token="t" requestId={FAKE_REQUEST_ID} hideHeader onChanged={() => { changed += 1 }} />
    </MemoryRouter>
  )
}

async function open() {
  await act(async () => root.render(page()))
  await settle(60)
}

function keydown(target: Element, key: string) {
  target.dispatchEvent(new KeyboardEvent('keydown', {
    key, code: /\d/.test(key) ? `Digit${key}` : key, bubbles: true, cancelable: true,
  }))
}

/** «Клавиатурный» сканер: символы подряд и Enter — туда, где фокус. */
function scan(code: string) {
  const target = document.activeElement ?? document.body
  act(() => {
    for (const key of code) keydown(target, key)
    keydown(target, 'Enter')
  })
}

async function scanAndWait(code: string, ms = 60) {
  scan(code)
  await settle(ms)
}

const q = (testId: string) => host.querySelector<HTMLElement>(`[data-testid="${testId}"]`)
const qa = (selector: string) => [...host.querySelectorAll<HTMLElement>(selector)]
const click = async (element: Element | null) => {
  expect(element).not.toBeNull()
  await act(async () => (element as HTMLElement).click())
  await settle(20)
}
const scanLine = () => q('unload-pick-screen')?.textContent ?? ''
const post = (suffix: string) => server.requests.filter((one) => one.method === 'POST' && one.path === `${FAKE_BASE}/${suffix}`)

describe('WMS-686 · вкладка «Подбор» отгрузки FBO: виды и раскрытие', () => {
  it('D1.1: по умолчанию «По ячейкам» с «План»/«Осталось»; переключатель даёт «По товарам» над теми же данными', async () => {
    await open()

    expect(q('fbs-cell-pick-table')).not.toBeNull()
    expect(q('pick-table')).toBeNull()
    expect(q('pick-view-switch')?.textContent).toBe('По ячейкамПо товарам')
    const headers = qa('[data-testid="fbs-cell-pick-table"] th').map((one) => one.textContent)
    expect(headers).toEqual(expect.arrayContaining(['План', 'Осталось', 'КИЗ', 'Собрано']))
    expect(q('pick-left-qty')?.textContent).toBe('9')

    await click(q('pick-view-products'))
    expect(q('pick-table')).not.toBeNull()
    expect(q('fbs-cell-pick-table')).toBeNull()
    expect(q('pick-left-qty')?.textContent).toBe('9')
    expect(qa('[data-testid="pick-table"] th').map((one) => one.textContent)).toContain('КИЗ')
  })

  it('D1.2: ячейки и короба сворачиваются стрелкой и раскрываются обратно; выбор источника не трогается', async () => {
    await open()
    await scanAndWait('INB-000101')
    expect(q('pick-source')?.textContent).toBe('INB-000101')
    const goodsBefore = qa('[data-testid^="fbs-pick-item-"]').length

    await click(q('fbs-pick-collapse-cell:loc-a'))
    expect(qa('[data-testid^="fbs-pick-item-"]').length).toBeLessThan(goodsBefore)
    expect(q('fbs-pick-item-obj:box-1')).toBeNull()
    expect(q('pick-source')?.textContent).toBe('INB-000101')

    await click(q('fbs-pick-collapse-cell:loc-a'))
    expect(qa('[data-testid^="fbs-pick-item-"]').length).toBe(goodsBefore)
  })

  it('D1.2: вид, раскрытие и источник переживают ошибку сохранения и новое открытие вкладки', async () => {
    await open()
    await click(q('pick-view-products'))
    await scanAndWait('INB-000101')
    await scanAndWait(PRODUCT_A)
    expect(q('pick-source')?.textContent).toBe('INB-000101')

    // Сервер отказал в ручной правке: страница перечитывает документ, но экран не сбрасывается.
    server.failNextPickSet()
    const input = host.querySelector<HTMLInputElement>('input[data-testid^="pick-place-qty-"]')!
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '2')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await settle(700)
    expect(q('pick-view-products')?.getAttribute('aria-pressed')).toBe('true')
    expect(q('pick-source')?.textContent).toBe('INB-000101')
    expect(q('pick-table')).not.toBeNull()

    // Смена вкладки документа: экран размонтирован и открыт заново.
    await act(async () => root.render(<div />))
    await open()
    expect(q('pick-view-products')?.getAttribute('aria-pressed')).toBe('true')
    expect(q('pick-source')?.textContent).toBe('INB-000101')
    expect(q('pick-table')).not.toBeNull()
  })
})

describe('WMS-686 · КИЗ в подборе FBO', () => {
  it('D1.3: число КИЗ — счёт кодов товара; клик раскрывает вертикальный список, повтор скрывает', async () => {
    server.seedKiz(KIZ_A1, 'p-a', '000041')
    server.seedKiz(KIZ_A2, 'p-a')
    await open()

    const count = q('pick-kiz-count-p-a-cell:loc-a')!
    expect(count.textContent).toBe('2')
    // У товара без Честного знака и без КИЗ ячейка пуста (R3).
    expect(q('pick-kiz-count-p-b-obj:box-3')).toBeNull()
    expect(qa('[data-testid="pick-kiz-row"]')).toHaveLength(0)

    await click(count)
    const rows = qa('[data-testid="pick-kiz-row"]')
    expect(rows.map((one) => one.textContent)).toEqual([
      expect.stringContaining(KIZ_A1),
      expect.stringContaining(KIZ_A2),
    ])
    expect(rows[0]!.textContent).toContain('Приёмка 000041')
    expect(rows[1]!.textContent).not.toContain('Приёмка')

    expect(rows[0]!.querySelector('button[aria-label="Отвязать код"]')).not.toBeNull()

    await click(count)
    expect(qa('[data-testid="pick-kiz-row"]')).toHaveLength(0)
  })

  it('R3: один список на товар — под первой строкой товара; число в другой строке того же товара его скрывает', async () => {
    server.seedKiz(KIZ_A1, 'p-a')
    await open()

    await click(q('pick-kiz-count-p-a-obj:box-2'))
    expect(qa('[data-testid="pick-kiz-list-p-a"]')).toHaveLength(1)
    // Список стоит сразу под первой строкой товара (россыпь на ячейке А-1-1), а не под строкой, где нажали.
    const firstGoods = q('fbs-pick-item-line-p-a|cell:loc-a')!.closest('tr')!
    expect(firstGoods.nextElementSibling?.querySelector('[data-testid="pick-kiz-list-p-a"]')).not.toBeNull()

    await click(q('pick-kiz-count-p-a-obj:box-1'))
    expect(qa('[data-testid="pick-kiz-list-p-a"]')).toHaveLength(0)
  })

  it('R19: подбор стал меньше числа КИЗ — сервер отвязал коды, экран говорит об этом без красного', async () => {
    server.seedKiz(KIZ_A1, 'p-a')
    await open()
    await scanAndWait('INB-000101')
    await scanAndWait(PRODUCT_A)
    server.unlinkOnNextPickSet([KIZ_A1])
    const input = host.querySelector<HTMLInputElement>('input[data-testid="pick-place-qty-p-a-obj:box-1"]')!
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '0')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await settle(700)

    expect(scanLine()).toContain(`Отвязаны КИЗ: ${KIZ_A1}`)
    expect(q('pick-scan')?.getAttribute('aria-invalid')).not.toBe('true')
  })

  it('R7: код, который не товар, не ячейка и не тара, уходит на привязку КИЗ; отказ сервера — красным', async () => {
    await open()
    await scanAndWait('INB-000101')
    await scanAndWait(PRODUCT_A)
    await scanAndWait('ABCDEFGHIJKLMNOP')

    expect(post('marking-codes/scan').at(-1)!.body).toMatchObject({ code: 'ABCDEFGHIJKLMNOP', product_id: 'p-a' })
    expect(scanLine()).toContain('Не похоже на код Честного знака')
    expect(q('pick-scan')?.getAttribute('aria-invalid')).toBe('true')
  })

  it('D1.4: ШК товара → КИЗ привязан к этому товару; число меняется сразу, а открытый список получает код', async () => {
    await open()
    await scanAndWait('INB-000101')
    await click(q('pick-kiz-count-p-a-cell:loc-a'))
    expect(q('pick-kiz-count-p-a-cell:loc-a')?.textContent).toBe('0')

    await scanAndWait(PRODUCT_A)
    await scanAndWait(KIZ_A1)

    expect(post('marking-codes/scan')[0]!.body).toMatchObject({ code: KIZ_A1, product_id: 'p-a' })
    expect(q('pick-kiz-count-p-a-cell:loc-a')?.textContent).toBe('1')
    expect(q('pick-left-qty')?.textContent).toBe('8')
    expect(scanLine()).toContain('КИЗ привязан')
    expect(changed).toBeGreaterThan(0)
  })

  it('D1.4: КИЗ без ШК товара прямо перед ним уходит без product_id; сервер отказывает — красный текст и число прежнее', async () => {
    await open()
    await scanAndWait('INB-000101')
    await scanAndWait(PRODUCT_A)
    await scanAndWait(KIZ_A1)
    await scanAndWait(KIZ_A2)

    expect(post('marking-codes/scan')[1]!.body).not.toHaveProperty('product_id')
    // Сервер определил товар по GTIN, но подобрана одна штука — второй код сверх неё.
    expect(scanLine()).toContain('Сначала отсканируйте ШК следующей штуки')
    expect(q('pick-kiz-count-p-a-cell:loc-a')?.textContent).toBe('1')
  })

  it('D1.4: повтор того же КИЗ — «уже привязан», без второго кода', async () => {
    await open()
    await scanAndWait('INB-000101')
    await scanAndWait(PRODUCT_A)
    await scanAndWait(KIZ_A1)
    await scanAndWait(PRODUCT_A)
    await scanAndWait(KIZ_A1)

    expect(q('pick-kiz-count-p-a-cell:loc-a')?.textContent).toBe('1')
    expect(scanLine()).toContain('уже привязан к товару')
  })

  it('D1.4: код другого товара — отказ без привязки', async () => {
    await open()
    await scanAndWait('INB-000101')
    await scanAndWait(PRODUCT_A)
    await scanAndWait(KIZ_B1)

    expect(scanLine()).toContain('другому товару')
    expect(q('pick-kiz-count-p-a-cell:loc-a')?.textContent).toBe('0')
    expect(server.kiz).toHaveLength(0)
  })

  it('D1.9: отказ по штуке сверх плана не мешает привязать КИЗ к уже подобранной штуке', async () => {
    await open()
    await scanAndWait('INB-000101')
    for (let index = 0; index < 3; index += 1) await scanAndWait(PRODUCT_A)
    await scanAndWait('INB-000102')
    for (let index = 0; index < 3; index += 1) await scanAndWait(PRODUCT_A)
    expect(server.totalTaken('p-a')).toBe(6)

    await scanAndWait(PRODUCT_A)
    expect(scanLine()).toContain('Нельзя подобрать больше')
    expect(server.totalTaken('p-a')).toBe(6)

    await scanAndWait(KIZ_A3)
    expect(post('marking-codes/scan').at(-1)!.body).toMatchObject({ code: KIZ_A3, product_id: 'p-a' })
    expect(q('pick-kiz-count-p-a-cell:loc-a')?.textContent).toBe('1')
  })

  it('D1.3: ✕ отвязывает ошибочный код (DELETE), «Перепечатать» печатает через WMS Print с одним ключом на повтор', async () => {
    server.seedKiz(KIZ_A1, 'p-a', '000041')
    await open()
    await click(q('pick-kiz-count-p-a-cell:loc-a'))

    printed.failNext = 1
    await click(q('pick-kiz-reprint'))
    await settle(30)
    expect(scanLine()).toContain('Нет ответа WMS Print')
    await click(q('pick-kiz-reprint'))
    await settle(30)
    await click(q('pick-kiz-reprint'))
    await settle(30)
    expect(printed.keys).toHaveLength(3)
    // Первая попытка не удалась — её повтор идёт с тем же ключом; после успеха ключ новый.
    expect(printed.keys[1]).toBe(printed.keys[0])
    expect(printed.keys[2]).not.toBe(printed.keys[0])

    await click(q('pick-kiz-remove'))
    await settle(30)
    expect(server.requests.some((one) => one.method === 'DELETE' && one.path.endsWith('/marking-codes/kiz-1'))).toBe(true)
    expect(q('pick-kiz-count-p-a-cell:loc-a')?.textContent).toBe('0')
    expect(qa('[data-testid="pick-kiz-row"]')).toHaveLength(0)
  })
})

describe('WMS-686 · «Забрать короб целиком»: двойной скан и кнопка', () => {
  it('D1.6: тот же ШК короба второй раз в окне 2 с забирает короб; источник сброшен, данные перечитаны', async () => {
    await open()
    await scanAndWait('INB-000101', 30)
    expect(q('pick-source')?.textContent).toBe('INB-000101')
    await scanAndWait('INB-000101')

    expect(post('boxes/attach')).toHaveLength(1)
    expect(post('boxes/attach')[0]!.body).toEqual({ barcode: 'INB-000101', allow_over_plan: false })
    expect(q('pick-source')).toBeNull()
    expect(server.totalTaken('p-a')).toBe(3)
    expect(q('pick-left-qty')?.textContent).toBe('6')
    expect(changed).toBeGreaterThan(0)
  })

  it('D1.6: третий быстрый скан ничего не переносит и не показывает ошибку', async () => {
    await open()
    await scanAndWait('INB-000101', 30)
    await scanAndWait('INB-000101', 30)
    const requestsBefore = server.requests.length
    await scanAndWait('INB-000101', 30)

    expect(post('boxes/attach')).toHaveLength(1)
    expect(server.requests.length).toBe(requestsBefore)
    expect(host.querySelector('[data-testid="pick-scan"]')?.getAttribute('aria-invalid')).not.toBe('true')
  })

  it('D1.6: второй скан позже 2 с — не перенос; скан другого кода между сканами рвёт пару', async () => {
    await open()
    await scanAndWait('INB-000101', 30)
    clockShift += 2500
    await scanAndWait('INB-000101', 30)
    expect(post('boxes/attach')).toHaveLength(0)

    await scanAndWait('INB-000102', 30)
    await scanAndWait(KIZ_A1, 30)
    await scanAndWait('INB-000102', 30)
    expect(post('boxes/attach')).toHaveLength(0)
  })

  it('D1.7: короб больше оставшегося плана — отказ с текстом сервера, ничего не меняется, источник на месте', async () => {
    await open()
    await scanAndWait('INB-000101')
    for (let index = 0; index < 3; index += 1) await scanAndWait(PRODUCT_A)
    await scanAndWait('INB-000102', 30)
    await scanAndWait('INB-000102', 30)

    expect(post('boxes/attach')).toHaveLength(1)
    expect(scanLine()).toContain('Количество товаров в коробе больше, чем осталось подобрать')
    expect(scanLine()).toContain('в коробе 4, осталось 3')
    expect(server.totalTaken('p-a')).toBe(3)
    expect(q('pick-source')?.textContent).toBe('INB-000102')
  })

  it('R8: повтор переноса уже перенесённого короба — спокойное сообщение, без красного', async () => {
    await open()
    await scanAndWait('INB-000103', 30)
    await scanAndWait('INB-000103')
    expect(post('boxes/attach')).toHaveLength(1)

    clockShift += 2500
    await scanAndWait('INB-000103', 30)
    await scanAndWait('INB-000103')

    expect(post('boxes/attach')).toHaveLength(2)
    expect(scanLine()).toContain('Этот короб уже в отгрузке.')
    expect(q('pick-scan')?.getAttribute('aria-invalid')).not.toBe('true')
  })

  it('D1.6: кнопка «Забрать короб целиком» в строке «Снимаем с:» делает то же, что двойной скан', async () => {
    await open()
    expect(q('pick-take-whole-box')).toBeNull()
    await scanAndWait('INB-000103')
    await click(q('pick-take-whole-box'))
    await settle(60)

    expect(post('boxes/attach')[0]!.body).toEqual({ barcode: 'INB-000103', allow_over_plan: false })
    expect(q('pick-source')).toBeNull()
    expect(q('pick-take-whole-box')).toBeNull()
    expect(server.totalTaken('p-b')).toBe(2)
  })

  it('D1.8: после переноса строки короба серые, а у ячейки со свободным товаром — обычные', async () => {
    await open()
    await scanAndWait('INB-000101', 30)
    await scanAndWait('INB-000101')

    const opacityOf = (itemKey: string) => {
      const item = q(`fbs-pick-item-${itemKey}`)
      return item ? getComputedStyle(item).opacity : null
    }
    const boxRow = qa('[data-testid^="fbs-pick-item-"]').find((one) => one.getAttribute('data-testid')!.startsWith('fbs-pick-item-line-p-a|obj:box-1'))
    const otherRow = qa('[data-testid^="fbs-pick-item-"]').find((one) => one.getAttribute('data-testid')!.startsWith('fbs-pick-item-line-p-a|obj:box-2'))
    expect(boxRow).toBeTruthy()
    expect(otherRow).toBeTruthy()
    expect(getComputedStyle(boxRow!).opacity).toBe('0.55')
    expect(getComputedStyle(otherRow!).opacity).not.toBe('0.55')
    expect(opacityOf('cell:loc-a')).not.toBe('0.55')
  })

  it('D1.10: надписи «состав КИЗ тары неизвестен» нет', async () => {
    await open()
    await scanAndWait('INB-000101')
    expect(host.textContent).not.toContain('неизвестен')
    expect(host.textContent).not.toContain('состав КИЗ')
  })
})
