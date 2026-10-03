// @vitest-environment jsdom
import { webcrypto } from 'node:crypto'
import { act, useCallback, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'
import { FbsPackingScanBar } from './FbsPackingScanBar'
import type { PackingScanController } from './fbsSequentialPacking'
import { saveFbsScanPrintPreferences } from './fbsScanAutoPrint'
import { directQrHash, forgetDirectQrProtocol, qrAttemptStore, type DurableQrAttempt } from '../../utils/durableDirectQr'

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
let committedTails: Record<string, string | null>
let validationFailure = false
let deleteFailure = false
let commitGate: Promise<void> | null = null
const originalFetch = globalThis.fetch
/** WMS-625: product scans with printing on (off by default, as in every scenario above). */
let printing: null | {
  program: 'old' | 'modern' | null
  loseNextPost: boolean
  selections: Map<string, number>
  started: Set<string>
  jobs: Map<string, Record<string, unknown>>
  native: Array<{ method: string; path: string; body: unknown }>
} = null

async function nativeServer(method: string, path: string, body: unknown): Promise<Response> {
  const state = printing!
  state.native.push({ method, path, body })
  if (!state.program) throw new TypeError('Failed to fetch')
  const sent = body as { idempotencyKey: string } & Parameters<typeof directQrHash>[0]
  if (state.program === 'old') {
    // WMS Print v2026.09.30.4/.5: only POST /print, the receipt kept by key.
    if (method !== 'POST' || path !== '/print') return json({}, 404)
    const receipt = (state.jobs.get(sent.idempotencyKey)?.receipt as string | undefined) ?? `queue-${state.jobs.size + 1}`
    state.jobs.set(sent.idempotencyKey, { receipt })
    if (state.loseNextPost) { state.loseNextPost = false; throw new TypeError('response lost') }
    return json({ receipt })
  }
  if (path === '/health') return json({ app: 'WMS Print Direct', protocolVersion: 2 })
  if (method === 'POST' && path === '/print') {
    if (!state.jobs.has(sent.idempotencyKey)) {
      // The journal keeps the key, size and order; the PNG stays behind its own endpoint.
      const job: Record<string, unknown> = { ...sent, hash: await directQrHash(sent), status: 'accepted', receipt: `queue-${state.jobs.size + 1}` }
      delete job.imageDataUrl
      delete job.protocolVersion
      state.jobs.set(sent.idempotencyKey, job)
    }
    if (state.loseNextPost) { state.loseNextPost = false; throw new TypeError('response lost') }
    return json(state.jobs.get(sent.idempotencyKey), 202)
  }
  const key = decodeURIComponent(path.split('/jobs/')[1]?.split('/')[0] ?? '')
  return state.jobs.has(key) ? json(state.jobs.get(key)) : json({}, 404)
}

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
  if (url.hostname === '127.0.0.1') return nativeServer(method, path, body)
  calls.push({ method, path: `${path}${url.search}`, body })
  if (path.startsWith('/operations/packaging-tasks/')) return json(packagingTask)
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/start-work`) return json(workspace(committedTails))
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
      requires_honest_sign: true,
    })
  }
  if (path === '/operations/fbs-orders/kiz/validate') {
    await wait(delays.validate ?? 0)
    if (validationFailure) return json({ detail: { code: 'duplicate_kiz', message: 'КИЗ уже занят' } }, 409)
    return json({ ok: true, hints: [] })
  }
  if (method === 'DELETE' && path.endsWith('/kiz')) {
    if (deleteFailure) return json({ detail: { code: 'wb_error', message: 'WB отказал' } }, 502)
    committedTails[path.split('/').at(-2)!] = null
    return new Response(null, { status: 204 })
  }
  if (path === '/operations/fbs-orders/kiz/commit') {
    await wait(delays.commit ?? 0)
    await commitGate
    const pair = (body as { pairs: Array<{ order_id: string; value: string }> }).pairs[0]!
    committedTails[pair.order_id] = pair.value.slice(-8)
    return json([{ order_id: pair.order_id, status: 'ok', code: 'ok', message: 'ok', newly_bound: true, bound_kiz: pair.value }])
  }
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/workspace`) {
    await wait(delays.workspace ?? 0)
    return json(workspace(committedTails))
  }
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/scan-auto-print`) {
    if (!printing) return json({ detail: { code: 'scan_product_not_found', message: 'Товар не найден' } }, 404)
    const sent = body as { idempotency_key: string }
    if (!printing.selections.has(sent.idempotency_key)) printing.selections.set(sent.idempotency_key, printing.selections.size + 1)
    const index = printing.selections.get(sent.idempotency_key)!
    return json({
      scan_id: `ordinary-scan-${index}`, order_id: index === 1 ? 'order-a' : 'order-b', wb_order_id: 5000 + index,
      replayed: false, binding_target: null, reprint_recovery: null, requires_honest_sign: false,
      qr_asset: { id: 'qr', status: 'ready', preview_url: '/fixture-qr.png' },
      codes: [], printed_codes: [], shortage: 0, order_errors: [],
    })
  }
  if (printing && path.startsWith(`/operations/fbs-supplies/${SUPPLY_ID}/scan-auto-print/`)) {
    const scanId = path.split('/scan-auto-print/')[1]!.split('/')[0]!
    if (path.endsWith('/print-started')) printing.started.add(scanId)
    return json({ claimed: path.endsWith('/print-claim') && !printing.started.has(scanId), started: printing.started.has(scanId) })
  }
  if (printing && path === '/fixture-qr.png') {
    const blob = new Blob([Uint8Array.from([137, 80, 78, 71])], { type: 'image/png' })
    return { ok: true, status: 200, blob: async () => blob } as Response
  }
  return json(null)
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  calls = []
  delays = {}
  committedTails = {}
  validationFailure = false
  deleteFailure = false
  commitGate = null
  window.sessionStorage.clear()
  window.localStorage.clear()
  // WMS-631: these scenarios are the sticker → KIZ path with every print checkbox off (R9);
  // printing paths are covered by fbsSequentialPacking tests.
  saveFbsScanPrintPreferences('t-575', { printQr: false, printChz: false, reprintChz: false })
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
      if (target instanceof HTMLInputElement && !target.disabled) {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(target, target.value + key)
        target.dispatchEvent(new Event('input', { bubbles: true }))
      }
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

  it('P2: сканер дважды прочитал стикер, пока шёл поиск, — второй не уходит как ЧЗ (механизм сборки, R4)', async () => {
    delays = { lookup: 150 }
    await openPackingTab()
    act(() => (document.activeElement as HTMLElement | null)?.blur())
    scan(STICKER_A)
    scan(STICKER_A)
    await settle(400)

    expect(kizCalls().map((call) => call.path.split('?')[0])).toEqual(['/operations/fbs-orders/kiz/lookup'])
    expect(activeRow()).toBe('order-a')
    expect(document.querySelector('[data-testid="fbs-kiz-scan-error"]')?.textContent).toContain('Сканируйте его Честный знак')
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

describe('WMS-630 · КИЗ в строке точного заказа', () => {
  const input = (id: string) => document.querySelector<HTMLInputElement>(`[data-order-id="${id}"] [data-testid="fbs-kiz-row-input"]`)!
  const focus = (id: string) => act(() => input(id).focus())

  it('выбирает второй заказ того же товара и сразу, без окна, заменяет только его (R18)', async () => {
    committedTails = { 'order-a': 'OLD0000A', 'order-b': 'OLD0000B' }
    await openPackingTab(workspace(committedTails))
    focus('order-b')
    expect(activeRow()).toBe('order-b')
    // Настоящий capture-слушатель принимает scanner burst ровно один раз.
    expect(scan(KIZ_A).defaultPrevented).toBe(true)
    await settle(80)
    expect(document.querySelector('[data-testid="fbs-kiz-confirm-replace"]')).toBeNull()
    expect(kizCalls().map((call) => call.path)).toEqual([
      '/operations/fbs-orders/kiz/validate', '/operations/fbs-orders/kiz/commit',
    ])
    expect(kizCalls()[0].body).toMatchObject({ order_id: 'order-b', value: KIZ_A })
    expect(kizCalls()[1].body).toMatchObject({ pairs: [{ order_id: 'order-b', value: KIZ_A, confirmed: true }] })
    expect(rowTail('order-a')).toBe('OLD0000A')
    expect(rowTail('order-b')).toBe(KIZ_A.slice(-8))
    expect(activeRow()).toBeNull()
    scan(STICKER_A)
    await settle(300)
    expect(activeRow()).toBe('order-a')
  })

  it('при смене поля и ручном вводе с Enter берёт последнюю выбранную строку', async () => {
    await openPackingTab()
    focus('order-a')
    focus('order-b')
    const field = input('order-b')
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, KIZ_A)
      field.dispatchEvent(new Event('input', { bubbles: true }))
    })
    act(() => field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })))
    await settle(60)
    expect(kizCalls()).toHaveLength(2)
    // R10/R18: the row's KIZ replaces at once.
    expect(kizCalls()[1].body).toMatchObject({ pairs: [{ order_id: 'order-b', value: KIZ_A, confirmed: true }] })
    expect(rowTail('order-a')).toBe('')
  })

  it('ошибка валидации сохраняет старый КИЗ; Escape освобождает выбор', async () => {
    committedTails = { 'order-b': 'OLD0000B' }
    validationFailure = true
    await openPackingTab(workspace(committedTails))
    focus('order-b')
    scan(KIZ_A)
    await settle(60)
    expect(rowTail('order-b')).toBe('OLD0000B')
    expect(kizCalls().filter((call) => call.path.endsWith('/commit'))).toHaveLength(0)
    expect(document.querySelector('[data-testid="fbs-kiz-scan-error"]')).not.toBeNull()
    focus('order-b')
    act(() => input('order-b').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })))
    await settle(20)
    expect(activeRow()).toBeNull()
  })

  it('R18: ни окна подтверждения, ни window.confirm при замене КИЗ строкой', async () => {
    committedTails = { 'order-b': 'OLD0000B' }
    const confirmSpy = vi.spyOn(window, 'confirm')
    await openPackingTab(workspace(committedTails))
    focus('order-b')
    scan(KIZ_A)
    await settle(80)
    expect(document.querySelector('[data-testid="fbs-kiz-confirm-replace"]')).toBeNull()
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(rowTail('order-b')).toBe(KIZ_A.slice(-8))
    expect(activeRow()).toBeNull()
    confirmSpy.mockRestore()
  })

  it.each([false, true])('крестик сохраняет отдельное удаление, отказ WB=%s', async (failure) => {
    committedTails = { 'order-b': 'OLD0000B' }
    deleteFailure = failure
    await openPackingTab(workspace(committedTails))
    act(() => document.querySelector<HTMLButtonElement>('[data-order-id="order-b"] [data-testid="fbs-kiz-undo-inline"]')!.click())
    await settle(20)
    const remove = [...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find((button) => button.textContent === 'Отменить КИЗ')!
    act(() => remove.click())
    await settle(60)
    expect(calls.filter((call) => call.method === 'DELETE')).toEqual([{ method: 'DELETE', path: '/operations/fbs-orders/order-b/kiz', body: null }])
    expect(rowTail('order-b')).toBe(failure ? 'OLD0000B' : '')
    expect(kizCalls()).toHaveLength(0)
  })

  it('не добавляет поля Ozon', async () => {
    const initial = workspace()
    initial.supply.marketplace = 'ozon'
    initial.orders.forEach((order) => { order.marketplace = 'ozon' })
    await openPackingTab(initial)
    expect(document.querySelector('[data-testid="fbs-kiz-row-input"]')).toBeNull()
  })

  it.each([false, true])('unified registerScanner: точный confirmed commit, быстрый следующий скан при delayed commit=%s', async (delayed) => {
    let releaseCommit: () => void = () => undefined
    if (delayed) commitGate = new Promise<void>((resolve) => { releaseCommit = resolve })
    committedTails = { 'order-a': 'OLD0000A', 'order-b': 'OLD0000B' }
    const initial = workspace(committedTails)
    initial.supply.packaging_task_id = null
    const packingHost = document.createElement('div')
    document.body.appendChild(packingHost)
    const noop = () => undefined
    const headers = () => ({ Authorization: 'Bearer t-575' })
    function Unified() {
      const [controller, setController] = useState<PackingScanController | null>(null)
      const [, changed] = useState(0)
      const registerScanner = useCallback((_id: string, scanner: PackingScanController | null) => setController(scanner), [])
      const onScanChange = useCallback(() => changed((value) => value + 1), [])
      return <>
        <FbsPackingScanBar token="t-575" enabled={Boolean(controller)} controllers={controller ? [controller] : []} />
        <FfFbsSupplyWorkspace token="t-575" authHeaders={headers} supplyId={SUPPLY_ID}
          initialWorkspace={initial} open onClose={noop}
          assemblyFrame={{ packingHost, registerScanner, onScanChange, active: false, expanded: false,
            visible: true, onToggleExpanded: noop, onActivate: noop, onDeactivate: noop,
            onWorkspaceChange: noop, registerEscape: noop }} />
      </>
    }
    await act(async () => root.render(<Unified />))
    await settle(50)
    expect(input('order-b')).not.toBeNull()
    focus('order-b')
    expect(activeRow()).toBe('order-b')
    scan(KIZ_A)
    await settle(30)
    if (delayed) {
      // The commit still waits for the server; the next scan is accepted and queued.
      scan(STICKER_A)
      await settle(30)
      expect(rowTail('order-b')).toBe('OLD0000B')
      expect(kizCalls()).toHaveLength(2)
      act(() => releaseCommit())
      await settle(80)
    }
    // The queued sticker is looked up only after the row commit finished (one queue).
    expect(kizCalls().map((call) => call.path.split('?')[0])).toEqual([
      '/operations/fbs-orders/kiz/validate', '/operations/fbs-orders/kiz/commit',
      ...(delayed ? ['/operations/fbs-orders/kiz/lookup'] : []),
    ])
    expect(kizCalls()[1].body).toMatchObject({ pairs: [{ order_id: 'order-b', value: KIZ_A, confirmed: true }] })
    expect(rowTail('order-a')).toBe('OLD0000A')
    expect(rowTail('order-b')).toBe(KIZ_A.slice(-8))
    expect(activeRow()).toBe(delayed ? 'order-a' : null)
    expect(calls.filter((call) => call.path.endsWith('/start-work'))).toHaveLength(1)
    expect(calls.some((call) => call.path.includes('/assign'))).toBe(false)
    // All checkboxes off: the queued sticker is looked up after the commit, no product scan (R9).
    expect(calls.filter((call) => call.path.endsWith('/scan-auto-print'))).toHaveLength(0)
    expect(calls.filter((call) => call.path.startsWith('/operations/fbs-orders/kiz/lookup'))).toHaveLength(delayed ? 1 : 0)
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

describe('WMS-625 · обычная карточка WB: QR заказа через WMS Print после скана товара', () => {
  const PRODUCT = '4600000000017'
  let rows: Map<string, DurableQrAttempt>
  let storeSpies: Array<{ mockRestore: () => void }> = []
  const nativePosts = () => printing!.native.filter((call) => call.method === 'POST' && call.path === '/print')
  const productScans = () => calls.filter((call) => call.path.endsWith('/scan-auto-print'))
  const packs = () => calls.filter((call) => call.path.endsWith('/pack'))
  const remount = async () => {
    await act(async () => root.unmount())
    root = createRoot(host)
    await openPackingTab()
  }

  beforeAll(() => {
    Object.defineProperty(globalThis, 'crypto', { value: webcrypto, configurable: true })
  })
  beforeEach(() => {
    printing = { program: 'old', loseNextPost: false, selections: new Map(), started: new Set(), jobs: new Map(), native: [] }
    rows = new Map()
    forgetDirectQrProtocol()
    // jsdom has no IndexedDB: the browser record lives in memory, with the same contract.
    storeSpies = [
      vi.spyOn(qrAttemptStore, 'get').mockImplementation(async (key) => structuredClone(rows.get(key))),
      vi.spyOn(qrAttemptStore, 'put').mockImplementation(async (attempt) => { rows.set(attempt.input.idempotencyKey, structuredClone(attempt)) }),
    ]
    saveFbsScanPrintPreferences('t-575', { printQr: true, printChz: false, reprintChz: false })
  })
  afterEach(() => {
    printing = null
    for (const spy of storeSpies) spy.mockRestore()
  })

  it('старая программа (только POST /print): одна этикетка тем же запросом, что на production (плюс контекст заказа, который она не читает), заказ упакован', async () => {
    await openPackingTab()
    scan(PRODUCT)
    await settle(200)
    expect(nativePosts()).toHaveLength(1)
    const body = nativePosts()[0].body as Record<string, unknown>
    expect(Object.keys(body)).toEqual(['imageDataUrl', 'idempotencyKey', 'widthMm', 'heightMm', 'context'])
    expect(body).toMatchObject({ idempotencyKey: 'ordinary-scan-1', widthMm: 58, heightMm: 40,
      context: { orderId: 'order-a', scanId: 'ordinary-scan-1', barcode: PRODUCT, marketplace: 'wildberries', wbOrderId: 5001 } })
    expect(String(body.imageDataUrl)).toMatch(/^data:image\/png;base64,/)
    expect(printing!.started.has('ordinary-scan-1')).toBe(true)
    expect(packs()).toHaveLength(1)
    expect(document.body.textContent).not.toContain('WMS Print')
  })

  it('новая программа: ответ потерян, страница перезагружена — повторный скан того же товара берёт тот же заказ и ту же этикетку, второй копии нет', async () => {
    printing!.program = 'modern'
    printing!.loseNextPost = true
    await openPackingTab()
    scan(PRODUCT)
    await settle(200)
    expect(nativePosts()).toHaveLength(1)
    expect(document.body.textContent).toContain('Нет ответа WMS Print')
    expect(packs()).toHaveLength(0)
    expect(rows.get('ordinary-scan-1')?.input.context).toMatchObject({ orderId: 'order-a', scanId: 'ordinary-scan-1', barcode: PRODUCT, wbOrderId: 5001 })
    await remount()
    scan(PRODUCT)
    await settle(200)
    expect(productScans()).toHaveLength(2)
    expect((productScans()[1].body as { idempotency_key: string }).idempotency_key)
      .toBe((productScans()[0].body as { idempotency_key: string }).idempotency_key)
    expect(printing!.selections.size).toBe(1)
    expect(nativePosts()).toHaveLength(1)
    expect(packs()).toHaveLength(1)
  })

  it('WMS-643: галка QR снята — WMS Print не нужен и не вызывается', async () => {
    saveFbsScanPrintPreferences('t-575', { printQr: false, printChz: true, reprintChz: false })
    printing!.program = null
    await openPackingTab()
    scan(PRODUCT)
    await settle(200)
    expect(productScans()).toHaveLength(1)
    expect(printing!.native).toEqual([])
    expect(packs()).toHaveLength(1)
  })
})
