// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'
import { saveFbsAssemblyStage } from './fbsSupplyAssembly'
import { saveFbsScanPrintPreferences } from './fbsScanAutoPrint'
import { saveLabelSizeId } from '../../utils/labelSize'

const { fetchWorkspace, openMarkingPrint, dispatchPreparedQr } = vi.hoisted(() => ({
  fetchWorkspace: vi.fn(),
  openMarkingPrint: vi.fn(),
  dispatchPreparedQr: vi.fn(),
}))

vi.mock('./fbsApi', async (importOriginal) => ({
  ...await importOriginal<typeof import('./fbsApi')>(),
  fetchFbsWorkspace: fetchWorkspace,
}))
vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
vi.mock('../../utils/useMarkingCodePrint', () => ({
  useMarkingCodePrint: () => ({ openPrint: openMarkingPrint, dialog: null }),
}))
vi.mock('../../utils/printPreparedQr', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../utils/printPreparedQr')>(),
  dispatchPreparedQrInKiosk: dispatchPreparedQr,
}))
vi.mock('../../utils/czLabelPng', () => ({
  renderCzLabelPng: vi.fn(async () => 'data:image/png;base64,WMS666'),
}))
vi.mock('./FfFbsAssemblyPick', () => ({ FfFbsAssemblyPick: () => null }))
vi.mock('./FbsSupplyHistoryDialog', () => ({ FbsSupplyHistoryDialog: () => null }))
vi.mock('./FbsPrintPreviewDialog', () => ({ FbsPrintPreviewDialog: () => null }))
vi.mock('./FbsTransferSupplyDialog', () => ({
  FbsTransferSupplyDialog: () => null,
  makeFbsTransferSupplyDeps: () => ({}),
}))

const TOKEN = 'wms-666'
const WB_BARCODE = '4606660000001'
const OZON_POSITION_BARCODE = 'OZON-POS-666-A'
const authHeaders = () => ({ Authorization: 'Bearer wms-666' })

type RecordedCall = { method: string; path: string; body: unknown }
let calls: RecordedCall[]
let state: Record<string, FbsWorkspace>
let wbScanOrderQueue: Record<string, string[]>
let wbScanNeedsKiz: boolean
let ozonLookupOrderIds: Record<string, string>
let deferredStartSupplyIds: Set<string>
let releaseDeferredStart: Record<string, (() => void) | undefined>
let root: Root
let host: HTMLDivElement
const originalFetch = globalThis.fetch

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const ozonLookupKey = (supplyId: string, code: string) => `${supplyId}\u0000${code}`

function order(supplyId: string, marketplace: 'wb' | 'ozon') {
  const ozon = marketplace === 'ozon'
  return {
    id: `${supplyId}-order`,
    marketplace,
    external_order_id: ozon ? 'OZON-POSTING-666' : null,
    wb_order_id: ozon ? -666 : 666001,
    status: 'assembling', wb_status: 'confirm', supplier_status: 'confirm',
    seller: { id: `${supplyId}-seller`, name: `Селлер ${supplyId}` },
    wb_warehouse: { id: 507, name: 'Коледино' },
    wms_warehouse: { id: 'warehouse-666', name: 'Основной склад' },
    product: {
      id: `${supplyId}-product-a`, name: ozon ? 'Футболка Ozon, позиция A' : 'Футболка WB',
      image_url: null, seller_article: ozon ? 'OZ-A' : 'WB-A', wb_article: ozon ? null : 666001,
      barcode: ozon ? OZON_POSITION_BARCODE : WB_BARCODE, sku: ozon ? 'OZ-SKU-A' : 'WB-SKU-A',
      chrt_id: ozon ? null : 666001, category: 'Одежда', color: 'синий', size: 'M',
      marketplace_bindings: [{ marketplace, external_barcodes: [ozon ? OZON_POSITION_BARCODE : WB_BARCODE] }],
    },
    positions: ozon ? [
      {
        id: `${supplyId}-position-a`, product_id: `${supplyId}-product-a`, name: 'Футболка Ozon, позиция A',
        image_url: null, seller_article: 'OZ-A', sku: 'OZ-SKU-A', size: 'M', color: 'синий',
        barcode: OZON_POSITION_BARCODE,
        marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: [OZON_POSITION_BARCODE] }],
        quantity: 1, reserved_quantity: 1, picked_quantity: 1,
      },
      {
        id: `${supplyId}-position-b`, product_id: `${supplyId}-product-b`, name: 'Брюки Ozon, позиция B',
        image_url: null, seller_article: 'OZ-B', sku: 'OZ-SKU-B', size: 'L', color: 'чёрный',
        barcode: 'OZON-POS-666-B',
        marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: ['OZON-POS-666-B'] }],
        quantity: 1, reserved_quantity: 1, picked_quantity: 1,
      },
    ] : [],
    inventory: { available_unpacked: 2, locations: [] },
    buyer_type: 'individual', cargo_type: 'mgt', can_pvz: false,
    delivery_route: ozon ? 'Ozon Логистика' : null,
    metadata: {
      required: [], optional: [], states: [], delivery_allowed: true, last_checked_at: null,
    },
    sticker: { code: ozon ? 'OZON-POSTING-666' : '666001 0001', status: 'ready', asset_url: null, applied_at: null },
    pick: { status: 'picked', location_code: 'A-01-01', picked_at: null },
    pack: { status: 'pending', packed_at: null },
    created_at_wb: '2026-10-05T08:00:00Z', deadline_at: '2026-10-06T08:00:00Z',
    supply_id: supplyId, selection_blockers: [], tape_order_index: 0,
  }
}

function workspace(id: string, marketplace: 'wb' | 'ozon', task = `task-${id}`): FbsWorkspace {
  return {
    supply: {
      id, marketplace, wb_supply_id: marketplace === 'wb' ? `WB-GI-${id}` : null,
      source: 'wms', name: `${marketplace.toUpperCase()} ${id}`, status: 'assembling',
      delivery_type: 'warehouse_sc', seller: { id: `${id}-seller`, name: `Селлер ${id}` },
      wb_warehouse: { id: 507, name: 'Коледино' },
      wms_warehouse: { id: 'warehouse-666', name: 'Основной склад' },
      planned_destination: null, planned_shipment_date: null, nearest_deadline_at: '2026-10-06T08:00:00Z',
      packaging_task_id: task, barcode_asset: null,
    },
    stage: 'packing',
    progress: { picked: 1, packed: 0, metadata_ready: 0, stickers_ready: 1, total: 1 },
    blockers: [], orders: [order(id, marketplace)], cargo_places: [],
    boxes: [{
      id: `${id}-box`, box_number: 1, barcode: `${id}-BOX-1`, assigned_order_ids: [],
      assigned_order_product_ids: [], trbx_id: null, wb_trbx_id: null, qr_asset: null,
      without_distribution: false,
    }],
    delivery_preflight: null, last_wb_sync_at: null, server_now: '2026-10-05T08:00:00Z',
  } as unknown as FbsWorkspace
}

function packagingTask(supplyId: string) {
  const current = state[supplyId]!
  return {
    id: current.supply.packaging_task_id, document_number: supplyId, display_number: supplyId,
    status: 'in_progress',
    lines: current.orders.flatMap((one) => {
      const productIds = one.positions.length
        ? one.positions.map((position) => position.product_id).filter(Boolean)
        : [one.product.id]
      return productIds.map((productId, index) => ({
        id: `${supplyId}-line-${index}`, product_id: productId, sku_code: one.product.sku,
        product_name: one.positions[index]?.name ?? one.product.name, requires_honest_sign: false,
        packaging_instructions: '', qty_total: 1, qty_need_pack: 1, marking_available_count: 0,
      }))
    }),
  }
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

async function server(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = typeof init?.body === 'string' ? JSON.parse(init.body) : null
  const path = url.pathname.replace(/^\/api/, '')
  calls.push({ method, path: `${path}${url.search}`, body })

  const task = path.match(/^\/operations\/packaging-tasks\/(task-[^/]+)$/)
  if (task && method === 'GET') return json(packagingTask(task[1]!.slice(5)))
  if (/^\/operations\/packaging-tasks\/task-[^/]+\/lines\/[^/]+\/pack$/.test(path)) return json({})

  const start = path.match(/^\/operations\/fbs-supplies\/([^/]+)\/start-work$/)
  if (start) {
    const next = state[start[1]!]!
    const complete = () => {
      next.supply.packaging_task_id ??= `task-${start[1]}`
      return json(clone(next))
    }
    if (deferredStartSupplyIds.has(start[1]!)) {
      return new Promise<Response>((resolve) => {
        releaseDeferredStart[start[1]!] = () => resolve(complete())
      })
    }
    return complete()
  }

  const scan = path.match(/^\/operations\/fbs-supplies\/([^/]+)\/scan-auto-print$/)
  if (scan) {
    const supplyId = scan[1]!
    const barcode = (body as { barcode?: string } | null)?.barcode
    if (!supplyId.startsWith('wb') || barcode !== WB_BARCODE) {
      return json({ detail: { code: 'scan_product_not_found', message: 'Товар не найден' } }, 404)
    }
    const queuedOrderId = wbScanOrderQueue[supplyId]?.shift()
    const selectedOrder = state[supplyId]!.orders.find((one) => one.id === queuedOrderId)
      ?? state[supplyId]!.orders[0]!
    return json({
      scan_id: `scan-${calls.length}`, order_id: selectedOrder.id, wb_order_id: selectedOrder.wb_order_id,
      replayed: false, binding_target: null, reprint_recovery: null, requires_honest_sign: wbScanNeedsKiz,
      qr_asset: {
        id: `qr-${selectedOrder.id}`, kind: 'order_sticker', status: 'ready', content_type: 'image/png',
        width_mm: 58, height_mm: 40, preview_url: '/assets/wms666-wb.png', download_url: null,
        checksum: null, applied_at: null, error: null,
      },
      codes: [], printed_codes: wbScanNeedsKiz ? [{
        id: `code-${selectedOrder.id}`, cis_code: `cis-${selectedOrder.id}`,
        has_label_artifact: false, order_product_id: null,
      }] : [], shortage: 0, order_errors: [],
    })
  }

  if (path === '/operations/fbs-orders/kiz/lookup') {
    const supplyId = url.searchParams.get('supply_id')!
    const sticker = url.searchParams.get('sticker')!
    const orderId = ozonLookupOrderIds[ozonLookupKey(supplyId, sticker)]
    const found = state[supplyId]?.orders.find((one) => one.id === orderId)
    if (supplyId.startsWith('ozon') && found) {
      return json({
        order_id: found.id, wb_order_id: found.wb_order_id,
        product: { name: found.product.name, image_url: null, barcode: found.product.barcode, seller_article: found.product.seller_article },
        current_kiz: null, needs_confirmation: false, can_bind: true, block_reason: null,
        requires_honest_sign: false,
      })
    }
    return json({ detail: { code: 'sticker_not_found', message: 'Стикер не найден' } }, 404)
  }

  const assign = path.match(/^\/operations\/fbs-supplies\/([^/]+)\/boxes\/([^/]+)\/orders$/)
  if (assign) {
    const next = state[assign[1]!]!
    const box = next.boxes.find((one) => one.id === assign[2])!
    const payload = body as { order_ids: string[]; order_product_ids?: string[] }
    box.assigned_order_ids = [...new Set([...box.assigned_order_ids, ...payload.order_ids])]
    box.assigned_order_product_ids = [...new Set([...(box.assigned_order_product_ids ?? []), ...(payload.order_product_ids ?? [])])]
    if (payload.order_product_ids?.length) {
      const orderId = next.orders.find((one) => one.positions.some((position) => payload.order_product_ids!.includes(position.id!)))?.id
      if (orderId) box.assigned_order_ids = [...new Set([...box.assigned_order_ids, orderId])]
    }
    return json(clone(next))
  }

  if (path.includes('/scan-auto-print/') && path.endsWith('/print-claim')) return json({ claimed: true, started: false })
  if (path.includes('/scan-auto-print/') && path.endsWith('/print-started')) return json({ claimed: false, started: true })
  if (path === '/assets/wms666-wb.png') return new Response(new Blob(['png'], { type: 'image/png' }))
  return json({ detail: { code: 'unexpected_test_request', message: `${method} ${path}` } }, 404)
}

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})

beforeEach(() => {
  calls = []
  wbScanOrderQueue = {}
  wbScanNeedsKiz = false
  ozonLookupOrderIds = {}
  deferredStartSupplyIds = new Set()
  releaseDeferredStart = {}
  state = {
    'wb-a': workspace('wb-a', 'wb'),
    'wb-b': workspace('wb-b', 'wb'),
    'wb-new': workspace('wb-new', 'wb', null as unknown as string),
    'ozon-a': workspace('ozon-a', 'ozon'),
    'ozon-b': workspace('ozon-b', 'ozon'),
  }
  ozonLookupOrderIds[ozonLookupKey('ozon-a', OZON_POSITION_BARCODE)] = 'ozon-a-order'
  ozonLookupOrderIds[ozonLookupKey('ozon-b', OZON_POSITION_BARCODE)] = 'ozon-b-order'
  state['wb-new']!.supply.packaging_task_id = null
  fetchWorkspace.mockReset().mockImplementation(async (_token, _headers, id: string) => clone(state[id]!))
  openMarkingPrint.mockReset().mockResolvedValue(undefined)
  dispatchPreparedQr.mockReset().mockResolvedValue(undefined)
  window.sessionStorage.clear()
  window.localStorage.clear()
  globalThis.fetch = server as typeof fetch
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  document.body.innerHTML = ''
  globalThis.fetch = originalFetch
})

async function settleUntil(ready: () => boolean, timeoutMs = 2_000) {
  const deadline = Date.now() + timeoutMs
  while (!ready() && Date.now() < deadline) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  }
}

async function renderAssembly(ids: string[]) {
  saveFbsAssemblyStage(ids, 'packing', window.sessionStorage)
  await act(async () => root.render(
    <FfFbsSupplyAssembly token={TOKEN} authHeaders={authHeaders} supplyIds={ids} open onClose={() => undefined} />,
  ))
  await settleUntil(() => ids.every((id) => document.querySelector(`[data-order-id="${id}-order"]`)))
}

async function renderSupply(id: string) {
  window.sessionStorage.setItem(`wms:fbs:${id}:stage`, 'packing')
  await act(async () => root.render(
    <FfFbsSupplyWorkspace token={TOKEN} authHeaders={authHeaders} supplyId={id} open onClose={() => undefined} />,
  ))
  await settleUntil(() => Boolean(document.querySelector(`[data-order-id="${id}-order"]`)))
}

function physicalScan(code: string) {
  act(() => {
    ;(document.activeElement as HTMLElement | null)?.blur()
    for (const key of code) document.body.dispatchEvent(new KeyboardEvent('keydown', { key, code: 'KeyA', bubbles: true, cancelable: true }))
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
}

const textCount = (text: string) => (document.body.textContent?.split(text).length ?? 1) - 1

describe('WMS-666 C1/C2/C3: the same packing surface in every entry', () => {
  it.each([
    ['supply_id=A', 'single'] as const,
    ['supply_ids=A', 'assembly-one'] as const,
    ['supply_ids=A,B', 'assembly-many'] as const,
  ])('%s renders one shared strip/list with the complete saved settings', async (_name, entry) => {
    saveFbsScanPrintPreferences(TOKEN, {
      printQr: true, printChz: true, reprintChz: false, printChzCopies: 4, reprintChzCopies: 3,
    })
    saveLabelSizeId('60x80')
    if (entry === 'single') await renderSupply('wb-a')
    else await renderAssembly(entry === 'assembly-one' ? ['wb-a'] : ['wb-a', 'wb-b'])

    expect(document.querySelectorAll('[data-testid="fbs-unified-scan"]')).toHaveLength(1)
    expect(document.querySelectorAll('[data-testid="fbs-unified-packing-rows"]')).toHaveLength(1)
    expect(document.querySelectorAll('[data-order-id]')).toHaveLength(entry === 'assembly-many' ? 2 : 1)
    expect(textCount('Начать работу с поставкой')).toBe(0)
    expect(textCount('Завершить работу с поставкой')).toBe(0)
    expect(document.querySelector('[data-active]')).toBeNull()

    const qr = document.querySelector<HTMLInputElement>('[data-testid="fbs-scan-print-qr-toggle"] input')
    expect(qr?.checked).toBe(true)
    expect(qr?.disabled).toBe(false)
    expect(document.querySelector<HTMLInputElement>('[data-testid="fbs-scan-print-chz-toggle"] input')?.checked).toBe(true)
    expect(document.querySelector('[data-testid="fbs-kiz-auto-reprint-toggle"]')).not.toBeNull()
    expect(document.querySelector('[data-testid="fbs-scan-print-chz-copies-value"]')?.textContent).toBe('4')
    expect(document.querySelector<HTMLInputElement>('[data-testid="label-size-select-input"]')?.value).toBe('60x80')
  })

  it('starts or reuses one packaging task without a button and continues the same first scan', async () => {
    saveFbsScanPrintPreferences(TOKEN, { printQr: false, printChz: true, reprintChz: false })
    await renderSupply('wb-new')
    expect(textCount('Начать работу с поставкой')).toBe(0)

    physicalScan(WB_BARCODE)
    physicalScan(WB_BARCODE)
    await settleUntil(() => calls.filter((call) => call.path.endsWith('/start-work')).length > 0, 500)

    expect(calls.filter((call) => call.path.endsWith('/start-work'))).toHaveLength(1)
    await settleUntil(() => calls.filter((call) => call.path.endsWith('/scan-auto-print')).length === 2, 1_000)
    expect(calls.filter((call) => call.path.endsWith('/scan-auto-print'))).toHaveLength(2)
  })
})

describe('WMS-666 C4/C8: real Ozon workspace inside FfFbsSupplyAssembly', () => {
  it('keeps the shared settings visible, forces only order QR off, and preserves Ozon position labels', async () => {
    saveFbsScanPrintPreferences(TOKEN, {
      printQr: true, printChz: true, reprintChz: false, printChzCopies: 2,
    })
    saveLabelSizeId('70x120')
    await renderAssembly(['ozon-a'])

    expect(document.querySelectorAll('[data-testid="fbs-unified-scan"]')).toHaveLength(1)
    const qr = document.querySelector<HTMLInputElement>('[data-testid="fbs-scan-print-qr-toggle"] input')!
    expect(qr).not.toBeNull()
    expect(qr.checked).toBe(false)
    expect(qr.disabled).toBe(true)
    expect(document.querySelector<HTMLInputElement>('[data-testid="fbs-scan-print-chz-toggle"] input')?.checked).toBe(true)
    expect(document.querySelector('[data-testid="fbs-kiz-auto-reprint-toggle"]')).not.toBeNull()
    expect(document.querySelector('[data-testid="fbs-scan-print-chz-copies-value"]')?.textContent).toBe('2')
    expect(document.querySelector<HTMLInputElement>('[data-testid="label-size-select-input"]')?.value).toBe('70x120')
    expect(document.body.textContent).toContain('OZON-POSTING-666')
    expect(document.body.textContent).toContain('Футболка Ozon, позиция A')
    expect(document.body.textContent).toContain(OZON_POSITION_BARCODE)
    expect(document.body.textContent).toContain('Брюки Ozon, позиция B')
    expect(textCount('Начать работу с поставкой')).toBe(0)
    expect(textCount('Завершить работу с поставкой')).toBe(0)

    const printAll = [...document.querySelectorAll<HTMLButtonElement>('button')]
      .find((button) => button.textContent === 'Печать всего (1)')!
    await act(async () => printAll.click())
    expect(openMarkingPrint).toHaveBeenCalledTimes(1)
    const printedPayload = JSON.stringify(openMarkingPrint.mock.calls[0])
    expect(printedPayload).toContain('Футболка Ozon, позиция A')
    expect(printedPayload).toContain('Брюки Ozon, позиция B')
    expect(printedPayload).toContain(OZON_POSITION_BARCODE)
    expect(printedPayload).not.toContain('666001')
    expect(calls.filter((call) => call.path.includes('/scan-auto-print'))).toHaveLength(0)

    // Opening Ozon must not erase the saved WB preference.
    await act(async () => root.render(
      <FfFbsSupplyAssembly token={TOKEN} authHeaders={authHeaders} supplyIds={['wb-a']} open onClose={() => undefined} />,
    ))
    saveFbsAssemblyStage(['wb-a'], 'packing', window.sessionStorage)
    await settleUntil(() => Boolean(document.querySelector('[data-order-id="wb-a-order"]')))
    const restored = document.querySelector<HTMLInputElement>('[data-testid="fbs-scan-print-qr-toggle"] input')!
    expect(restored.checked).toBe(true)
    expect(restored.disabled).toBe(false)
  })

  it('routes a position barcode into the open Ozon box with order_product_ids only', async () => {
    saveFbsScanPrintPreferences(TOKEN, { printQr: true, printChz: false, reprintChz: false })
    await renderAssembly(['ozon-a'])
    // Compatibility only for proving the old branch fails for the payload reason.
    const legacyStart = document.querySelector<HTMLButtonElement>('[data-testid="fbs-assembly-supply-start-ozon-a"]')
    if (legacyStart) {
      await act(async () => legacyStart.click())
      await settleUntil(() => Boolean(document.querySelector('[data-testid="fbs-kiz-scan-input"]')))
    }
    physicalScan(OZON_POSITION_BARCODE)
    await settleUntil(() => calls.some((call) => /\/boxes\/[^/]+\/orders$/.test(call.path)))

    const assignment = calls.find((call) => /\/boxes\/[^/]+\/orders$/.test(call.path))
    expect(assignment?.body).toEqual({
      order_ids: [],
      order_product_ids: ['ozon-a-position-a'],
    })
    expect(document.body.textContent).not.toContain('ozon_order_positions_required')
    expect(calls.filter((call) => call.path.includes('/scan-auto-print'))).toHaveLength(0)
    expect(dispatchPreparedQr).not.toHaveBeenCalled()
  })
})

describe('WMS-666 C5: mixed WB and Ozon scan ownership', () => {
  it('processes WB → Ozon → WB once each, prints QR only for WB, and never needs an active frame', async () => {
    const secondWbOrder = clone(state['wb-a']!.orders[0]!)
    secondWbOrder.id = 'wb-a-order-2'
    secondWbOrder.wb_order_id = 666002
    secondWbOrder.sticker.code = '666002 0001'
    state['wb-a']!.orders.push(secondWbOrder)
    state['wb-a']!.progress = { ...state['wb-a']!.progress, picked: 2, stickers_ready: 2, total: 2 }
    wbScanOrderQueue['wb-a'] = ['wb-a-order', 'wb-a-order-2']
    saveFbsScanPrintPreferences(TOKEN, { printQr: true, printChz: false, reprintChz: false })
    await renderAssembly(['wb-a', 'ozon-a'])

    physicalScan(WB_BARCODE)
    await settleUntil(() => calls.filter((call) => call.path.endsWith('/scan-auto-print')).length === 1, 1_000)
    await settleUntil(() => dispatchPreparedQr.mock.calls.length === 1, 1_000)
    physicalScan(OZON_POSITION_BARCODE)
    await settleUntil(() => calls.some((call) => /\/boxes\/[^/]+\/orders$/.test(call.path)), 500)
    expect(calls.some((call) => /\/boxes\/[^/]+\/orders$/.test(call.path))).toBe(true)
    physicalScan(WB_BARCODE)
    await settleUntil(() => calls.filter((call) => call.path.endsWith('/scan-auto-print')).length === 2, 1_000)
    await settleUntil(() => dispatchPreparedQr.mock.calls.length === 2, 1_000)

    const wbScans = calls.filter((call) => call.path.endsWith('/scan-auto-print'))
    expect(wbScans).toHaveLength(2)
    expect(wbScans.map((call) => call.body)).toEqual([
      expect.objectContaining({ barcode: WB_BARCODE, print_qr: true }),
      expect.objectContaining({ barcode: WB_BARCODE, print_qr: true }),
    ])
    expect(calls.filter((call) => call.path.startsWith('/operations/fbs-orders/kiz/lookup?supply_id=ozon-a'))).toHaveLength(1)
    expect(dispatchPreparedQr).toHaveBeenCalledTimes(2)
    expect(new Set(dispatchPreparedQr.mock.calls.map(([request]) => request.idempotencyKey)).size).toBe(2)
    expect(textCount('Начать работу с поставкой')).toBe(0)
    expect(document.querySelector('[role="alert"]')?.textContent ?? '').not.toContain('QR')
  })
})

describe('WMS-666 review regressions: live settings and Ozon routing', () => {
  it('uses the visible standalone WB settings changed immediately before the physical scan', async () => {
    saveFbsScanPrintPreferences(TOKEN, {
      printQr: false, printChz: false, reprintChz: false, printChzCopies: 1,
    })
    wbScanNeedsKiz = true
    await renderSupply('wb-a')

    const scanBar = document.querySelector<HTMLElement>('[data-testid="fbs-unified-scan"]')!
    const qr = scanBar.querySelector<HTMLInputElement>('[data-testid="fbs-scan-print-qr-toggle"] input')!
    const chz = scanBar.querySelector<HTMLInputElement>('[data-testid="fbs-scan-print-chz-toggle"] input')!
    await act(async () => qr.click())
    await act(async () => chz.click())
    await settleUntil(() => Boolean(scanBar.querySelector('[data-testid="fbs-scan-print-chz-copies-plus"]')))
    await act(async () => scanBar.querySelector<HTMLButtonElement>('[data-testid="fbs-scan-print-chz-copies-plus"]')!.click())
    expect(qr.checked).toBe(true)
    expect(chz.checked).toBe(true)
    expect(scanBar.querySelector('[data-testid="fbs-scan-print-chz-copies-value"]')?.textContent).toBe('2')

    physicalScan(WB_BARCODE)
    await settleUntil(() => calls.some((call) => call.path.endsWith('/scan-auto-print')), 1_000)
    const request = calls.find((call) => call.path.endsWith('/scan-auto-print'))
    expect(request?.body).toEqual(expect.objectContaining({
      barcode: WB_BARCODE, print_qr: true, print_chz: true,
    }))
    await settleUntil(() => dispatchPreparedQr.mock.calls.length === 3, 1_000)
    expect(dispatchPreparedQr).toHaveBeenCalledTimes(3)
  })

  it('maps an Ozon position barcode to the posting lookup while boxing only the scanned position', async () => {
    delete ozonLookupOrderIds[ozonLookupKey('ozon-a', OZON_POSITION_BARCODE)]
    ozonLookupOrderIds[ozonLookupKey('ozon-a', 'OZON-POSTING-666')] = 'ozon-a-order'
    saveFbsScanPrintPreferences(TOKEN, { printQr: true, printChz: false, reprintChz: false })
    await renderAssembly(['ozon-a'])

    physicalScan(OZON_POSITION_BARCODE)
    await settleUntil(() => calls.some((call) => /\/boxes\/[^/]+\/orders$/.test(call.path)), 750)

    const lookups = calls.filter((call) => call.path.startsWith('/operations/fbs-orders/kiz/lookup?supply_id=ozon-a'))
    expect(lookups.map((call) => new URL(call.path, 'http://wms.test').searchParams.get('sticker')))
      .toEqual(['OZON-POSTING-666'])
    expect(calls.find((call) => /\/boxes\/[^/]+\/orders$/.test(call.path))?.body).toEqual({
      order_ids: [], order_product_ids: ['ozon-a-position-a'],
    })
    expect(dispatchPreparedQr).not.toHaveBeenCalled()
  })

  it('drops a delayed Ozon start-work continuation when the standalone screen has moved from A to B', async () => {
    state['ozon-a']!.supply.packaging_task_id = null
    deferredStartSupplyIds.add('ozon-a')
    await renderSupply('ozon-a')

    physicalScan(OZON_POSITION_BARCODE)
    await settleUntil(() => Boolean(releaseDeferredStart['ozon-a']), 750)
    await renderSupply('ozon-b')
    await act(async () => {
      releaseDeferredStart['ozon-a']?.()
      await new Promise((resolve) => setTimeout(resolve, 80))
    })

    expect(calls.filter((call) => call.path.startsWith('/operations/fbs-orders/kiz/lookup?supply_id=ozon-b'))).toHaveLength(0)
    expect(calls.filter((call) => call.path.startsWith('/operations/fbs-supplies/ozon-b/boxes/'))).toHaveLength(0)
  })

  it('lets an unknown child Ozon posting number reach the server lookup and complete its order action', async () => {
    const childPosting = 'OZON-CHILD-POSTING-666'
    ozonLookupOrderIds[ozonLookupKey('ozon-a', childPosting)] = 'ozon-a-order'
    await renderAssembly(['ozon-a'])

    physicalScan(childPosting)
    await settleUntil(() => calls.some((call) => /\/boxes\/[^/]+\/orders$/.test(call.path)), 750)

    const lookup = calls.find((call) => call.path.startsWith('/operations/fbs-orders/kiz/lookup?supply_id=ozon-a'))
    expect(lookup && new URL(lookup.path, 'http://wms.test').searchParams.get('sticker')).toBe(childPosting)
    expect(calls.some((call) => /\/operations\/fbs-supplies\/ozon-a\/boxes\/[^/]+\/orders$/.test(call.path))).toBe(true)
  })

  it('releases an unmarked boxless Ozon scan so the next mixed physical scan reaches WB without Escape', async () => {
    state['ozon-a']!.boxes = []
    saveFbsScanPrintPreferences(TOKEN, { printQr: false, printChz: false, reprintChz: false })
    await renderAssembly(['ozon-a', 'wb-a'])

    physicalScan(OZON_POSITION_BARCODE)
    await settleUntil(() => calls.some((call) => call.path.startsWith('/operations/fbs-orders/kiz/lookup?supply_id=ozon-a')), 750)
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
    physicalScan(WB_BARCODE)
    await settleUntil(() => calls.some((call) => call.path.endsWith('/scan-auto-print')), 750)

    expect(calls.filter((call) => call.path.endsWith('/scan-auto-print'))).toHaveLength(1)
    expect(document.querySelector('[data-testid="fbs-kiz-scan-active"]')).toBeNull()
    expect(document.body.textContent).not.toContain('Откройте или создайте короб.')
  })
})
