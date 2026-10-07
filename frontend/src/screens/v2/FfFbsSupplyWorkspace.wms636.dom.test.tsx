// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'
import { saveFbsScanPrintPreferences } from './fbsScanAutoPrint'

vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
vi.mock('../../utils/useMarkingCodePrint', () => ({ useMarkingCodePrint: () => ({ openPrint: vi.fn(), dialog: null }) }))
vi.mock('./FbsSupplyHistoryDialog', () => ({ FbsSupplyHistoryDialog: () => null }))
vi.mock('./FbsPrintPreviewDialog', () => ({ FbsPrintPreviewDialog: () => null }))
vi.mock('./FbsTransferSupplyDialog', () => ({ FbsTransferSupplyDialog: () => null, makeFbsTransferSupplyDeps: () => ({}) }))

// WMS-636 · треугольник «Не принятые WB КИЗ» — фильтр ленты упаковки WB.
// Настоящая карточка поставки; сервер подменён через fetch, сканер — keydown.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})

const SUPPLY_ID = 'sup-636'
const IDS = ['order-a', 'order-b', 'order-c', 'order-d'] as const
type Id = typeof IDS[number]
type Mark = 'rejected' | 'accepted' | 'pending' | 'missing'
const STICKER: Record<Id, string> = { 'order-a': '*CDhjtA1111', 'order-b': '*CDhjtB2222', 'order-c': '*CDhjtC3333', 'order-d': '*CDhjtD4444' }
const KIZ = '0104600000000017215AbCdEfGh1234'

let marks: Record<Id, Mark>
/** What WB answers to the next KIZ committed for an order (default: still checking). */
let verdictOnCommit: Partial<Record<Id, Mark>>

function state(id: Id) {
  const mark = marks[id]
  if (mark === 'missing') return { kind: 'sgtin', status: 'missing', reason: null, source: null, value_tail: null }
  return {
    id: `mark-${id}`, kind: 'sgtin', status: mark, source: 'operator', value_tail: 'TAIL1234',
    reason: mark === 'rejected' ? 'КИЗ не введён в оборот' : null,
  }
}

function order(id: Id, index: number) {
  const wbOrderId = 6001 + index
  return {
    id, marketplace: 'wb', external_order_id: null, wb_order_id: wbOrderId, status: 'assembling',
    wb_status: 'confirm', supplier_status: 'confirm', seller: { id: 'seller-1', name: 'ИП Тестовый' },
    wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'wh-1', name: 'Основной склад' },
    product: {
      id: 'prod-1', name: `Футболка ${index + 1}`, image_url: null, seller_article: 'TS-01', wb_article: 1001,
      barcode: '4600000000017', sku: 'TS-01', chrt_id: 1, category: 'Футболки', color: null, size: null,
    },
    positions: [], inventory: { available_unpacked: 5, locations: [] }, buyer_type: 'individual', cargo_type: 'mgt',
    can_pvz: false,
    metadata: { required: ['sgtin'], optional: [], states: [state(id)], delivery_allowed: false, last_checked_at: null },
    sticker: { code: `${wbOrderId} 000${index}`, status: 'print_opened', asset_url: null, applied_at: null },
    pick: { status: 'picked', location_code: 'А-01-01', picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: new Date().toISOString(), deadline_at: new Date(Date.now() + 86_400_000).toISOString(),
    supply_id: SUPPLY_ID, selection_blockers: [], tape_order_index: index,
  }
}

function workspace(): FbsWorkspace {
  return {
    supply: {
      id: SUPPLY_ID, marketplace: 'wb', wb_supply_id: 'WB-GI-636', source: 'wms', name: 'Поставка 000636',
      status: 'assembling', delivery_type: 'warehouse_sc', seller: { id: 'seller-1', name: 'ИП Тестовый' },
      wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'wh-1', name: 'Основной склад' },
      planned_destination: null, planned_shipment_date: null,
      nearest_deadline_at: new Date(Date.now() + 86_400_000).toISOString(), packaging_task_id: 'pt-636', barcode_asset: null,
    },
    stage: 'packing',
    progress: { picked: 4, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 4 },
    blockers: [], orders: IDS.map((id, index) => order(id, index)), cargo_places: [], boxes: [],
    delivery_preflight: null, last_wb_sync_at: null, server_now: new Date().toISOString(),
  } as unknown as FbsWorkspace
}

const packagingTask = {
  id: 'pt-636', document_number: '000636', display_number: '000636', status: 'in_progress', lines: [{
    id: 'ptl-1', product_id: 'prod-1', sku_code: 'TS-01', product_name: 'Футболка', requires_honest_sign: true,
    packaging_instructions: '', qty_total: 4, qty_need_pack: 4, marking_available_count: 5,
  }],
}

let calls: string[]
let undoBodies: unknown[]
const originalFetch = globalThis.fetch
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

async function server(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = typeof init?.body === 'string' ? JSON.parse(init.body) : null
  const path = url.pathname.replace(/^\/api/, '')
  calls.push(`${method} ${path}`)
  if (path.startsWith('/operations/packaging-tasks/')) return json(packagingTask)
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/start-work`) return json(workspace())
  if (path === '/operations/fbs-orders/kiz/lookup') {
    const id = IDS.find((one) => STICKER[one] === url.searchParams.get('sticker'))
    if (!id) return json({ detail: { code: 'sticker_not_found', message: 'sticker_not_found' } }, 404)
    return json({
      order_id: id, wb_order_id: 6001 + IDS.indexOf(id), product: { name: 'Футболка', image_url: null, barcode: null, seller_article: null },
      current_kiz: null, needs_confirmation: false, can_bind: true, block_reason: null, requires_honest_sign: true,
    })
  }
  if (path === '/operations/fbs-orders/kiz/validate') return json({ ok: true, hints: [] })
  if (path === '/operations/fbs-orders/kiz/commit') {
    const pair = (body as { pairs: Array<{ order_id: Id; value: string }> }).pairs[0]!
    marks[pair.order_id] = verdictOnCommit[pair.order_id] ?? 'pending'
    return json([{ order_id: pair.order_id, status: 'ok', code: 'ok', message: 'ok', newly_bound: true, bound_kiz: pair.value }])
  }
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/scan-undo`) {
    undoBodies.push(body)
    marks[(body as { order_id: Id }).order_id] = 'missing'
    return json({ warning: null })
  }
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/workspace`) return json(workspace())
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/scan-auto-print`) {
    return json({ detail: { code: 'scan_product_not_found', message: 'Товар не найден' } }, 404)
  }
  return json(null)
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  calls = []
  undoBodies = []
  marks = { 'order-a': 'rejected', 'order-b': 'accepted', 'order-c': 'missing', 'order-d': 'rejected' }
  verdictOnCommit = {}
  window.sessionStorage.clear()
  window.localStorage.clear()
  // The sticker → KIZ path with every print checkbox off, as in WMS-575 tests.
  saveFbsScanPrintPreferences('t-636', { printQr: false, printChz: false, reprintChz: false })
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
  for (let step = 0; step < Math.max(1, Math.ceil(ms / 10)); step += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, Math.min(ms, 10))) })
  }
}

function scan(code: string) {
  const target = document.activeElement ?? document.body
  act(() => {
    for (const key of code) {
      target.dispatchEvent(new KeyboardEvent('keydown', { key, code: 'KeyA', bubbles: true, cancelable: true }))
      if (target instanceof HTMLInputElement && !target.disabled) {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(target, target.value + key)
        target.dispatchEvent(new Event('input', { bubbles: true }))
      }
    }
    target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
}

async function open() {
  await act(async () => {
    root.render(
      <FfFbsSupplyWorkspace token="t-636" authHeaders={() => ({ Authorization: 'Bearer t-636' })} supplyId={SUPPLY_ID}
        initialWorkspace={workspace()} open onClose={() => undefined} />,
    )
  })
  await settle(50)
  act(() => (document.activeElement as HTMLElement | null)?.blur())
}

const q = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`)
const rows = () => [...document.querySelectorAll<HTMLElement>('[data-order-id]')]
const rowsStack = () => rows()[0]!.parentElement!
const visibleIds = () => rows().filter((row) => getComputedStyle(row).display !== 'none').map((row) => row.dataset.orderId)
const greenId = () => document.querySelector<HTMLElement>('[data-scan-highlighted="true"]')?.dataset.orderId ?? null
const toggle = () => q('fbs-wb-rejected-kiz-toggle')
/** DOM order of the rows stack: order ids and the header. */
const listOrder = () => [...rowsStack().children]
  .filter((node) => getComputedStyle(node as HTMLElement).display !== 'none' && node.tagName !== 'HR')
  .map((node) => (node as HTMLElement).dataset.orderId ?? (node as HTMLElement).dataset.testid)
const click = (element: HTMLElement) => act(() => element.click())

describe('WMS-636 · фильтр «Не принятые WB КИЗ»', () => {
  it('R1/R3: без непринятых треугольника нет, лента как раньше', async () => {
    marks = { 'order-a': 'accepted', 'order-b': 'accepted', 'order-c': 'missing', 'order-d': 'pending' }
    await open()
    expect(toggle()).toBeNull()
    expect(q('fbs-wb-rejected-kiz-header')).toBeNull()
    expect(visibleIds()).toEqual([...IDS])
    expect(rowsStack().querySelectorAll(':scope > hr')).toHaveLength(IDS.length - 1)
  })

  it('R1/R2/R3/R4: треугольник N, клик — только непринятые под шапкой, повторный клик — обычная лента', async () => {
    await open()
    expect(toggle()!.textContent).toBe('2')
    expect(toggle()!.getAttribute('aria-pressed')).toBe('false')
    // R3: фильтр выключен — все строки, красные на своих местах, шапки нет, разделители как были.
    expect(visibleIds()).toEqual([...IDS])
    expect(q('fbs-wb-rejected-kiz-header')).toBeNull()
    expect(rowsStack().querySelectorAll(':scope > hr')).toHaveLength(IDS.length - 1)

    click(toggle()!)
    expect(toggle()!.getAttribute('aria-pressed')).toBe('true')
    expect(q('fbs-wb-rejected-kiz-header')!.textContent).toContain('Не принятые WB КИЗ · 2')
    expect(listOrder()).toEqual(['fbs-wb-rejected-kiz-header', 'order-a', 'order-d'])
    // R4: остальные строки только скрыты — в DOM они есть.
    expect(rows().map((row) => row.dataset.orderId)).toEqual([...IDS])

    click(toggle()!)
    expect(toggle()!.getAttribute('aria-pressed')).toBe('false')
    expect(q('fbs-wb-rejected-kiz-header')).toBeNull()
    expect(visibleIds()).toEqual([...IDS])
    expect(rowsStack().querySelectorAll(':scope > hr')).toHaveLength(IDS.length - 1)
  })

  it('R2: клик по треугольнику не забирает фокус у поля скана', async () => {
    await open()
    const input = q('fbs-unified-scan')!.querySelector<HTMLInputElement>('input[data-packing-scan="true"]')!
    act(() => input.focus())
    const down = new MouseEvent('mousedown', { bubbles: true, cancelable: true })
    act(() => { toggle()!.dispatchEvent(down) })
    expect(down.defaultPrevented).toBe(true)
    expect(toggle()!.tabIndex).toBe(-1)
    expect(document.activeElement).toBe(input)
  })

  // R5 выполняет сценарий дважды (без фильтра и с фильтром) с полным
  // перемонтированием воркспейса между прогонами. В CI-прогоне GitHub Actions
  // 37139806128 (.agent-runs/wms652/ci-frontend-first.log) этот тест упёрся в
  // дефолт 5 с (измерено 5514 мс), после чего из-за утечки act() попадали
  // соседние тесты файла. Поднимаем предел harness-ожидания до 20 с —
  // инфраструктурный запас, а не ослабление продуктовой проверки: ожидания
  // результата не изменены. Полный CI должен подтвердить, что соседние три
  // падения были следствием именно этого таймаута.
  it('R5: скан в фильтре — тот же обработчик; строка скана зелёная сверху, отклонённая WB уходит к красным', { timeout: 20_000 }, async () => {
    const run = async (filter: boolean) => {
      await open()
      if (filter) click(toggle()!)
      calls = []
      verdictOnCommit = { 'order-c': 'rejected' }
      scan(STICKER['order-c'])
      await settle(60)
      scan(KIZ)
      await settle(120)
      return calls.filter((call) => call.includes('/kiz/'))
    }
    const plain = await run(false)
    act(() => root.unmount())
    root = createRoot(host)
    marks = { 'order-a': 'rejected', 'order-b': 'accepted', 'order-c': 'missing', 'order-d': 'rejected' }
    const filtered = await run(true)
    expect(filtered).toEqual(plain)
    expect(filtered).toEqual([
      'GET /operations/fbs-orders/kiz/lookup', 'POST /operations/fbs-orders/kiz/validate', 'POST /operations/fbs-orders/kiz/commit',
    ])

    // WB отклонил только что отсканированный: он зелёный сверху, N вырос, шапка под ним.
    expect(greenId()).toBe('order-c')
    expect(toggle()!.textContent).toBe('3')
    expect(listOrder()).toEqual(['order-c', 'fbs-wb-rejected-kiz-header', 'order-a', 'order-d'])

    // Следующий скан: B (принят) становится зелёным, C остаётся среди красных.
    scan(STICKER['order-b'])
    await settle(60)
    expect(greenId()).toBe('order-b')
    expect(listOrder()).toEqual(['order-b', 'fbs-wb-rejected-kiz-header', 'order-a', 'order-c', 'order-d'])
    expect(toggle()!.getAttribute('aria-pressed')).toBe('true')
  })

  it('R6/R7: новый КИЗ в поле красной строки, WB принял — строка ушла; N = 0 выключает фильтр', async () => {
    marks = { 'order-a': 'rejected', 'order-b': 'accepted', 'order-c': 'missing', 'order-d': 'accepted' }
    verdictOnCommit = { 'order-a': 'accepted' }
    await open()
    click(toggle()!)
    expect(listOrder()).toEqual(['fbs-wb-rejected-kiz-header', 'order-a'])
    const field = document.querySelector<HTMLElement>('[data-order-id="order-a"] [data-testid="fbs-kiz-row-input"]') as HTMLInputElement
    act(() => field.focus())
    scan(KIZ)
    await settle(150)
    expect(calls).toContain('POST /operations/fbs-orders/kiz/commit')
    expect(toggle()).toBeNull()
    expect(q('fbs-wb-rejected-kiz-header')).toBeNull()
    expect(visibleIds()).toEqual([...IDS])
  })

  it('R10/R11: одно «Назад» откатывает весь скан — КИЗ снят, выбора нет, хвост ушёл из строки сразу', async () => {
    marks = { 'order-a': 'accepted', 'order-b': 'missing', 'order-c': 'missing', 'order-d': 'accepted' }
    await open()
    scan(STICKER['order-c'])
    await settle(60)
    scan(KIZ)
    await settle(120)
    const tail = () => document.querySelector<HTMLElement>('[data-order-id="order-c"]')!.dataset.kizTail
    expect(tail()).toBe(KIZ.slice(-8))
    expect(q('fbs-kiz-scan-active')).toBeNull()

    calls = []
    act(() => q('fbs-scan-undo')!.click())
    await settle(60)
    // Существующий серверный откат, один вызов; заказ заново не выбирается.
    expect(undoBodies).toHaveLength(1)
    expect(undoBodies[0]).toMatchObject({ order_id: 'order-c' })
    expect(calls.filter((call) => call.includes('/kiz/'))).toEqual([])
    expect(q('fbs-kiz-scan-active')).toBeNull()
    const scanInput = q('fbs-unified-scan')!.querySelector<HTMLInputElement>('input[data-packing-scan="true"]')!
    expect(scanInput.placeholder).toBe('Сканируйте штрихкод товара')
    expect(scanInput.value).toBe('')
    // R11: хвост снятого КИЗ не висит до следующего опроса.
    expect(tail()).toBe('')
    // Откатывать больше нечего — кнопка неактивна.
    expect((q('fbs-scan-undo') as HTMLButtonElement).disabled).toBe(true)
  })

  it('C10: рамка сборки — фильтр общий, шапка только у назначенной поставки, зелёная только у поднятой', async () => {
    const packingHost = document.createElement('div')
    document.body.appendChild(packingHost)
    const frame = (rejectedFilter: { active: boolean; count: number; headerSupplyId: string | null }, promotedSupplyId: string | null) => (
      <FfFbsSupplyWorkspace token="t-636" authHeaders={() => ({ Authorization: 'Bearer t-636' })} supplyId={SUPPLY_ID}
        initialWorkspace={workspace()} open onClose={() => undefined}
        assemblyFrame={{
          stage: 'packing', packingHost, registerScanner: () => undefined, promotedSupplyId, rejectedFilter,
          active: false, expanded: false, visible: true, onToggleExpanded: () => undefined, onActivate: () => undefined,
          onDeactivate: () => undefined, onWorkspaceChange: () => undefined, registerEscape: () => undefined,
        }} />
    )
    const shown = () => [...packingHost.querySelectorAll<HTMLElement>('[data-order-id], [data-testid="fbs-wb-rejected-kiz-header"]')]
      .filter((node) => getComputedStyle(node).display !== 'none')
      .map((node) => node.dataset.orderId ?? node.dataset.testid)
    await act(async () => root.render(frame({ active: false, count: 5, headerSupplyId: SUPPLY_ID }, null)))
    await settle(50)
    expect(shown()).toEqual([...IDS])
    // Треугольник рамки не рисует: он в общей полосе скана сборки.
    expect(toggle()).toBeNull()
    await act(async () => root.render(frame({ active: true, count: 5, headerSupplyId: SUPPLY_ID }, null)))
    await settle(20)
    expect(shown()).toEqual(['fbs-wb-rejected-kiz-header', 'order-a', 'order-d'])
    expect(q('fbs-wb-rejected-kiz-header')!.textContent).toContain('· 5')
    await act(async () => root.render(frame({ active: true, count: 5, headerSupplyId: 'other-supply' }, 'other-supply')))
    await settle(20)
    expect(shown()).toEqual(['order-a', 'order-d'])
    packingHost.remove()
  })
})
