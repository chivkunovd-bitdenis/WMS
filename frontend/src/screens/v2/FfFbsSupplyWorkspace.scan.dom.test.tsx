// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'

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

async function openPackingTab() {
  await act(async () => {
    root.render(
      <FfFbsSupplyWorkspace
        token="t-575"
        authHeaders={() => ({ Authorization: 'Bearer t-575' })}
        supplyId={SUPPLY_ID}
        initialWorkspace={workspace()}
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
