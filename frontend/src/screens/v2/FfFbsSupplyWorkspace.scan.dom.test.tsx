// @vitest-environment jsdom
import { webcrypto } from 'node:crypto'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'
import { printPreparedQr } from '../../utils/printPreparedQr'

// The scanner tests render the real workspace and scan intake; unrelated modal
// contents and the picking screen do not participate in these scenarios.
// OS/browser print transport has its own tests; this suite verifies routing and packing.
vi.mock('../../utils/printPreparedQr', () => ({ printPreparedQr: vi.fn().mockResolvedValue(undefined) }))
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
const STICKER_A = '4600000000017'
const STICKER_B = STICKER_A
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
let selectedCount = 0
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
  if (path.startsWith('/operations/packaging-tasks/')) return json(packagingTask)
  if (path.endsWith('/scan-auto-print')) {
    await wait(delays.lookup ?? 0)
    const orderId = selectedCount++ === 0 ? 'order-a' : 'order-b'
    return json({ scan_id: `scan-${orderId}`, order_id: orderId, wb_order_id: orderId === 'order-a' ? 5001 : 5002,
      requires_honest_sign: true, reprint_recovery: null, qr_asset: { status: 'ready', preview_url: '/fixture.png' },
      binding_target: { order_id: orderId, product: { name: 'Футболка' } }, order_errors: [],
    })
  }
  if (path === '/fixture.png') return new Response(new Blob(['fixture'], { type: 'image/png' }))
  if (path.endsWith('/print-claim')) return json({ claimed: true, started: false })
  if (path.endsWith('/print-started')) return json({ claimed: false, started: true })
  if (path === '/operations/fbs-orders/kiz/validate') {
    await wait(delays.validate ?? 0)
    if (body.value === STICKER_A) return json({ detail: { code: 'invalid_kiz', message: 'Сканируйте Честный знак' } }, 422)
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
  calls = []
  delays = {}
  committedTails = {}
  selectedCount = 0
  vi.mocked(printPreparedQr).mockClear()
  vi.stubGlobal('crypto', webcrypto)
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
  vi.unstubAllGlobals()
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
  expect(document.querySelector('[data-testid="fbs-unified-scan"]')).not.toBeNull()
}

const activeRow = () => document.querySelector<HTMLElement>('[data-testid="fbs-kiz-row-active"]')?.dataset.orderId ?? null
const rowTail = (orderId: string) => document.querySelector<HTMLElement>(`[data-order-id="${orderId}"]`)?.dataset.kizTail ?? ''
const kizCalls = () => calls.filter((call) => call.path.startsWith('/operations/fbs-orders/kiz/'))

describe('WMS-575 · «Упаковка и маркировка» принимает скан в любой точке', () => {
  it('C5/R5: фокус на «Выбрать всё» — ШК товара, ЧЗ A, следующий ШК без единого клика', async () => {
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
      '/operations/fbs-orders/kiz/validate',
      '/operations/fbs-orders/kiz/commit',
    ])
    const commit = kizCalls().find((call) => call.path === '/operations/fbs-orders/kiz/commit')!
    expect((commit.body as { pairs: Array<{ order_id: string; value: string }> }).pairs[0]).toMatchObject({
      order_id: 'order-a', value: KIZ_A,
    })
    expect(activeRow()).toBe('order-b')
    // «Выбрать всё» от Enter сканера не нажималась: ни один заказ не выбран.
    expect(document.querySelectorAll('[data-testid="fbs-packing-select-order"] input:checked')).toHaveLength(0)
  })

  it('C6/R6: ШК товара и ЧЗ A подряд, пока сервер отвечает, — оба обработаны по порядку, ЧЗ у заказа A', async () => {
    delays = { lookup: 150, validate: 50, commit: 50 }
    await openPackingTab()
    act(() => (document.activeElement as HTMLElement | null)?.blur())

    scan(STICKER_A)
    scan(KIZ_A)
    await settle(600)

    expect(kizCalls().map((call) => call.path.split('?')[0])).toEqual([
      '/operations/fbs-orders/kiz/validate',
      '/operations/fbs-orders/kiz/commit',
    ])
    const validate = kizCalls()[0]!
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
    const input = document.querySelector<HTMLInputElement>('[data-testid="fbs-unified-scan"] input')!
    act(() => input.focus())
    scan(STICKER_A)
    await settle(60)

    expect(calls.filter((call) => call.path.endsWith('/scan-auto-print'))).toHaveLength(1)
    expect(kizCalls()).toHaveLength(0)
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
    const input = document.querySelector<HTMLInputElement>('[data-testid="fbs-unified-scan"] input')!
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

  it('WMS-604: повтор товарного ШК вместо ЧЗ оставляет тот же заказ и не печатает', async () => {
    delays = { lookup: 150 }
    await openPackingTab()
    act(() => (document.activeElement as HTMLElement | null)?.blur())
    scan(STICKER_A)
    scan(STICKER_A)
    await settle(400)

    expect(kizCalls()).toHaveLength(0)
    expect(activeRow()).toBe('order-a')
    expect(printPreparedQr).not.toHaveBeenCalled()
  })

  it('P2: ШК и ЧЗ подряд во время поиска — как раньше, ЧЗ привязывается к заказу', async () => {
    delays = { lookup: 150 }
    await openPackingTab()
    act(() => (document.activeElement as HTMLElement | null)?.blur())
    scan(STICKER_A)
    scan(KIZ_A)
    await settle(400)
    expect(bodyOf('/operations/fbs-orders/kiz/validate')).toMatchObject({ order_id: 'order-a', value: KIZ_A })
  })
})
