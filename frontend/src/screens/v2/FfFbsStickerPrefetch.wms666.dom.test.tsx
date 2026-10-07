// @vitest-environment jsdom
// WMS-666: post-release regression guard. Mount real screens with initially missing stickers.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import { saveFbsAssemblyStage } from './fbsSupplyAssembly'
import type { FbsWorkspace } from './fbsApi'

const { fetchWorkspace, fetchBatch, printQr, printMarking } = vi.hoisted(() => ({
  fetchWorkspace: vi.fn(), fetchBatch: vi.fn(), printQr: vi.fn(), printMarking: vi.fn(),
}))
vi.mock('./fbsApi', async (original) => ({
  ...await original<typeof import('./fbsApi')>(),
  fetchFbsWorkspace: fetchWorkspace, fetchFbsPrintBatch: fetchBatch,
}))
vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
vi.mock('./FfFbsAssemblyPick', () => ({ FfFbsAssemblyPick: () => null }))
vi.mock('../../utils/useMarkingCodePrint', () => ({ useMarkingCodePrint: () => ({ openPrint: printMarking, dialog: null }) }))
vi.mock('../../utils/printPreparedQr', async (original) => ({ ...await original<typeof import('../../utils/printPreparedQr')>(), dispatchPreparedQrInKiosk: printQr }))
vi.mock('./FbsSupplyHistoryDialog', () => ({ FbsSupplyHistoryDialog: () => null }))
vi.mock('./FbsPrintPreviewDialog', () => ({ FbsPrintPreviewDialog: () => null }))
vi.mock('./FbsTransferSupplyDialog', () => ({ FbsTransferSupplyDialog: () => null, makeFbsTransferSupplyDeps: () => ({}) }))
const WB_BARCODE = '4606660000001'
const OZON_POSITION_BARCODE = 'OZON-POS-666-A'
const TOKEN = 'sticker-test'
const authHeaders = () => ({ Authorization: 'Bearer fixture' })
const clone = <T,>(value: T): T => structuredClone(value)
let state: Record<string, FbsWorkspace>
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

let host: HTMLDivElement
let root: Root
const originalFetch = globalThis.fetch
beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})
beforeEach(() => {
  window.sessionStorage.clear()
  window.localStorage.clear()
  state = { a: workspace('a', 'wb', null as unknown as string), b: workspace('b', 'wb', null as unknown as string) }
  for (const entry of Object.values(state)) {
    entry.supply.status = 'draft'
    entry.orders[0]!.sticker = { code: null, status: 'not_requested', asset_url: null, applied_at: null }
  }
  fetchWorkspace.mockReset().mockImplementation(async (_t, _h, id: string) => clone(state[id]!))
  fetchBatch.mockReset().mockImplementation(async (_t, _h, id: string, body: { order_ids: string[] }) => {
    for (const row of state[id]!.orders.filter((row) => body.order_ids.includes(row.id))) {
      row.sticker = { code: `5877994 ${id === 'a' ? '0283' : '0284'}`, status: 'ready', asset_url: `/operations/fbs-print-assets/${row.id}/content`, applied_at: null }
    }
    return { requested: body.order_ids.length, ready: body.order_ids.length, missing: 0, failed: 0, assets: [], order_errors: [] }
  })
  printQr.mockReset()
  printMarking.mockReset()
  globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(null), { headers: { 'Content-Type': 'application/json' } }))
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
async function settle() {
  for (let i = 0; i < 8; i++) await act(async () => { await new Promise((r) => setTimeout(r, 10)) })
}
async function render(mode: 'supply' | 'assembly', ids = ['a'], stage = 'packing') {
  if (mode === 'supply') {
    window.sessionStorage.setItem(`wms:fbs:${ids[0]}:stage`, stage)
    await act(async () => root.render(<FfFbsSupplyWorkspace token={TOKEN} authHeaders={authHeaders} supplyId={ids[0]!} open onClose={() => undefined} />))
  } else {
    saveFbsAssemblyStage(ids, 'packing', window.sessionStorage)
    await act(async () => root.render(<FfFbsSupplyAssembly token={TOKEN} authHeaders={authHeaders} supplyIds={ids} open onClose={() => undefined} />))
  }
  await settle()
}
it.each(['supply', 'assembly'] as const)('%s: opening a draft displays fetched WB sticker without scan, start-work or print', async (mode) => {
  await render(mode)
  expect(fetchBatch).toHaveBeenCalledTimes(1)
  expect(fetchBatch).toHaveBeenCalledWith(TOKEN, authHeaders, 'a', { kind: 'order_sticker', order_ids: ['a-order'], retry_missing: true })
  expect(document.querySelector('[data-order-id="a-order"] [data-testid="fbs-sticker-code"]')?.textContent).toBe('5877994 0283')
  expect(fetchWorkspace.mock.calls.length).toBeGreaterThanOrEqual(2)
  expect(state.a!.supply.packaging_task_id).toBeNull()
  expect(globalThis.fetch).not.toHaveBeenCalled()
  expect(printQr).not.toHaveBeenCalled()
  expect(printMarking).not.toHaveBeenCalled()
  await settle()
  expect(fetchBatch).toHaveBeenCalledTimes(1)
})
it('requests only missing orders and leaves existing sticker unchanged', async () => {
  const ready = clone(state.a!.orders[0]!)
  ready.id = 'already-ready'
  ready.sticker = { code: '1111111 9999', status: 'ready', asset_url: '/existing.png', applied_at: null }
  state.a!.orders.push(ready)
  await render('supply')
  expect(fetchBatch.mock.calls[0]?.[3].order_ids).toEqual(['a-order'])
  expect(document.querySelector('[data-order-id="already-ready"] [data-testid="fbs-sticker-code"]')?.textContent).toBe('1111111 9999')
})
it('opens two supplies in assembly and shows stickers in both', async () => {
  await render('assembly', ['a', 'b'])
  expect(fetchBatch).toHaveBeenCalledTimes(2)
  expect(document.querySelector('[data-order-id="a-order"] [data-testid="fbs-sticker-code"]')?.textContent).toBe('5877994 0283')
  expect(document.querySelector('[data-order-id="b-order"] [data-testid="fbs-sticker-code"]')?.textContent).toBe('5877994 0284')
})
it('does not request WB labels for Ozon', async () => {
  state.a = workspace('a', 'ozon', null as unknown as string)
  state.a.orders[0]!.sticker.code = null
  await render('supply')
  expect(fetchBatch).not.toHaveBeenCalled()
})
it('does not request labels from the composition tab', async () => {
  await render('supply', ['a'], 'composition')
  expect(fetchBatch).not.toHaveBeenCalled()
})
it('surfaces provider failure and does not loop or pretend the sticker exists', async () => {
  fetchBatch.mockResolvedValue({ requested: 1, ready: 0, missing: 0, failed: 1, assets: [], order_errors: [{ message: 'WB не вернул стикер' }] })
  await render('supply')
  expect(document.body.textContent).toContain('WB не вернул стикер')
  expect(document.querySelector('[data-testid="fbs-sticker-code"]')).toBeNull()
  expect(fetchBatch).toHaveBeenCalledTimes(1)
})
