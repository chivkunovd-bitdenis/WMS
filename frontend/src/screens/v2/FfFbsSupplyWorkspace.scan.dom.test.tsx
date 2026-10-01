// @vitest-environment jsdom
import { webcrypto } from 'node:crypto'
import { directQrHash, type DurableQrAttempt } from '../../utils/durableDirectQr'
import { fbsPendingProductScanStorageKey, readPendingAttempts } from './fbsScanAutoPrint'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('./fbsPackingScanLocks', () => ({ packingScanLocks: () => { if (durable.noLocks) throw new Error('no navigator.locks'); return { owner: async () => 'test-owner', active: async () => false, run: async (_scope: string, action: () => Promise<unknown>) => action() } } }))
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'

const durable = vi.hoisted(() => ({ noLocks: false, rows: new Map<string, DurableQrAttempt>(), chz: vi.fn(async () => undefined) }))
vi.mock('../../utils/durableDirectQr', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../utils/durableDirectQr')>()
  const store = { get: async (key: string) => structuredClone(durable.rows.get(key)),
    put: async (attempt: DurableQrAttempt) => { durable.rows.set(attempt.input.idempotencyKey, structuredClone(attempt)) } }
  return { ...actual,
    prepareDurableQr: (input: Parameters<typeof actual.prepareDurableQr>[0]) => actual.prepareDurableQr(input, store),
    restoreDurableQr: (key: string, context: Parameters<typeof actual.restoreDurableQr>[1]) => actual.restoreDurableQr(key, context, store),
    dispatchDurableQr: (input: Parameters<typeof actual.dispatchDurableQr>[0], _store?: unknown, _io?: unknown, existing = false) => actual.dispatchDurableQr(input, store, undefined, existing),
  }
})
vi.mock('../../utils/printMarkingCodeLabel', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../utils/printMarkingCodeLabel')>(), printMarkingCodeTape: durable.chz,
}))

// Only the actual workspace and scanner participate in these tests.
vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
vi.mock('../../utils/useMarkingCodePrint', () => ({ useMarkingCodePrint: () => ({ openPrint: vi.fn(), dialog: null }) }))
vi.mock('./FbsSupplyHistoryDialog', () => ({ FbsSupplyHistoryDialog: () => null }))
vi.mock('./FbsPrintPreviewDialog', () => ({ FbsPrintPreviewDialog: () => null }))
vi.mock('./FbsTransferSupplyDialog', () => ({ FbsTransferSupplyDialog: () => null, makeFbsTransferSupplyDeps: () => ({}) }))

// WMS-575 · «Упаковка и маркировка»: скан принимает вся вкладка, где бы ни
// стоял курсор, коды подряд не теряются, отметка ЧЗ — по ответу commit.
// Рендерится настоящая карточка поставки; сервер подменён только через fetch,
// сканер — события keydown в тот элемент, где сейчас фокус.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  // jsdom не прокручивает; карточка подкручивает список к ожившей строке.
  Element.prototype.scrollIntoView = () => undefined
})

const SUPPLY_ID = 'sup-575'
const STICKER_A = '*CDhjtA1111'
const STICKER_B = '*CDhjtB2222'
const KIZ_A = '0104600000000017215AbCdEfGh1234'

function order(id: string, wbOrderId: number, index: number, tail: string | null) {
  return {
    id,
    marketplace: 'wb',
    external_order_id: null,
    wb_order_id: wbOrderId,
    status: 'assembling',
    wb_status: 'confirm',
    supplier_status: 'confirm',
    seller: { id: 'seller-1', name: 'ИП Тестовый' },
    wb_warehouse: { id: 507, name: 'Коледино' },
    wms_warehouse: { id: 'wh-1', name: 'Основной склад' },
    product: {
      id: 'prod-1', name: `Футболка ${index + 1}`, image_url: null, seller_article: 'TS-01',
      wb_article: 1001, barcode: '4600000000017', sku: 'TS-01', chrt_id: 1, category: 'Футболки',
      color: null, size: null,
    },
    positions: [],
    inventory: { available_unpacked: 5, locations: [] },
    buyer_type: 'individual',
    cargo_type: 'mgt',
    can_pvz: false,
    metadata: {
      required: ['sgtin'],
      optional: [],
      states: [tail
        ? { id: `mark-${id}`, kind: 'sgtin', status: 'pending', reason: null, source: 'operator', value_tail: tail }
        : { kind: 'sgtin', status: 'missing', reason: null, source: null, value_tail: null }],
      delivery_allowed: false,
      last_checked_at: null,
    },
    sticker: { code: `${wbOrderId} 000${index}`, status: 'print_opened', asset_url: null, applied_at: null },
    pick: { status: 'picked', location_code: 'А-01-01', picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: new Date().toISOString(),
    deadline_at: new Date(Date.now() + 86_400_000).toISOString(),
    supply_id: SUPPLY_ID,
    selection_blockers: [],
    tape_order_index: index,
  }
}

function workspace(tails: Record<string, string | null> = {}): FbsWorkspace {
  return {
    supply: {
      id: SUPPLY_ID, marketplace: 'wb', wb_supply_id: 'WB-GI-575', source: 'wms', name: 'Поставка 000575',
      status: 'assembling', delivery_type: 'warehouse_sc', seller: { id: 'seller-1', name: 'ИП Тестовый' },
      wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'wh-1', name: 'Основной склад' },
      planned_destination: null, planned_shipment_date: null,
      nearest_deadline_at: new Date(Date.now() + 86_400_000).toISOString(), packaging_task_id: 'pt-575',
      barcode_asset: null,
    },
    stage: 'packing',
    progress: { picked: 2, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 2 },
    blockers: [],
    orders: [order('order-a', 5001, 0, tails['order-a'] ?? null), order('order-b', 5002, 1, tails['order-b'] ?? null)],
    cargo_places: [],
    boxes: [],
    delivery_preflight: null,
    last_wb_sync_at: null,
    server_now: new Date().toISOString(),
  } as unknown as FbsWorkspace
}

const packagingTask = {
  id: 'pt-575', document_number: '000575', display_number: '000575', status: 'in_progress', lines: [{
    id: 'ptl-1', product_id: 'prod-1', sku_code: 'TS-01', product_name: 'Футболка', requires_honest_sign: true,
    packaging_instructions: '', qty_total: 2, qty_need_pack: 2, marking_available_count: 5,
  }],
}

type Call = { method: string; path: string; body: unknown }
let calls: Call[]
let delays: Record<string, number>
const PRODUCT = '4600000000017'
const png = 'data:image/png;base64,AQID'
let nativeMode: 'online' | 'lost' | 'missing'
let nativeJobs: Map<string, Record<string, unknown>>
let selections: Map<string, number>
let printStarted: Set<string>
let newChz: boolean
let committedTails: Record<string, string | null>
const originalFetch = globalThis.fetch

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

async function wait(ms: number) {
  if (ms > 0) await new Promise((resolve) => setTimeout(resolve, ms))
}

async function server(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = typeof init?.body === 'string' ? JSON.parse(init.body) : null
  const path = url.pathname.replace(/^\/api/, '')
  calls.push({ method, path: `${path}${url.search}`, body })
  if (url.hostname === '127.0.0.1') {
    if (path === '/health') return json({ app: 'WMS Print Direct', protocolVersion: 2 })
    if (path === '/print') {
      const sent = body as Parameters<typeof directQrHash>[0]
      const job = { ...sent, hash: await directQrHash(sent), status: 'accepted', receipt: `queue-${nativeJobs.size + 1}` }
      nativeJobs.set(sent.idempotencyKey, job)
      if (nativeMode === 'lost') { nativeMode = 'online'; throw new Error('lost POST response') }
      return json(job, 202)
    }
    const key = decodeURIComponent(path.split('/jobs/')[1]?.split('/')[0] ?? '')
    return nativeMode !== 'missing' && nativeJobs.has(key) ? json(nativeJobs.get(key)) : json({}, 404)
  }
  if (path === '/fixture-ordinary-label.png') return new Response(Uint8Array.from([1, 2, 3]), { headers: { 'Content-Type': 'image/png' } })
  if (path.endsWith('/scan-auto-print')) {
    const sent = body as { idempotency_key: string }
    if (!selections.has(sent.idempotency_key)) selections.set(sent.idempotency_key, selections.size + 1)
    const index = selections.get(sent.idempotency_key)!
    return json({ scan_id: `ordinary-scan-${index}`, order_id: index === 1 ? 'order-a' : 'order-b', wb_order_id: 5000 + index,
      requires_honest_sign: newChz, qr_asset: { id: 'qr', status: 'ready', preview_url: '/fixture-ordinary-label.png' },
      printed_codes: newChz ? [{ id: 'code-one', cis_code: KIZ_A }] : [], shortage: 0, order_errors: [], reprint_recovery: null })
  }
  if (path.endsWith('/print-claim')) {
    const key = path.split('/scan-auto-print/')[1]!.split('/')[0]!
    return json({ claimed: !printStarted.has(key), started: printStarted.has(key) })
  }
  if (path.endsWith('/print-started')) {
    const key = path.split('/scan-auto-print/')[1]!.split('/')[0]!
    printStarted.add(key)
    return json({ claimed: false, started: true })
  }
  if (path.startsWith('/operations/packaging-tasks/')) return json(packagingTask)
  if (path === '/operations/fbs-orders/kiz/lookup') {
    await wait(delays.lookup ?? 0)
    const sticker = url.searchParams.get('sticker')
    const orderId = sticker === STICKER_A ? 'order-a' : sticker === STICKER_B ? 'order-b' : null
    if (!orderId) {
      return json({ detail: { code: 'sticker_not_found', message: 'sticker_not_found' } }, 404)
    }
    return json({
      order_id: orderId, wb_order_id: orderId === 'order-a' ? 5001 : 5002,
      product: { name: 'Футболка', image_url: null, barcode: null, seller_article: null },
      current_kiz: null, needs_confirmation: false, can_bind: true, block_reason: null,
    })
  }
  if (path === '/operations/fbs-orders/kiz/validate') {
    await wait(delays.validate ?? 0)
    return json({ ok: true, hints: [] })
  }
  if (path === '/operations/fbs-orders/kiz/commit') {
    await wait(delays.commit ?? 0)
    const pair = (body as { pairs: Array<{ order_id: string; value: string }> }).pairs[0]!
    committedTails[pair.order_id] = pair.value.slice(-8)
    return json([{ order_id: pair.order_id, status: 'ok', code: 'ok', message: 'ok', newly_bound: true, bound_kiz: pair.value }])
  }
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/workspace`) {
    await wait(delays.workspace ?? 0)
    return json(workspace(committedTails))
  }
  return json(null)
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  Object.defineProperty(globalThis, 'crypto', { value: webcrypto, configurable: true })
  durable.rows.clear(); durable.chz.mockClear(); durable.noLocks = false
  nativeJobs = new Map(); selections = new Map(); printStarted = new Set(); nativeMode = 'online'; newChz = false
  calls = []
  delays = {}
  committedTails = {}
  window.sessionStorage.clear()
  window.localStorage.clear()
  globalThis.fetch = server as typeof fetch
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  document.body.innerHTML = ''
  globalThis.fetch = originalFetch
})

async function settle(ms = 0) {
  const steps = Math.max(1, Math.ceil(ms / 10))
  for (let step = 0; step < steps; step += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, Math.min(ms, 10)))
    })
  }
}

/** «Клавиатурный» сканер: символы подряд и Enter — туда, где сейчас фокус. */
function scan(code: string) {
  const target = document.activeElement ?? document.body
  let enter: KeyboardEvent | null = null
  act(() => {
    for (const key of code) {
      target.dispatchEvent(new KeyboardEvent('keydown', { key, code: 'KeyA', bubbles: true, cancelable: true }))
    }
    enter = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true })
    target.dispatchEvent(enter)
  })
  return enter! as KeyboardEvent
}

async function openPackingTab(initial: FbsWorkspace = workspace()) {
  await act(async () => {
    root.render(
      <FfFbsSupplyWorkspace
        token="t-575"
        authHeaders={() => ({ Authorization: 'Bearer t-575' })}
        supplyId={SUPPLY_ID}
        initialWorkspace={initial}
        open
        onClose={() => undefined}
      />,
    )
  })
  await settle(50)
  expect(document.querySelector('[data-testid="fbs-kiz-scan-bar"]')).not.toBeNull()
}

const activeRow = () => document.querySelector<HTMLElement>('[data-testid="fbs-kiz-row-active"]')?.dataset.orderId ?? null
const rowTail = (orderId: string) => document.querySelector<HTMLElement>(`[data-order-id="${orderId}"]`)?.dataset.kizTail ?? ''
const kizCalls = () => calls.filter((call) => call.path.startsWith('/operations/fbs-orders/kiz/'))

describe('WMS-575 · «Упаковка и маркировка» принимает скан в любой точке', () => {
  it('C5/R5: фокус на «Выбрать всё» — стикер A, ЧЗ A, стикер B без единого клика', async () => {
    await openPackingTab()
    const selectAll = document.querySelector<HTMLButtonElement>('[data-testid="fbs-packing-select-all"]')!
    act(() => selectAll.focus())
    expect(document.activeElement).toBe(selectAll)

    const first = scan(STICKER_A)
    await settle(40)
    expect(first.defaultPrevented).toBe(true)
    expect(activeRow()).toBe('order-a')

    scan(KIZ_A)
    await settle(60)
    scan(STICKER_B)
    await settle(60)

    expect(kizCalls().map((call) => call.path.split('?')[0])).toEqual([
      '/operations/fbs-orders/kiz/lookup',
      '/operations/fbs-orders/kiz/validate',
      '/operations/fbs-orders/kiz/commit',
      '/operations/fbs-orders/kiz/lookup',
    ])
    const commit = kizCalls().find((call) => call.path === '/operations/fbs-orders/kiz/commit')!
    expect((commit.body as { pairs: Array<{ order_id: string; value: string }> }).pairs[0]).toMatchObject({
      order_id: 'order-a', value: KIZ_A,
    })
    expect(activeRow()).toBe('order-b')
    // «Выбрать всё» от Enter сканера не нажималась: ни один заказ не выбран.
    expect(document.querySelectorAll('[data-testid="fbs-packing-select-order"] input:checked')).toHaveLength(0)
  })

  it('C6/R6: стикер A и ЧЗ A подряд, пока сервер отвечает, — оба обработаны по порядку, ЧЗ у заказа A', async () => {
    delays = { lookup: 150, validate: 50, commit: 50 }
    await openPackingTab()
    act(() => (document.activeElement as HTMLElement | null)?.blur())

    scan(STICKER_A)
    scan(KIZ_A)
    await settle(600)

    expect(kizCalls().map((call) => call.path.split('?')[0])).toEqual([
      '/operations/fbs-orders/kiz/lookup',
      '/operations/fbs-orders/kiz/validate',
      '/operations/fbs-orders/kiz/commit',
    ])
    const validate = kizCalls()[1]!
    expect(validate.body).toMatchObject({ order_id: 'order-a', value: KIZ_A })
  })

  it('C7/R7: хвост ЧЗ в строке сразу по ответу commit, до ответа перечитывания; следующий скан не ждёт его', async () => {
    delays = { workspace: 400 }
    await openPackingTab()
    act(() => (document.activeElement as HTMLElement | null)?.blur())

    scan(STICKER_A)
    await settle(40)
    scan(KIZ_A)
    await settle(60)

    // Перечитывание поставки ещё идёт, а хвост уже в строке.
    expect(calls.some((call) => call.path === `/operations/fbs-supplies/${SUPPLY_ID}/workspace`)).toBe(true)
    expect(rowTail('order-a')).toBe(KIZ_A.slice(-8))

    // Следующий скан принят до ответа перечитывания.
    scan(STICKER_B)
    await settle(60)
    expect(activeRow()).toBe('order-b')

    await settle(500)
    expect(rowTail('order-a')).toBe(KIZ_A.slice(-8))
  })

  it('C5/R5: курсор в поле скана — код обработан один раз и не остаётся в поле', async () => {
    await openPackingTab()
    const input = document.querySelector<HTMLInputElement>('[data-testid="fbs-kiz-scan-input"] input, input[data-testid="fbs-kiz-scan-input"]')
      ?? document.querySelector<HTMLElement>('[data-testid="fbs-kiz-scan-input"]')!.querySelector('input')!
    act(() => input.focus())
    scan(STICKER_A)
    await settle(60)

    expect(kizCalls().map((call) => call.path.split('?')[0])).toEqual(['/operations/fbs-orders/kiz/lookup'])
    expect(activeRow()).toBe('order-a')
    expect(input.value).toBe('')
  })
})

// R11: круговая стрелка «Перепечатать ЧЗ» (WMS-519) показывается у кода,
// внесённого оператором, только когда сервер отдал id этого кода. До правки
// схемы ответа id выбрасывался, и стрелки не было ни у одного заказа.
describe('WMS-575 · R11 стрелка «Перепечатать ЧЗ» у кода оператора', () => {
  const reprintArrow = (orderId: string) =>
    document.querySelector(`[data-order-id="${orderId}"] [data-testid="fbs-kiz-reprint-inline"]`)

  it('сервер отдал id кода оператора — стрелка в строке этого заказа', async () => {
    await openPackingTab(workspace({ 'order-a': 'AbCd1234' }))
    expect(reprintArrow('order-a')).not.toBeNull()
    // У заказа без кода стрелки нет.
    expect(reprintArrow('order-b')).toBeNull()
  })

  it('без id — как отвечал сервер до правки — стрелки нет', async () => {
    const withoutId = workspace({ 'order-a': 'AbCd1234' })
    for (const current of withoutId.orders) {
      for (const state of current.metadata.states) delete (state as { id?: string | null }).id
    }
    await openPackingTab(withoutId)
    expect(reprintArrow('order-a')).toBeNull()
  })
})

// Ночное ревью кандидата 29.09 (P1-1 Opus, F3 Astra).
describe('WMS-575 · исправления по ревью ночного кандидата', () => {
  const LAT = "qwertyuiop[]asdfghjkl;'zxcvbnm,./"
  const RUS = 'йцукенгшщзхъфывапролджэячсмитьбю.'
  const ruKey = (ch: string): { key: string; code: string; shiftKey: boolean } => {
    if (/[0-9]/.test(ch)) return { key: ch, code: `Digit${ch}`, shiftKey: false }
    if (ch === '/') return { key: '.', code: 'Slash', shiftKey: false }
    if (ch === '?') return { key: ',', code: 'Slash', shiftKey: true }
    if (ch === '&') return { key: '?', code: 'Digit7', shiftKey: true }
    const lower = ch.toLowerCase()
    const ru = RUS[LAT.indexOf(lower)]
    return { key: ch === lower ? ru : ru.toUpperCase(), code: `Key${lower.toUpperCase()}`, shiftKey: ch !== lower }
  }
  const scanRu = (code: string) => {
    const target = document.activeElement ?? document.body
    act(() => {
      for (const ch of code) {
        const k = ruKey(ch)
        target.dispatchEvent(new KeyboardEvent('keydown', { key: k.key, code: k.code, shiftKey: k.shiftKey, bubbles: true, cancelable: true }))
      }
      target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
    })
  }
  const KIZ_SYMBOLS = '0104600000000017215Ab/c?d&Ef9GhJ'
  const bodyOf = (path: string) => kizCalls().find((call) => call.path === path)?.body as
    | { order_id?: string; value?: string; pairs?: Array<{ order_id: string; value: string }> }
    | undefined

  it('P1: русская раскладка — ЧЗ с «/», «?», «&» уходит на validate и commit сырым, как из поля скана', async () => {
    await openPackingTab()
    const input = document.querySelector<HTMLElement>('[data-testid="fbs-kiz-scan-input"]')!.querySelector('input')!
    act(() => input.focus())
    scan(STICKER_A)
    await settle(60)
    scanRu(KIZ_SYMBOLS)
    await settle(80)
    // Сервер восстанавливает эту строку в исходный код полной таблицей
    // раскладки (backend/tests/test_fbs_kiz_ru_layout_symbols.py).
    const raw = '0104600000000017215Фи.с,в?Уа9ПрО'
    expect(bodyOf('/operations/fbs-orders/kiz/validate')).toMatchObject({ order_id: 'order-a', value: raw })
    expect(bodyOf('/operations/fbs-orders/kiz/commit')?.pairs?.[0]).toMatchObject({ order_id: 'order-a', value: raw })
  })

  it('P1: латинская раскладка — тот же ЧЗ уходит без изменений', async () => {
    await openPackingTab()
    act(() => (document.activeElement as HTMLElement | null)?.blur())
    scan(STICKER_A)
    await settle(60)
    scan(KIZ_SYMBOLS)
    await settle(80)
    expect(bodyOf('/operations/fbs-orders/kiz/validate')).toMatchObject({ order_id: 'order-a', value: KIZ_SYMBOLS })
    expect(bodyOf('/operations/fbs-orders/kiz/commit')?.pairs?.[0]).toMatchObject({ order_id: 'order-a', value: KIZ_SYMBOLS })
  })

  it('P2: сканер дважды прочитал стикер, пока шёл поиск, — второй снимает выбор, а не уходит как ЧЗ', async () => {
    delays = { lookup: 150 }
    await openPackingTab()
    act(() => (document.activeElement as HTMLElement | null)?.blur())
    scan(STICKER_A)
    scan(STICKER_A)
    await settle(400)

    expect(kizCalls().map((call) => call.path.split('?')[0])).toEqual(['/operations/fbs-orders/kiz/lookup'])
    expect(activeRow()).toBeNull()
    expect(document.querySelector('[data-testid="fbs-kiz-scan-error"]')).toBeNull()
  })

  it('P2: стикер и ЧЗ подряд во время поиска — как раньше, ЧЗ привязывается к заказу', async () => {
    delays = { lookup: 150 }
    await openPackingTab()
    act(() => (document.activeElement as HTMLElement | null)?.blur())
    scan(STICKER_A)
    scan(KIZ_A)
    await settle(400)
    expect(bodyOf('/operations/fbs-orders/kiz/validate')).toMatchObject({ order_id: 'order-a', value: KIZ_A })
  })
})

describe('WMS-604 unified packing presentation', () => {
  it('prepares missing stickers without a supply Start button and keeps rows and scanner registered', async () => {
    const initial = workspace()
    initial.orders.forEach((order) => { order.sticker.code = null })
    const packingHost = document.createElement('div')
    document.body.appendChild(packingHost)
    const registerScanner = vi.fn()
    const noop = () => undefined
    await act(async () => root.render(<FfFbsSupplyWorkspace
      token="t-575" authHeaders={() => ({})} supplyId={SUPPLY_ID} initialWorkspace={initial}
      open onClose={noop} assemblyFrame={{ packingHost, registerScanner, active: false,
        expanded: false, visible: true, onToggleExpanded: noop, onActivate: noop, onDeactivate: noop,
        onWorkspaceChange: noop, registerEscape: noop }} />))
    await settle(60)
    expect(document.querySelector('[data-testid="fbs-assembly-supply-sup-575"]')).toBeNull()
    expect(document.body.textContent).not.toContain('Начать работу с поставкой')
    expect(packingHost.querySelectorAll('[data-order-id]')).toHaveLength(2)
    expect(packingHost.textContent).toContain('5001')
    expect(registerScanner.mock.calls.some(([, controller]) => Boolean(controller))).toBe(true)
    const prepares = calls.filter((call) => call.path.endsWith('/print-assets'))
    expect(prepares).toHaveLength(1)
    expect(prepares[0].body).toMatchObject({ kind: 'order_sticker', order_ids: ['order-a', 'order-b'], retry_missing: true })
  })
})

describe('WMS-625 ordinary WB durable QR', () => {
  const nativePosts = () => calls.filter((call) => call.path === '/print')
  const setPreferences = (printQr: boolean, printChz = false) => window.localStorage.setItem(
    'wms:fbs:scan-auto-print:unknown-tenant:unknown-user', JSON.stringify({ printQr, printChz, reprintChz: false }))
  const productScans = () => calls.filter((call) => call.path.endsWith('/scan-auto-print'))
  const remount = async () => { await act(async () => root.unmount()); root = createRoot(host); await openPackingTab() }
  it('lost native response + reload retains QR+CHZ snapshot and completed CHZ, then recovers same order without auto-pack', async () => {
    newChz = true; nativeMode = 'lost'; setPreferences(true, true)
    await openPackingTab(); scan(PRODUCT); await settle(130)
    expect(nativePosts()).toHaveLength(1)
    expect(durable.chz).toHaveBeenCalledTimes(1)
    const pending = readPendingAttempts('t-575', SUPPLY_ID)[0]!
    expect(pending).toMatchObject({ orderId: 'order-a', scanId: 'ordinary-scan-1', qrStarted: false, chzStarted: true })
    expect(durable.rows.get('ordinary-scan-1')?.dispatchStartedAt).toBeGreaterThan(0)
    setPreferences(false); await remount(); scan(PRODUCT); await settle(130)
    expect(productScans()).toHaveLength(2)
    expect(productScans()[1].body).toEqual(productScans()[0].body)
    expect(nativePosts()).toHaveLength(1)
    expect(durable.chz).toHaveBeenCalledTimes(1)
    expect(readPendingAttempts('t-575', SUPPLY_ID)).toEqual([])
    expect(calls.some((call) => call.path.endsWith('/pack'))).toBe(false)
    expect(durable.rows.get('ordinary-scan-1')?.input.imageDataUrl).toBe(png)
  })
  it('unknown POST followed by native GET404 stays on same order without another copy', async () => {
    nativeMode = 'lost'; setPreferences(true)
    await openPackingTab(); scan(PRODUCT); await settle(120)
    nativeMode = 'missing'; await remount(); scan(PRODUCT); await settle(120)
    expect(nativePosts()).toHaveLength(1)
    expect(selections.size).toBe(1)
    expect(document.body.textContent).toContain('новая копия не отправлена')
    expect(readPendingAttempts('t-575', SUPPLY_ID)[0]?.scanId).toBe('ordinary-scan-1')
  })
  it('successive identical product units have separate QR intents without changing quantity workflow', async () => {
    setPreferences(true); await openPackingTab(); scan(PRODUCT); await settle(100); scan(PRODUCT); await settle(100)
    expect(nativePosts()).toHaveLength(2)
    expect(selections.size).toBe(2)
    expect(Array.from(durable.rows.keys())).toEqual(['ordinary-scan-1', 'ordinary-scan-2'])
    expect(calls.some((call) => call.path.endsWith('/pack'))).toBe(false)
  })
  it('CHZ-only keeps ordinary code path and never contacts native', async () => {
    newChz = true; setPreferences(false, true); await openPackingTab(); scan(PRODUCT); await settle(100)
    expect(productScans()).toHaveLength(1)
    expect(durable.chz).toHaveBeenCalledTimes(1)
    expect(calls.some((call) => call.path === '/health' || call.path.startsWith('/jobs/') || call.path === '/print')).toBe(false)
  })
  it.each(['wb', 'ozon'])('%s sticker/KIZ path still works with flags off and no Web Locks', async (marketplace) => {
    durable.noLocks = true
    const initial = workspace(); initial.supply.marketplace = marketplace as 'wb' | 'ozon'
    await openPackingTab(initial); scan(STICKER_A); await settle(80)
    expect(activeRow()).toBe('order-a')
    scan(KIZ_A); await settle(100)
    expect(kizCalls().some((call) => call.path === '/operations/fbs-orders/kiz/commit')).toBe(true)
    expect(productScans()).toHaveLength(0)
    expect(nativePosts()).toHaveLength(0)
  })
  it('storage failure stops before server product selection', async () => {
    setPreferences(true); await openPackingTab()
    const setItem = Storage.prototype.setItem
    const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key, value) {
      if (key === fbsPendingProductScanStorageKey('t-575', SUPPLY_ID)) throw new Error('quota')
      setItem.call(this, key, value)
    })
    scan(PRODUCT); await settle(100)
    expect(productScans()).toHaveLength(0)
    expect(nativePosts()).toHaveLength(0)
    expect(document.body.textContent).toContain('Не удалось сохранить попытку')
    write.mockRestore()
  })
})
