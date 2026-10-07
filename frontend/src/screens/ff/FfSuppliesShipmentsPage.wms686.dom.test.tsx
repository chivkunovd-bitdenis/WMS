// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfSuppliesShipmentsPage, type FfMarketplaceUnloadSummary } from './FfSuppliesShipmentsPage'

// WMS-686 · контракт вкладки «Упаковка» отгрузки FBO (docs/requirements/WMS-686.md,
// разделы 4.3, 5 (R12–R16, R28, R31, R32), 9 и 10). Настоящая страница
// «Отгрузки на МП» с открытым документом; подменены только внешние границы:
// - сеть: globalThis.fetch отвечает подставным сервером этого файла по формам
//   ответов API (раздел 9), включая WMS Print на http://127.0.0.1:17843/print;
// - Canvas/Image браузера, которых нет в jsdom: getContext даёт пустой 2D
//   контекст, toDataURL — постоянную картинку, Image «загружается» сразу.
// Сканер — «клавиатурный»: символы и Enter туда, где сейчас фокус.
// Неизвестный маршрут получает 404 с телом и записывается — каждый тест в конце
// проверяет, что таких обращений не было, чтобы 404 не маскировал ошибку.

// Сборный пакет иконок (@mui/icons-material, >10 тыс. модулей) грузится больше
// минуты и не влияет на поведение. Любая иконка из него — пустой <svg>; имена
// не перечислены, чтобы новая иконка в продукте не ломала тест. Отдельные
// импорты вида '@mui/icons-material/AddOutlined' остаются настоящими.
vi.mock('@mui/icons-material', async () => {
  const { createElement } = await import('react')
  const icons = new Map<string, unknown>()
  const icon = (name: string) => {
    let component = icons.get(name)
    if (!component) {
      const Icon = () => createElement('svg', { 'aria-hidden': true, 'data-mock-icon': name })
      Icon.muiName = 'SvgIcon'
      component = Icon
      icons.set(name, component)
    }
    return component
  }
  return new Proxy({} as Record<string, unknown>, {
    has: (_target, name) => typeof name === 'string' && name !== 'then',
    get: (_target, name) => {
      if (typeof name !== 'string' || name === 'then' || name === 'default') return undefined
      if (name === '__esModule') return true
      return icon(name)
    },
  })
})

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const SHIPMENT_ID = 'mp-686'
const TASK_ID = 'task-686'
const BASE = `/operations/marketplace-unload-requests/${SHIPMENT_ID}`
const SELLER = { id: 'seller-686', name: 'ИП Тестовый' }
const WMS_PRINT_URL = 'http://127.0.0.1:17843/print'
const TOKEN = `contract.${btoa(JSON.stringify({ tenant_id: 'tenant-686', sub: 'user-686' }))}.signature`

type Product = {
  id: string
  lineId: string
  sku: string
  name: string
  barcode: string
  gtin: string
  plan: number
  honestSign: boolean
}

const PRODUCT_A: Product = {
  id: 'p-a', lineId: 'pl-a', sku: 'SKU-686-A', name: 'Футболка хлопковая 48',
  barcode: '4600000000011', gtin: '04600000000011', plan: 4, honestSign: true,
}
const PRODUCT_B: Product = {
  id: 'p-b', lineId: 'pl-b', sku: 'SKU-686-B', name: 'Футболка хлопковая 50',
  barcode: '4600000000028', gtin: '04600000000028', plan: 2, honestSign: false,
}
const PRODUCTS = [PRODUCT_A, PRODUCT_B]
const CELL = { id: 'loc-1', code: 'А-1-1' }
/** Короба хранения, из которых подбирали (источники подбора). */
const SOURCE_K1 = { id: 'box-k1', code: 'INB-000123' }
const SOURCE_K2 = { id: 'box-k2', code: 'INB-000124' }
/** Короба отгрузки. */
const BOX_B1 = { id: 'box-b1', barcode: 'WHB-0000000686B1' }
const BOX_B2 = { id: 'box-b2', barcode: 'WHB-0000000686B2' }
/** КИЗ формата GS1: 01 + GTIN-14 + 21 + серийный номер (D1). */
const KIZ_1 = `01${PRODUCT_A.gtin}21AbCdEf000001`
const KIZ_2 = `01${PRODUCT_A.gtin}21AbCdEf000002`
/** КИЗ единиц, уже лежащих в коробе (C39): снятый при подборе (источник известен) и впервые отсканированный на упаковке. */
const KIZ_SOURCE_KNOWN = `01${PRODUCT_A.gtin}21Qx7Lm1Zp`
const KIZ_SOURCE_UNKNOWN = `01${PRODUCT_A.gtin}21Wv3Nk8Rt`
/** КИЗ с GTIN, которого нет в карточках селлера. */
const KIZ_UNKNOWN_GTIN = '010469999999999021ZzZz000009'
/** Пул кодов товара A для «Печатать ЧЗ» (C44). */
const POOL_1 = `01${PRODUCT_A.gtin}21PoOl000001`
const POOL_2 = `01${PRODUCT_A.gtin}21PoOl000002`
const PRINTER_ERROR = 'Принтер не отвечает (WMS-686 C45)'

const isKiz = (code: string) => /^01\d{14}21/.test(code) || /^\(01\)\d{14}\(21\)/.test(code)

type Recorded = { method: string; url: string; path: string; body: Record<string, unknown> | null }
type BoxSpec = { id: string; barcode: string; closed?: boolean; units?: Record<string, number> }
type BoxState = { id: string; barcode: string; closed: boolean; units: Map<string, number> }
/** Откуда сняли товар при подборе: короб хранения или россыпь ячейки (container: null). */
type SourceSpec = { productId: string; container: { id: string; code: string } | null; picked: number }
type MarkingLink = {
  marking_code_id: string
  cis_code: string
  product_id: string
  box_id: string | null
  container_id: string | null
  storage_location_id: string | null
}
type PrintMode = 'ok' | 'error' | 'reject'

/** По умолчанию: A — 4 шт. сняты из K1, B — 2 шт. россыпью; ничего не уложено. */
const DEFAULT_SOURCES: SourceSpec[] = [
  { productId: PRODUCT_A.id, container: SOURCE_K1, picked: 4 },
  { productId: PRODUCT_B.id, container: null, picked: 2 },
]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/**
 * Подставной сервер отгрузки FBO: короба, источники подбора, связи КИЗ, пул
 * кодов и задания WMS Print живут здесь; экран видит только ответы API.
 */
function createPackServer({
  boxes: boxSpecs,
  sources: sourceSpecs = DEFAULT_SOURCES,
  links: initialLinks = [],
  pool: initialPool = [],
}: {
  boxes: BoxSpec[]
  sources?: SourceSpec[]
  links?: MarkingLink[]
  pool?: string[]
}) {
  const requests: Recorded[] = []
  const unknown: string[] = []
  const boxes: BoxState[] = boxSpecs.map((box) => ({
    id: box.id, barcode: box.barcode, closed: Boolean(box.closed), units: new Map(Object.entries(box.units ?? {})),
  }))
  const sources = sourceSpecs.map((source) => ({ ...source }))
  const links: MarkingLink[] = initialLinks.map((link) => ({ ...link }))
  const pool = [...initialPool]
  const prints: Array<Record<string, unknown>> = []
  const receipts = new Map<string, string>()
  const replies = new Map<string, unknown>()
  let printMode: PrintMode = 'ok'

  const productById = (id: unknown) => PRODUCTS.find((product) => product.id === id) ?? null
  const picked = (productId: string) =>
    sources.filter((source) => source.productId === productId).reduce((sum, source) => sum + source.picked, 0)
  const packed = (productId: string) =>
    boxes.reduce((sum, box) => sum + (box.units.get(productId) ?? 0), 0)
  const packedTotal = () => PRODUCTS.reduce((sum, product) => sum + packed(product.id), 0)
  const pickedTotal = () => PRODUCTS.reduce((sum, product) => sum + picked(product.id), 0)
  const boxLineId = (boxId: string, productId: string) => `${boxId}-${productId}`
  const unmarkedInBox = (box: BoxState, productId: string) =>
    (box.units.get(productId) ?? 0) - links.filter((link) => link.box_id === box.id && link.product_id === productId).length

  const boxOut = (box: BoxState) => ({
    id: box.id,
    box_preset: '60_40_40',
    internal_barcode: box.barcode,
    closed_at: box.closed ? '2026-10-08T10:00:00Z' : null,
    lines: PRODUCTS.filter((product) => (box.units.get(product.id) ?? 0) > 0).map((product) => ({
      id: boxLineId(box.id, product.id),
      product_id: product.id,
      sku_code: product.sku,
      product_name: product.name,
      quantity: box.units.get(product.id) ?? 0,
    })),
  })

  const detail = () => ({
    id: SHIPMENT_ID,
    document_number: '000686',
    display_number: '000686',
    public_number: null,
    human_number: null,
    warehouse_id: 'wh-686',
    warehouse_name: 'Склад ФФ',
    status: 'collecting',
    ff_modified: false,
    seller_id: SELLER.id,
    seller_name: SELLER.name,
    marketplace: 'wb',
    wb_mp_warehouse_id: 1,
    planned_shipment_date: '2026-10-09',
    created_at: '2026-10-06T12:00:00Z',
    lines: PRODUCTS.map((product) => ({
      id: `line-${product.id}`,
      product_id: product.id,
      sku_code: product.sku,
      product_name: product.name,
      quantity: product.plan,
      picked_qty: picked(product.id),
    })),
    boxes: boxes.map(boxOut),
    pick_allocations: sources.filter((source) => source.picked > 0).map((source) => {
      const product = productById(source.productId)!
      return {
        id: `alloc-${source.productId}-${source.container?.id ?? 'loose'}`,
        product_id: product.id,
        sku_code: product.sku,
        product_name: product.name,
        storage_location_id: CELL.id,
        location_code: CELL.code,
        quantity: source.picked,
      }
    }),
    linked_packaging_task: {
      task_id: TASK_ID,
      status: 'in_progress',
      qty_done: packedTotal(),
      qty_total: pickedTotal(),
      is_complete: false,
    },
  })

  const task = () => ({
    id: TASK_ID,
    document_number: '000686',
    display_number: '000686',
    warehouse_id: 'wh-686',
    warehouse_name: 'Склад ФФ',
    seller_id: SELLER.id,
    seller_name: SELLER.name,
    status: 'in_progress',
    marketplace_unload_request_id: SHIPMENT_ID,
    inbound_intake_request_id: null,
    is_complete: false,
    pick_resync_warning: false,
    events: [],
    lines: PRODUCTS.map((product) => ({
      id: product.lineId,
      product_id: product.id,
      seller_id: SELLER.id,
      seller_name: SELLER.name,
      sku_code: product.sku,
      product_name: product.name,
      size: null,
      color: null,
      storage_location_id: 'sorting',
      storage_location_code: '__SORTING__',
      packaging_instructions: null,
      requires_honest_sign: product.honestSign,
      qty_total: picked(product.id),
      qty_suggested_packed: picked(product.id),
      qty_confirmed_packed: packed(product.id),
      qty_need_pack: picked(product.id),
      qty_packed_in_task: packed(product.id),
      qty_done: packed(product.id),
      qty_marking_printed: 0,
      qty_marking_external: links.filter((link) => link.product_id === product.id).length,
      qty_product_label_printed: 0,
      marking_available_count: pool.length,
      is_complete: packed(product.id) >= picked(product.id),
    })),
  })

  /** Раздел 9 п.12: места подбора с тарой и составом КИЗ «точно/возможно в таре» (здесь — пустой). */
  const pickOptions = () => PRODUCTS.map((product) => {
    const own = sources.filter((source) => source.productId === product.id)
    return {
      product_id: product.id,
      sku_code: product.sku,
      product_name: product.name,
      seller_article: null,
      barcode: null,
      planned_qty: product.plan,
      picked_qty: picked(product.id),
      locations: own.length === 0 ? [] : [{
        storage_location_id: CELL.id,
        location_code: CELL.code,
        quantity: own.length * 2,
        reserved: 0,
        available: own.length * 2,
        picked: picked(product.id),
        sources: own.map((source) => ({
          quantity: 2,
          available: 2,
          is_loose: source.container === null,
          source_label: source.container ? `Короб ${source.container.code}` : 'Россыпью',
          picked: source.picked,
          container_path: source.container
            ? [{ kind: 'box', id: source.container.id, code: source.container.code, label: `Короб ${source.container.code}` }]
            : [],
          known_marking_codes: [],
          uncertain_marking_codes: [],
        })),
      }],
    }
  })

  const catalog = PRODUCTS.map((product, index) => ({
    id: product.id,
    name: product.name,
    sku_code: product.sku,
    seller_name: SELLER.name,
    wb_nm_id: 100686001 + index,
    wb_vendor_code: `ART-686-${index + 1}`,
    wb_subject_name: 'Футболки',
    wb_primary_image_url: null,
    wb_barcodes: [product.barcode],
    wb_primary_barcode: product.barcode,
    wb_size: index === 0 ? '48' : '50',
    wb_color: null,
    marketplaces: ['wb'],
    marketplace_bindings: [],
  }))

  const productByGtin = (code: string) => {
    const gtin = code.replace(/[()]/g, '').slice(2, 16).replace(/^0+/, '')
    return PRODUCTS.find((product) => product.barcode.replace(/^0+/, '') === gtin) ?? null
  }

  const replay = (mutationId: unknown) =>
    typeof mutationId === 'string' && replies.has(mutationId) ? json(replies.get(mutationId)) : null
  const remember = (mutationId: unknown, reply: unknown) => {
    if (typeof mutationId === 'string') replies.set(mutationId, reply)
    return json(reply)
  }

  /** Раздел 9 п.5, п.9: укладка в короб; с pick_from_storage=false — только подобранное. */
  function boxScan(boxId: string, body: Record<string, unknown>): Response {
    const box = boxes.find((one) => one.id === boxId)
    if (!box) return json({ detail: 'box_not_found' }, 404)
    const replayed = replay(body.mutation_id)
    if (replayed) return replayed
    const barcode = String(body.barcode ?? '')
    if (isKiz(barcode)) {
      // Раздел 9 п.9, D16: product_id — товар последнего ШК (контекст единицы);
      // без него — контекст проверки короба по GTIN кода.
      const byGtin = productByGtin(barcode)
      const unitContext = typeof body.product_id === 'string' ? productById(body.product_id) : null
      if (unitContext && byGtin && byGtin.id !== unitContext.id) return json({ detail: 'marking_code_other_product' }, 422)
      const target = unitContext ?? byGtin
      if (!target) return json({ detail: 'marking_product_unknown' }, 422)
      const existing = links.find((link) => link.cis_code === barcode)
      if (existing && existing.box_id !== null && existing.box_id !== box.id) {
        return json({ detail: 'marking_code_other_box' }, 422)
      }
      if (existing) {
        existing.box_id = box.id
        return remember(body.mutation_id, {
          kind: 'marking', product_id: existing.product_id, marking_code_id: existing.marking_code_id,
          cis_code: barcode, already_linked: true, box_id: box.id,
        })
      }
      // R14: код идёт только в текущий короб, к его непомеченной единице этого товара.
      if (unmarkedInBox(box, target.id) <= 0) return json({ detail: 'marking_unit_not_in_box' }, 422)
      const link: MarkingLink = {
        marking_code_id: `mc-${links.length + 1}`, cis_code: barcode, product_id: target.id,
        box_id: box.id, container_id: null, storage_location_id: null,
      }
      links.push(link)
      return remember(body.mutation_id, {
        kind: 'marking', product_id: target.id, marking_code_id: link.marking_code_id,
        cis_code: barcode, already_linked: false, box_id: box.id,
      })
    }
    const product = PRODUCTS.find((one) => one.barcode === barcode || one.sku === barcode)
    if (!product) return json({ detail: 'barcode_unknown' }, 422)
    if (packed(product.id) >= picked(product.id)) {
      return json({ detail: body.pick_from_storage === false ? 'nothing_picked_to_pack' : 'insufficient_available' }, 422)
    }
    box.units.set(product.id, (box.units.get(product.id) ?? 0) + 1)
    return remember(body.mutation_id, {
      kind: 'product', id: boxLineId(box.id, product.id), product_id: product.id, sku_code: product.sku,
      product_name: product.name, quantity: box.units.get(product.id), picked_qty: picked(product.id),
      storage_location_id: null, location_code: null, container_kind: null, container_id: null,
      container_code: null, lines_added: null, total_qty: null,
    })
  }

  /**
   * Раздел 9 п.10: убрать одну единицу (с этим кодом или без КИЗ). Код с источником
   * подбора возвращается туда (source_known=true); код без источника и единица без
   * КИЗ — в выбранное место return_to из источников подбора этого товара.
   */
  function removeLine(boxId: string, lineId: string, body: Record<string, unknown>): Response {
    const box = boxes.find((one) => one.id === boxId)
    const product = PRODUCTS.find((one) => boxLineId(boxId, one.id) === lineId)
    if (!box || !product || (box.units.get(product.id) ?? 0) <= 0) return json({ detail: 'line_not_found' }, 404)
    const replayed = replay(body.mutation_id)
    if (replayed) return replayed
    const productSources = sources.filter((source) => source.productId === product.id)
    const requested = body.return_to && typeof body.return_to === 'object'
      ? (body.return_to as { storage_location_id?: unknown; container_id?: unknown })
      : null
    const chosen = requested
      ? productSources.find((source) => (source.container?.id ?? null) === (requested.container_id ?? null))
      : undefined
    if (requested && !chosen) return json({ detail: 'invalid_return_place' }, 422)
    let returnedTo: { storage_location_id: string; container_id: string | null }
    let sourceKnown = false
    if (typeof body.marking_code_id === 'string') {
      const index = links.findIndex((link) =>
        link.marking_code_id === body.marking_code_id && link.box_id === box.id && link.product_id === product.id)
      if (index < 0) return json({ detail: 'marking_code_not_found' }, 404)
      const link = links[index]
      if (link.container_id === null && !chosen) return json({ detail: 'return_place_required' }, 422)
      links.splice(index, 1)
      sourceKnown = link.container_id !== null
      returnedTo = { storage_location_id: CELL.id, container_id: sourceKnown ? link.container_id : chosen!.container?.id ?? null }
    } else {
      if (unmarkedInBox(box, product.id) <= 0) return json({ detail: 'marking_unit_ambiguous' }, 422)
      // D14: по умолчанию — последний источник подбора товара, где есть единицы без КИЗ.
      const plain = productSources.filter((source) => source.picked >
        links.filter((link) => link.product_id === product.id && link.container_id === (source.container?.id ?? null)).length)
      const source = chosen ?? plain[plain.length - 1]
      returnedTo = { storage_location_id: CELL.id, container_id: source?.container?.id ?? null }
    }
    const source = sources.find((one) => one.productId === product.id && (one.container?.id ?? null) === returnedTo.container_id)
    if (source && source.picked > 0) source.picked -= 1
    box.units.set(product.id, (box.units.get(product.id) ?? 0) - 1)
    return remember(body.mutation_id, {
      id: lineId, product_id: product.id, sku_code: product.sku, product_name: product.name,
      quantity: box.units.get(product.id), returned_to: returnedTo, source_known: sourceKnown,
    })
  }

  /** Раздел 9 п.11: один код из пула на единицу товара в коробе. */
  function printMarking(boxId: string, body: Record<string, unknown>): Response {
    const box = boxes.find((one) => one.id === boxId)
    const product = productById(body.product_id)
    if (!box || !product) return json({ detail: 'line_not_found' }, 404)
    const replayed = replay(body.mutation_id)
    if (replayed) return replayed
    if (unmarkedInBox(box, product.id) <= 0) return json({ detail: 'unit_may_be_marked' }, 422)
    const code = pool.shift()
    if (!code) return json({ detail: 'marking_pool_empty' }, 422)
    const link: MarkingLink = {
      marking_code_id: `mc-${links.length + 1}`, cis_code: code, product_id: product.id,
      box_id: box.id, container_id: null, storage_location_id: null,
    }
    links.push(link)
    return remember(body.mutation_id, { marking_code_id: link.marking_code_id, cis_code: code })
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
    requests.push({ method, url: url.href, path, body })

    if (url.href === WMS_PRINT_URL && method === 'POST') {
      // WMS Print Direct: квитанция на ключ операции; повтор ключа — та же квитанция.
      prints.push(body ?? {})
      if (printMode === 'reject') throw new TypeError('Failed to fetch')
      if (printMode === 'error') return json({ error: PRINTER_ERROR }, 500)
      const key = typeof body?.idempotencyKey === 'string' ? body.idempotencyKey : ''
      if (!key) return json({ error: 'idempotencyKey required' }, 400)
      const receipt = receipts.get(key) ?? `receipt-${receipts.size + 1}`
      receipts.set(key, receipt)
      return json({ receipt })
    }
    if (url.origin === 'http://wms.test') {
      if (method === 'GET' && path === BASE) return json(detail())
      if (method === 'GET' && path === `${BASE}/pick-options`) return json(pickOptions())
      if (method === 'GET' && path === '/operations/marketplace-unload-requests/available-products') return json([])
      if (method === 'GET' && path === '/operations/wb-mp-warehouses') return json([{ wb_warehouse_id: 1, name: 'Коледино' }])
      if (method === 'GET' && path === '/products/linked-wb-catalog') return json(catalog)
      if (method === 'GET' && path === `/operations/packaging-tasks/by-unload/${SHIPMENT_ID}`) return json(task())
      if (method === 'GET' && path === `/operations/packaging-tasks/${TASK_ID}`) return json(task())
      if (method === 'GET' && path === `${BASE}/marking-codes`) {
        return json(links.map((link) => ({ ...link, intake_document_number: null })))
      }
      const removal = /^\/operations\/marketplace-unload-requests\/mp-686\/marking-codes\/([^/]+)$/.exec(path)
      if (method === 'DELETE' && removal) {
        const index = links.findIndex((link) => link.marking_code_id === removal[1])
        if (index >= 0) links.splice(index, 1)
        return json({ removed: index >= 0 })
      }
      const boxAction = /^\/operations\/marketplace-unload-requests\/mp-686\/boxes\/([^/]+)\/(scan|close|print-marking)$/.exec(path)
      if (method === 'POST' && boxAction) {
        const [, boxId, action] = boxAction
        if (action === 'scan') return boxScan(boxId, body ?? {})
        if (action === 'print-marking') return printMarking(boxId, body ?? {})
        const box = boxes.find((one) => one.id === boxId)
        if (!box) return json({ detail: 'box_not_found' }, 404)
        box.closed = true
        return json(boxOut(box))
      }
      const lineRemoval = /^\/operations\/marketplace-unload-requests\/mp-686\/boxes\/([^/]+)\/lines\/([^/]+)\/remove$/.exec(path)
      if (method === 'POST' && lineRemoval) return removeLine(lineRemoval[1], lineRemoval[2], body ?? {})
      if (method === 'POST' && path === `${BASE}/boxes/attach`) {
        const own = boxes.some((box) => box.barcode === body?.barcode)
        return json({ detail: own ? 'box_already_attached' : 'box_not_found' }, own ? 409 : 422)
      }
    }
    unknown.push(`${method} ${url.origin === 'http://wms.test' ? path : url.href}`)
    return json({ detail: `Неизвестный маршрут подставного сервера: ${method} ${path}` }, 404)
  }

  const posts = (pattern: RegExp) => requests.filter((one) => one.method === 'POST' && pattern.test(one.path))

  return {
    fetch: handle as typeof fetch,
    requests,
    unknown,
    links,
    /** Все обращения к WMS Print (тела заданий) в порядке прихода, включая неудачные. */
    prints,
    packed,
    setPrintMode(mode: PrintMode) {
      printMode = mode
    },
    /** Текст «Упаковано (из подобранного)» сводки документа по состоянию сервера. */
    summaryText: () => `${packedTotal()}/${pickedTotal()}`,
    /** Запросы укладки POST …/boxes/{boxId}/scan в порядке прихода. */
    boxScans: (boxId: string) =>
      requests.filter((one) => one.method === 'POST' && one.path === `${BASE}/boxes/${boxId}/scan`),
    /** Только укладки по ШК товара или по коду (без ШК коробов). */
    productScans: (product: Product | { barcode: string }, boxId?: string) =>
      requests.filter((one) =>
        one.method === 'POST' &&
        (boxId ? one.path === `${BASE}/boxes/${boxId}/scan` : /\/boxes\/[^/]+\/scan$/.test(one.path)) &&
        one.body?.barcode === product.barcode),
    attaches: () => posts(/\/boxes\/attach$/),
    closes: () => posts(/\/boxes\/[^/]+\/close$/),
    printMarkings: () => posts(/\/boxes\/[^/]+\/print-marking$/),
    lineRemovals: () => posts(/\/boxes\/[^/]+\/lines\/[^/]+\/remove$/),
    markingDeletes: () => requests.filter((one) => one.method === 'DELETE' && one.path.startsWith(`${BASE}/marking-codes/`)),
  }
}

type PackServer = ReturnType<typeof createPackServer>

// ─── Внешние границы браузера, которых нет в jsdom ───────────────────────────

const FAKE_PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='

/** Пустой 2D-контекст: любые вызовы рисования принимаются, размеры текста условные. */
function fakeContext2d(canvas: HTMLCanvasElement): CanvasRenderingContext2D {
  const state: Record<string | symbol, unknown> = {
    canvas, fillStyle: '#000', strokeStyle: '#000', font: '10px sans-serif', lineWidth: 1,
    textAlign: 'start', textBaseline: 'alphabetic', globalAlpha: 1, imageSmoothingEnabled: true,
  }
  const imageData = (width: number, height: number) => ({
    width, height, data: new Uint8ClampedArray(Math.max(0, Math.floor(width) * Math.floor(height) * 4)),
  })
  const method = (name: string | symbol): unknown => {
    if (name === 'measureText') {
      return (text: string) => ({
        width: String(text).length * 6, actualBoundingBoxAscent: 8, actualBoundingBoxDescent: 2,
        actualBoundingBoxLeft: 0, actualBoundingBoxRight: String(text).length * 6,
        fontBoundingBoxAscent: 8, fontBoundingBoxDescent: 2,
      })
    }
    if (name === 'getImageData') return (_x: number, _y: number, width: number, height: number) => imageData(width, height)
    if (name === 'createImageData') return (width: number, height: number) => imageData(width, height)
    if (name === 'getLineDash') return () => []
    if (name === 'isPointInPath' || name === 'isPointInStroke') return () => false
    if (name === 'createLinearGradient' || name === 'createRadialGradient' || name === 'createConicGradient') {
      return () => ({ addColorStop: () => undefined })
    }
    if (name === 'createPattern') return () => null
    if (name === 'getTransform') return () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 })
    return () => undefined
  }
  return new Proxy(state, {
    get: (target, name) => (name in target ? target[name] : method(name)),
    set: (target, name, value) => {
      target[name] = value
      return true
    },
  }) as unknown as CanvasRenderingContext2D
}

/** Картинка «загружается» сразу: настоящий <img>, onload — в следующей задаче. */
function instantImage(width?: number, height?: number): HTMLImageElement {
  const image = document.createElement('img')
  if (width !== undefined) image.width = width
  if (height !== undefined) image.height = height
  Object.defineProperty(image, 'src', {
    configurable: true,
    get: () => image.getAttribute('src') ?? '',
    set: (value: string) => {
      image.setAttribute('src', value)
      setTimeout(() => image.dispatchEvent(new Event('load')), 0)
    },
  })
  Object.defineProperty(image, 'complete', { configurable: true, get: () => true })
  Object.defineProperty(image, 'naturalWidth', { configurable: true, get: () => width ?? 200 })
  Object.defineProperty(image, 'naturalHeight', { configurable: true, get: () => height ?? 100 })
  image.decode = () => Promise.resolve()
  return image
}

function installBrowserBoundary() {
  const contexts = new WeakMap<HTMLCanvasElement, CanvasRenderingContext2D>()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (this: HTMLCanvasElement) {
    let context = contexts.get(this)
    if (!context) {
      context = fakeContext2d(this)
      contexts.set(this, context)
    }
    return context
  })
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockImplementation(() => FAKE_PNG)
  vi.stubGlobal('Image', function Image(width?: number, height?: number) {
    return instantImage(width, height)
  })
}

// ─── Рендер, сканер, ожидания ────────────────────────────────────────────────

const originalFetch = globalThis.fetch
const originalScrollIntoView = Element.prototype.scrollIntoView
let host: HTMLDivElement
let root: Root

beforeEach(() => {
  try {
    window.localStorage.clear()
    window.sessionStorage.clear()
  } catch {
    // Хранилище браузера — не часть контракта.
  }
  installBrowserBoundary()
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
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  try {
    window.localStorage.clear()
    window.sessionStorage.clear()
  } catch {
    // Хранилище браузера — не часть контракта.
  }
})

async function settle(ms = 20) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms))
  })
}

/** Ждёт состояние, которое экран показывает после асинхронного действия; иначе — последняя ошибка проверки. */
async function waitFor(assertion: () => void, timeoutMs = 2000) {
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
  if (key === '-') return 'Minus'
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

async function click(element: HTMLElement) {
  await act(async () => element.click())
}

const byTestId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`)
const packagingPanel = () => byTestId('ff-mp-tab-packaging-panel')
const scanBar = () => byTestId('fbo-pack-scan')
const packedSummary = () => byTestId('ff-mp-shipment-summary-packed')?.textContent ?? ''
const kizRows = () => [...(packagingPanel()?.querySelectorAll<HTMLElement>('[data-testid="fbo-pack-kiz-row"]') ?? [])]
const menuItems = () => [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')]

function textOf(node: Element | null | undefined) {
  return (node?.textContent ?? '').replace(/\s+/g, ' ').trim()
}

/** Кнопка с этим текстом внутри узла (раздел 9 п.8: «Повторить печать», «Закрыть короб»). */
function buttonIn(scope: HTMLElement | null, text: string): HTMLButtonElement | null {
  if (!scope) return null
  return [...scope.querySelectorAll<HTMLButtonElement>('button')].find((button) => textOf(button).includes(text)) ?? null
}

const summary: FfMarketplaceUnloadSummary = {
  id: SHIPMENT_ID,
  document_number: '000686',
  display_number: '000686',
  warehouse_id: 'wh-686',
  warehouse_name: 'Склад ФФ',
  status: 'collecting',
  line_count: PRODUCTS.length,
  seller_id: SELLER.id,
  seller_name: SELLER.name,
  marketplace: 'wb',
  planned_shipment_date: '2026-10-09',
  created_at: '2026-10-06T12:00:00Z',
}

/** Открывает документ отгрузки на вкладке «Упаковка» и ждёт задание на упаковку. */
async function openPackaging(server: PackServer) {
  globalThis.fetch = server.fetch
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/app/ff/mp-shipments']}>
        <FfSuppliesShipmentsPage
          pageVariant="mp-shipments"
          busy={false}
          error={null}
          infoNotice={null}
          onDismissInfoNotice={() => undefined}
          token={TOKEN}
          sellers={[SELLER]}
          productPicklist={[]}
          onRefreshFfSupplyExtras={async () => undefined}
          inboundSummaries={[]}
          outboundSummaries={[]}
          marketplaceUnloadSummaries={[summary]}
          discrepancyActSummaries={[]}
          onOpenInbound={() => undefined}
          onOpenOutbound={() => undefined}
          onCreateMpShipment={async () => null}
          onCreateDiverge={async () => null}
          initialMarketplaceUnloadId={SHIPMENT_ID}
          addressStorageEnabled
        />
      </MemoryRouter>,
    )
  })
  await waitFor(() => {
    const tab = byTestId('ff-mp-tab-packaging') as HTMLButtonElement | null
    expect(tab, 'вкладка «Упаковка» документа').not.toBeNull()
    expect(tab!.disabled, 'вкладка «Упаковка» доступна').toBe(false)
  }, 5000)
  await click(byTestId('ff-mp-tab-packaging')!)
  await waitFor(() => expect(packagingPanel(), 'открыта вкладка «Упаковка»').not.toBeNull())
  await waitFor(() => expect(byTestId('ff-packaging-task-panel'), 'задание на упаковку загружено').not.toBeNull())
  await waitFor(() => expect(packedSummary()).toBe(server.summaryText()))
  await settle(50)
}

/** Галка по её подписи: обёртка <label>, связанная подпись или aria-label. */
function checkbox(name: string): HTMLInputElement | null {
  const scope = packagingPanel()
  if (!scope) return null
  for (const input of scope.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')) {
    const labelled = (input.getAttribute('aria-labelledby') ?? '')
      .split(/\s+/)
      .filter(Boolean)
      .map((id) => textOf(document.getElementById(id)))
      .join(' ')
    const names = [
      input.getAttribute('aria-label') ?? '',
      textOf(input.closest('label')),
      ...[...(input.labels ?? [])].map((label) => textOf(label)),
      labelled,
    ]
    if (names.some((one) => one.startsWith(name))) return input
  }
  return null
}

/**
 * «+» количества экземпляров у галки (R12: «Печатать ЧЗ − N +», «Перепечатывать
 * ЧЗ − N +»): первая кнопка с именем «…больше»/«увеличить»/«+» после этой галки
 * и до следующей галки панели.
 */
function copiesPlusAfter(name: string): HTMLButtonElement | null {
  const scope = packagingPanel()
  const anchor = checkbox(name)
  if (!scope || !anchor) return null
  const controls = [...scope.querySelectorAll<HTMLElement>('input[type="checkbox"], button')]
  for (const element of controls.slice(controls.indexOf(anchor) + 1)) {
    if (element instanceof HTMLInputElement) break
    const label = `${element.getAttribute('aria-label') ?? ''} ${element.getAttribute('title') ?? ''} ${textOf(element)}`
    if (/больше|увелич|(^|\s)\+(\s|$)/i.test(label)) return element as HTMLButtonElement
  }
  return null
}

/** Ставит галку печати в нужное положение, если такая галка есть на экране. */
async function setPrintToggle(name: string, checked: boolean) {
  const input = checkbox(name)
  if (!input || input.checked === checked) return
  await click(input)
  await waitFor(() => expect(checkbox(name)?.checked, `галка «${name}»`).toBe(checked))
}

/** Печать при скане выключена — ни одна галка не добавляет заданий WMS Print. */
async function turnScanPrintingOff() {
  await setPrintToggle('Печатать ЧЗ', false)
  await setPrintToggle('Перепечатывать ЧЗ', false)
  await setPrintToggle('Печатать ШК', false)
}

/** Строки товаров таблицы упаковки в порядке документа. */
function productRows(): HTMLElement[] {
  return PRODUCTS
    .map((product) => byTestId(`ff-packaging-line-barcode-${product.lineId}`)?.closest('tr') ?? null)
    .filter((row): row is HTMLTableRowElement => row !== null)
    .sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1))
}

/** Строка КИЗ — во вложенности своего товара: после его строки и до строки следующего. */
function expectUnderProduct(kizRow: HTMLElement, product: Product) {
  const own = byTestId(`ff-packaging-line-barcode-${product.lineId}`)?.closest('tr') ?? null
  expect(own, `строка товара ${product.sku} в таблице упаковки`).not.toBeNull()
  expect(own!.compareDocumentPosition(kizRow) & Node.DOCUMENT_POSITION_FOLLOWING, `строка КИЗ под товаром ${product.sku}`)
    .toBeTruthy()
  const rows = productRows()
  const next = rows[rows.indexOf(own as HTMLElement) + 1]
  if (next) {
    expect(kizRow.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING, `строка КИЗ стоит до следующего товара`)
      .toBeTruthy()
  }
}

/** Ошибка WMS Print видна в поле скана: сообщение принтера/программы или блок ошибки. */
function expectPrintFailureShown(hint: string) {
  const bar = scanBar()
  expect(bar, 'поле скана упаковки').not.toBeNull()
  const shown = textOf(bar).includes(hint) || bar!.querySelector('[role="alert"]') !== null
  expect(shown, `ошибка печати показана в поле скана (${hint})`).toBe(true)
}

function expectNoUnknownRoutes(server: PackServer) {
  expect(server.unknown, 'обращения к маршрутам вне контракта получили 404 подставного сервера').toEqual([])
}

describe('WMS-686 · «Упаковка» FBO: поле скана, КИЗ под товаром, печать через WMS Print', () => {
  it('c18 C18/R12: на «Упаковке» FBO есть поле скана и галки «Печатать ШК», «Печатать ЧЗ», «Перепечатывать ЧЗ», без «Печатать QR»', async () => {
    const server = createPackServer({ boxes: [BOX_B1] })
    await openPackaging(server)

    const bar = scanBar()
    expect(bar, 'на вкладке «Упаковка» FBO есть поле скана [data-testid="fbo-pack-scan"]').not.toBeNull()
    expect(
      bar!.querySelector('input:not([type="checkbox"]):not([type="hidden"]), textarea'),
      'внутри fbo-pack-scan — поле ввода скана',
    ).not.toBeNull()
    expect(checkbox('Печатать ШК'), 'галка «Печатать ШК»').not.toBeNull()
    expect(checkbox('Печатать ЧЗ'), 'галка «Печатать ЧЗ»').not.toBeNull()
    expect(checkbox('Перепечатывать ЧЗ'), 'галка «Перепечатывать ЧЗ»').not.toBeNull()
    expect(checkbox('Печатать QR'), 'галки «Печатать QR» нет').toBeNull()
    expect(document.body.textContent ?? '', 'текста «Печатать QR» нет').not.toContain('Печатать QR')
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c21 C21/R13/R14: короб B1 — ШК → укладка в B1 без снятия со склада и +1; КИЗ → новая строка под товаром; второй ШК+КИЗ → вторая строка', async () => {
    const server = createPackServer({ boxes: [BOX_B1] })
    await openPackaging(server)
    await turnScanPrintingOff()

    scan(PRODUCT_A.barcode)
    await waitFor(() =>
      expect(server.boxScans(BOX_B1.id), 'ШК товара на «Упаковке» уходит в POST …/boxes/B1/scan').toHaveLength(1))
    const first = server.boxScans(BOX_B1.id)[0]
    expect(first.body?.barcode).toBe(PRODUCT_A.barcode)
    expect(first.body?.pick_from_storage, 'укладка только подобранного: pick_from_storage=false').toBe(false)
    await waitFor(() => expect(packedSummary(), '«Упаковано» в сводке +1').toBe('1/6'))

    scan(KIZ_1)
    await waitFor(() => expect(server.boxScans(BOX_B1.id), 'КИЗ уходит в тот же короб B1').toHaveLength(2))
    expect(server.boxScans(BOX_B1.id)[1].body?.barcode).toBe(KIZ_1)
    expect(server.boxScans(BOX_B1.id)[1].body?.product_id, 'КИЗ после ШК — контекст единицы: product_id товара этого ШК (D16)')
      .toBe(PRODUCT_A.id)
    await waitFor(() => expect(kizRows(), 'под товаром появилась строка КИЗ').toHaveLength(1))
    expect(kizRows()[0].dataset.kizState, 'строка КИЗ подсвечена как новая').toBe('new')
    expectUnderProduct(kizRows()[0], PRODUCT_A)
    await settle(50)
    expect(packedSummary(), 'КИЗ не добавляет единицу').toBe('1/6')

    scan(PRODUCT_A.barcode)
    await waitFor(() => expect(server.boxScans(BOX_B1.id)).toHaveLength(3))
    expect(server.boxScans(BOX_B1.id)[2].body?.barcode).toBe(PRODUCT_A.barcode)
    expect(server.boxScans(BOX_B1.id)[2].body?.pick_from_storage).toBe(false)
    await waitFor(() => expect(packedSummary()).toBe('2/6'))

    scan(KIZ_2)
    await waitFor(() => expect(server.boxScans(BOX_B1.id)).toHaveLength(4))
    expect(server.boxScans(BOX_B1.id)[3].body?.barcode).toBe(KIZ_2)
    expect(server.boxScans(BOX_B1.id)[3].body?.product_id).toBe(PRODUCT_A.id)
    await waitFor(() => expect(kizRows(), 'второй КИЗ — второй строкой').toHaveLength(2))
    const rows = kizRows()
    expect(rows[rows.length - 1].dataset.kizState, 'последняя строка КИЗ — новая').toBe('new')
    rows.forEach((row) => expectUnderProduct(row, PRODUCT_A))
    expect(server.links.map((link) => link.box_id)).toEqual([BOX_B1.id, BOX_B1.id])
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c22 C22/R15: скан ШК короба этой отгрузки делает его текущим — следующий ШК уходит в него, присоединения нет', async () => {
    const server = createPackServer({ boxes: [BOX_B1, BOX_B2] })
    await openPackaging(server)
    await turnScanPrintingOff()

    scan(BOX_B1.barcode)
    await settle(100)
    scan(PRODUCT_A.barcode)
    await waitFor(() =>
      expect(server.productScans(PRODUCT_A, BOX_B1.id), 'после скана короба B1 ШК товара уложен в B1').toHaveLength(1))

    scan(BOX_B2.barcode)
    await settle(100)
    scan(PRODUCT_A.barcode)
    await waitFor(() =>
      expect(server.productScans(PRODUCT_A, BOX_B2.id), 'после скана короба B2 ШК товара уходит в POST …/boxes/B2/scan').toHaveLength(1))
    expect(server.productScans(PRODUCT_A, BOX_B1.id), 'в B1 второй единицы нет').toHaveLength(1)
    expect(server.productScans(PRODUCT_A, BOX_B2.id)[0].body?.pick_from_storage).toBe(false)
    expect(server.attaches(), 'короба этой отгрузки не присоединяются заново').toHaveLength(0)
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c23 C23/R16: «Печатать ШК» — одно задание WMS Print на единицу с уникальным ключом; галка снята — печати нет', async () => {
    const server = createPackServer({ boxes: [BOX_B1] })
    await openPackaging(server)
    await setPrintToggle('Печатать ЧЗ', false)
    await setPrintToggle('Перепечатывать ЧЗ', false)

    expect(checkbox('Печатать ШК'), 'галка «Печатать ШК» на «Упаковке» FBO').not.toBeNull()
    await setPrintToggle('Печатать ШК', true)

    scan(PRODUCT_A.barcode)
    await waitFor(() => expect(server.productScans(PRODUCT_A, BOX_B1.id)).toHaveLength(1))
    await waitFor(() => expect(server.prints, 'ШК товара напечатан через WMS Print').toHaveLength(1))
    scan(PRODUCT_A.barcode)
    await waitFor(() => expect(server.productScans(PRODUCT_A, BOX_B1.id)).toHaveLength(2))
    await waitFor(() => expect(server.prints, 'вторая единица — второе задание WMS Print').toHaveLength(2))

    const keys = server.prints.map((one) => one.idempotencyKey)
    for (const key of keys) expect(typeof key === 'string' && key.length > 0, 'задание несёт idempotencyKey').toBe(true)
    expect(new Set(keys).size, 'у каждой единицы свой ключ').toBe(2)
    const printRequests = server.requests.filter((one) => one.url === WMS_PRINT_URL)
    expect(printRequests.every((one) => one.method === 'POST')).toBe(true)

    await setPrintToggle('Печатать ШК', false)
    scan(PRODUCT_A.barcode)
    await waitFor(() => expect(server.productScans(PRODUCT_A, BOX_B1.id)).toHaveLength(3))
    await settle(300)
    expect(server.prints, 'после снятия галки ШК не печатается').toHaveLength(2)
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c39 C39/R28: в «Сборке» у строки товара закрытого короба «Убрать» — пункты «КИЗ … (источник известен)», «КИЗ … — источник неизвестен» с выбором места, «Без КИЗ»; запросы …/lines/{line}/remove с marking_code_id, для кода без источника — с return_to', async () => {
    // В закрытом B1 три единицы A: с КИЗ из подбора (источник K1), с КИЗ, впервые
    // отсканированным на упаковке (источник неизвестен), и без КИЗ. A подбиралась из K1 и K2.
    const server = createPackServer({
      boxes: [{ ...BOX_B1, closed: true, units: { [PRODUCT_A.id]: 3 } }],
      sources: [
        { productId: PRODUCT_A.id, container: SOURCE_K1, picked: 1 },
        { productId: PRODUCT_A.id, container: SOURCE_K2, picked: 2 },
        { productId: PRODUCT_B.id, container: null, picked: 2 },
      ],
      links: [
        {
          marking_code_id: 'mc-source-known', cis_code: KIZ_SOURCE_KNOWN, product_id: PRODUCT_A.id,
          box_id: BOX_B1.id, container_id: SOURCE_K1.id, storage_location_id: CELL.id,
        },
        {
          marking_code_id: 'mc-source-unknown', cis_code: KIZ_SOURCE_UNKNOWN, product_id: PRODUCT_A.id,
          box_id: BOX_B1.id, container_id: null, storage_location_id: null,
        },
      ],
    })
    await openPackaging(server)
    const lineId = `${BOX_B1.id}-${PRODUCT_A.id}`
    const removeButton = () => byTestId(`fbo-box-line-remove-${lineId}`)
    const itemWith = (...parts: string[]) => menuItems().find((item) => parts.every((part) => textOf(item).includes(part)))

    // Существующий блок «Короба» — раскрываем, как оператор.
    const boxesSummary = byTestId('ff-mp-boxes-summary')
    if (boxesSummary) await click(boxesSummary)
    await waitFor(() => expect(removeButton(), '«Убрать» у строки товара в карточке закрытого короба').not.toBeNull())
    await click(removeButton()!)

    await waitFor(() => expect(menuItems().length, 'пункты выбора единицы').toBeGreaterThanOrEqual(3))
    const knownItem = itemWith(KIZ_SOURCE_KNOWN.slice(-6))
    expect(knownItem, 'пункт с кодом из подбора').toBeDefined()
    expect(textOf(knownItem), 'место возврата кода из подбора — его источник K1').toContain(SOURCE_K1.code)
    expect(textOf(knownItem)).toContain('источник известен')
    const unknownItem = itemWith(KIZ_SOURCE_UNKNOWN.slice(-6))
    expect(unknownItem, 'пункт с кодом, впервые отсканированным на упаковке').toBeDefined()
    expect(textOf(unknownItem)).toContain('источник неизвестен')
    const plainItem = itemWith('Без КИЗ')
    expect(plainItem, 'пункт «Без КИЗ»').toBeDefined()
    expect(textOf(plainItem), 'у «Без КИЗ» предложено место — последний источник без КИЗ (K2)').toContain(SOURCE_K2.code)

    // Код без источника: выбор места из источников подбора этого товара, затем запрос с return_to.
    await click(unknownItem!)
    await waitFor(() =>
      expect(
        menuItems().find((item) => textOf(item).includes(SOURCE_K2.code) && !textOf(item).includes('Без КИЗ')),
        'для кода без источника — выбор места (короб K2 среди источников подбора)',
      ).toBeDefined())
    await click(menuItems().find((item) => textOf(item).includes(SOURCE_K2.code) && !textOf(item).includes('Без КИЗ'))!)
    await waitFor(() => expect(server.lineRemovals(), 'выбор места отправляет …/lines/{line}/remove').toHaveLength(1))
    const unknownRemoval = server.lineRemovals()[0]
    expect(unknownRemoval.path).toBe(`${BASE}/boxes/${BOX_B1.id}/lines/${lineId}/remove`)
    expect(unknownRemoval.body?.marking_code_id, 'запрос несёт marking_code_id выбранного кода').toBe('mc-source-unknown')
    const returnTo = unknownRemoval.body?.return_to as { container_id?: unknown } | undefined
    expect(returnTo, 'для кода без известного источника запрос несёт return_to').toBeDefined()
    expect(returnTo?.container_id, 'return_to — выбранный короб K2').toBe(SOURCE_K2.id)

    // Код из подбора: место известно, запрос с его marking_code_id.
    await waitFor(() => expect(removeButton(), '«Убрать» доступно снова').not.toBeNull())
    await click(removeButton()!)
    await waitFor(() => expect(itemWith(KIZ_SOURCE_KNOWN.slice(-6)), 'пункт кода из подбора').toBeDefined())
    await click(itemWith(KIZ_SOURCE_KNOWN.slice(-6))!)
    await waitFor(() => expect(server.lineRemovals()).toHaveLength(2))
    expect(server.lineRemovals()[1].body?.marking_code_id, 'запрос несёт marking_code_id кода из подбора').toBe('mc-source-known')
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c44 C44/R16б,в,г: «Печатать ЧЗ» ×2 — код из пула и задания k, k:c2, строка КИЗ новая; «Перепечатывать ЧЗ» ×2 — два задания на скан КИЗ без запроса в пул', async () => {
    const server = createPackServer({ boxes: [BOX_B1], pool: [POOL_1, POOL_2] })
    await openPackaging(server)
    await setPrintToggle('Печатать ШК', false)
    await setPrintToggle('Перепечатывать ЧЗ', false)

    expect(checkbox('Печатать ЧЗ'), 'галка «Печатать ЧЗ» на «Упаковке» FBO').not.toBeNull()
    await setPrintToggle('Печатать ЧЗ', true)
    const plusPrint = copiesPlusAfter('Печатать ЧЗ')
    expect(plusPrint, '«+» количества экземпляров у «Печатать ЧЗ»').not.toBeNull()
    await click(plusPrint!)

    scan(PRODUCT_A.barcode)
    await waitFor(() => expect(server.productScans(PRODUCT_A, BOX_B1.id), 'ШК уложен в B1').toHaveLength(1))
    expect(server.productScans(PRODUCT_A, BOX_B1.id)[0].body?.pick_from_storage).toBe(false)
    await waitFor(() =>
      expect(server.printMarkings(), 'код из пула запрошен: POST …/boxes/B1/print-marking').toHaveLength(1))
    const poolRequest = server.printMarkings()[0]
    expect(poolRequest.path).toBe(`${BASE}/boxes/${BOX_B1.id}/print-marking`)
    expect(poolRequest.body?.product_id).toBe(PRODUCT_A.id)
    expect(typeof poolRequest.body?.mutation_id, 'запрос в пул несёт mutation_id').toBe('string')
    await waitFor(() => expect(server.prints, 'два экземпляра ЧЗ — два задания WMS Print').toHaveLength(2))
    const [firstKey, copyKey] = server.prints.map((one) => one.idempotencyKey)
    expect(typeof firstKey === 'string' && firstKey.length > 0, 'задание несёт idempotencyKey').toBe(true)
    expect(copyKey, 'ключ второго экземпляра — k:c2').toBe(`${String(firstKey)}:c2`)
    await waitFor(() => expect(kizRows(), 'напечатанный код — строкой КИЗ под товаром').toHaveLength(1))
    expect(kizRows()[0].dataset.kizState).toBe('new')
    expectUnderProduct(kizRows()[0], PRODUCT_A)

    // «Перепечатывать ЧЗ» ×2: скан существующего КИЗ печатает этот код, пул не трогается.
    await setPrintToggle('Печатать ЧЗ', false)
    await setPrintToggle('Перепечатывать ЧЗ', true)
    const plusReprint = copiesPlusAfter('Перепечатывать ЧЗ')
    expect(plusReprint, '«+» количества экземпляров у «Перепечатывать ЧЗ»').not.toBeNull()
    await click(plusReprint!)
    scan(PRODUCT_A.barcode)
    await waitFor(() => expect(server.productScans(PRODUCT_A, BOX_B1.id)).toHaveLength(2))
    await settle(150)
    expect(server.prints, 'ШК без «Печатать ЧЗ» ничего не печатает').toHaveLength(2)
    scan(KIZ_1)
    await waitFor(() => expect(server.productScans({ barcode: KIZ_1 }, BOX_B1.id), 'КИЗ уходит в B1').toHaveLength(1))
    await waitFor(() => expect(server.prints, 'перепечать ×2 — ещё два задания WMS Print').toHaveLength(4))
    const reprintKeys = server.prints.slice(2).map((one) => one.idempotencyKey)
    expect(new Set([...server.prints.map((one) => one.idempotencyKey)]).size, 'у каждого задания свой ключ').toBe(4)
    expect(reprintKeys.every((key) => typeof key === 'string' && key.length > 0)).toBe(true)
    expect(server.printMarkings(), 'перепечать не берёт код из пула').toHaveLength(1)
    expectNoUnknownRoutes(server)
  }, 20_000)

  for (const failure of [
    { mode: 'error' as const, title: 'WMS Print отвечает ошибкой', hint: PRINTER_ERROR },
    { mode: 'reject' as const, title: 'обрыв ответа WMS Print', hint: 'WMS Print' },
  ]) {
    it(`c45 C45/R16г/R31 (${failure.title}): ошибка в поле скана, укладка не откатывается, «Повторить печать» — тот же idempotencyKey; после снятия галки повтора нет`, async () => {
      const server = createPackServer({ boxes: [BOX_B1] })
      server.setPrintMode(failure.mode)
      await openPackaging(server)
      await setPrintToggle('Печатать ЧЗ', false)
      await setPrintToggle('Перепечатывать ЧЗ', false)

      expect(checkbox('Печатать ШК'), 'галка «Печатать ШК» на «Упаковке» FBO').not.toBeNull()
      await setPrintToggle('Печатать ШК', true)

      scan(PRODUCT_A.barcode)
      await waitFor(() => expect(server.productScans(PRODUCT_A, BOX_B1.id)).toHaveLength(1))
      await waitFor(() => expect(server.prints, 'задание отправлено в WMS Print').toHaveLength(1))
      const key = server.prints[0].idempotencyKey
      expect(typeof key === 'string' && key.length > 0, 'задание несёт idempotencyKey').toBe(true)
      await waitFor(() => expect(buttonIn(scanBar(), 'Повторить печать'), '«Повторить печать» в поле скана').not.toBeNull())
      expectPrintFailureShown(failure.hint)
      await waitFor(() => expect(packedSummary(), 'единица осталась упакованной').toBe('1/6'))
      expect(server.packed(PRODUCT_A.id)).toBe(1)

      await click(buttonIn(scanBar(), 'Повторить печать')!)
      await waitFor(() => expect(server.prints, '«Повторить печать» отправляет задание снова').toHaveLength(2))
      expect(server.prints[1].idempotencyKey, 'повтор — с тем же idempotencyKey').toBe(key)
      await waitFor(() => expect(buttonIn(scanBar(), 'Повторить печать'), 'после повторной ошибки повтор доступен').not.toBeNull())

      await setPrintToggle('Печатать ШК', false)
      const retry = buttonIn(scanBar(), 'Повторить печать')
      if (retry) await click(retry)
      await settle(300)
      expect(server.prints, 'после снятия галки повтор не отправляет задание').toHaveLength(2)
      expect(packedSummary(), 'укладка не откатилась').toBe('1/6')
      expect(server.lineRemovals(), 'единица не убиралась из короба').toHaveLength(0)
      expectNoUnknownRoutes(server)
    }, 20_000)
  }

  it('c48 C48/R32: «Закрыть короб» в поле скана — POST …/boxes/B1/close, следующий ШК уходит в B2; скан ШК B1 — следующий ШК снова в B1', async () => {
    const server = createPackServer({ boxes: [BOX_B1, BOX_B2] })
    await openPackaging(server)
    await turnScanPrintingOff()

    // Текущий короб — B1 (выбран сканом его ШК).
    scan(BOX_B1.barcode)
    await settle(100)
    const close = buttonIn(scanBar(), 'Закрыть короб')
    expect(close, '«Закрыть короб» в поле скана упаковки').not.toBeNull()
    await click(close!)
    await waitFor(() => expect(server.closes(), 'отправлен POST …/boxes/B1/close').toHaveLength(1))
    expect(server.closes()[0].path).toBe(`${BASE}/boxes/${BOX_B1.id}/close`)
    await settle(100)

    scan(PRODUCT_A.barcode)
    await waitFor(() =>
      expect(server.productScans(PRODUCT_A, BOX_B2.id), 'после закрытия B1 текущий — B2: ШК уходит в B2').toHaveLength(1))
    expect(server.productScans(PRODUCT_A, BOX_B1.id)).toHaveLength(0)

    scan(BOX_B1.barcode)
    await settle(100)
    scan(PRODUCT_A.barcode)
    await waitFor(() =>
      expect(server.productScans(PRODUCT_A, BOX_B1.id), 'закрытый B1 снова текущий сканом его ШК и принимает товар').toHaveLength(1))
    expect(server.productScans(PRODUCT_A, BOX_B2.id)).toHaveLength(1)
    expect(server.attaches(), 'короба этой отгрузки не присоединяются заново').toHaveLength(0)
    expectNoUnknownRoutes(server)
  }, 20_000)

  it('c54 C54/R6б/R14/D16 (упаковка): скан ШК короба B1 → КИЗ без ШК — укладка кода в B1 без product_id, строка КИЗ под товаром, «Упаковано» прежнее; неизвестный GTIN — «Сначала отсканируйте ШК товара»', async () => {
    // В B1 уже уложена одна A без КИЗ.
    const server = createPackServer({ boxes: [{ ...BOX_B1, units: { [PRODUCT_A.id]: 1 } }] })
    await openPackaging(server)
    await turnScanPrintingOff()
    expect(packedSummary()).toBe('1/6')

    scan(BOX_B1.barcode)
    await settle(100)
    scan(KIZ_2)
    await waitFor(() =>
      expect(server.productScans({ barcode: KIZ_2 }, BOX_B1.id), 'КИЗ после скана ШК короба уходит в POST …/boxes/B1/scan').toHaveLength(1))
    const kizScan = server.productScans({ barcode: KIZ_2 }, BOX_B1.id)[0]
    expect(kizScan.body?.product_id ?? null, 'после скана короба КИЗ уходит без product_id (контекст проверки)').toBeNull()
    await waitFor(() => expect(kizRows(), 'код привязан к уже уложенной единице — строка КИЗ').toHaveLength(1))
    expect(kizRows()[0].dataset.kizState).toBe('new')
    expectUnderProduct(kizRows()[0], PRODUCT_A)
    expect(server.links.map((link) => link.box_id)).toEqual([BOX_B1.id])
    await settle(50)
    expect(packedSummary(), 'КИЗ не добавляет единицу').toBe('1/6')

    scan(KIZ_UNKNOWN_GTIN)
    await waitFor(() =>
      expect(textOf(scanBar()), 'код с неизвестным GTIN в контексте проверки').toContain('Сначала отсканируйте ШК товара'))
    expect(server.links, 'неизвестный код не привязан').toHaveLength(1)
    expect(packedSummary()).toBe('1/6')
    expectNoUnknownRoutes(server)
  }, 20_000)
})
