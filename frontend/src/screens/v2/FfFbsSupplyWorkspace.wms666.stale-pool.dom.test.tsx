// @vitest-environment jsdom
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'

const { openPrint } = vi.hoisted(() => ({ openPrint: vi.fn() }))

vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
vi.mock('../../utils/useMarkingCodePrint', () => ({ useMarkingCodePrint: () => ({ openPrint, dialog: null }) }))
vi.mock('./FbsSupplyHistoryDialog', () => ({ FbsSupplyHistoryDialog: () => null }))
vi.mock('./FbsPrintPreviewDialog', () => ({ FbsPrintPreviewDialog: () => null }))
vi.mock('./FbsTransferSupplyDialog', () => ({ FbsTransferSupplyDialog: () => null, makeFbsTransferSupplyDeps: () => ({}) }))

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})

const SUPPLY_ID = 'supply-wms666-stale-count'
const ORDER_ID = 'order-wms666-stale-count'
const TASK_ID = 'task-wms666-stale-count'

function workspace(markingAvailableCount: number): FbsWorkspace {
  return {
    supply: {
      id: SUPPLY_ID, marketplace: 'wb', wb_supply_id: 'WB-GI-666', source: 'wms', name: 'Поставка WMS-666',
      status: 'assembling', delivery_type: 'warehouse_sc', seller: { id: 'seller-666', name: 'Продавец 666' },
      wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'warehouse-666', name: 'Основной склад' },
      planned_destination: null, planned_shipment_date: null, nearest_deadline_at: new Date().toISOString(),
      packaging_task_id: TASK_ID, barcode_asset: null,
    },
    stage: 'packing',
    progress: { picked: 1, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 1 },
    blockers: [],
    orders: [{
      id: ORDER_ID, marketplace: 'wb', external_order_id: null, wb_order_id: 666001,
      status: 'assembling', wb_status: 'confirm', supplier_status: 'confirm',
      seller: { id: 'seller-666', name: 'Продавец 666' },
      wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'warehouse-666', name: 'Основной склад' },
      product: {
        id: 'product-666', name: 'Товар с текущим ЧЗ', image_url: null, seller_article: 'SKU-666',
        wb_article: 666, barcode: '460666001', sku: 'SKU-666', chrt_id: 666, category: 'Тест', color: null, size: null,
      },
      positions: [], inventory: { available_unpacked: 1, locations: [] }, buyer_type: 'individual', cargo_type: 'mgt',
      can_pvz: false, metadata: { required: ['sgtin'], optional: [], states: [], delivery_allowed: false, last_checked_at: null },
      sticker: { code: '*AUDIT-666', status: 'print_opened', asset_url: null, applied_at: null },
      pick: { status: 'picked', location_code: 'A-01', picked_at: null }, pack: { status: 'pending', packed_at: null },
      created_at_wb: new Date().toISOString(), deadline_at: new Date().toISOString(), supply_id: SUPPLY_ID,
      selection_blockers: [], tape_order_index: 0, marking_available_count: markingAvailableCount,
    }],
    cargo_places: [], boxes: [], delivery_preflight: null, last_wb_sync_at: null, server_now: new Date().toISOString(),
  } as unknown as FbsWorkspace
}

let taskCount = 0
let apiCount = 2
let requests: string[]
const originalFetch = globalThis.fetch
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })

async function server(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const path = url.pathname.replace(/^\/api/, '')
  requests.push(`${(init?.method ?? 'GET').toUpperCase()} ${path}`)
  if (path === `/operations/packaging-tasks/${TASK_ID}`) {
    return json({ id: TASK_ID, status: 'in_progress', lines: [{
      id: 'line-666', product_id: 'product-666', sku_code: 'SKU-666', product_name: 'Товар с текущим ЧЗ',
      requires_honest_sign: true, packaging_instructions: '', qty_total: 1, qty_need_pack: 1,
      marking_available_count: taskCount,
    }] })
  }
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/workspace`) return json(workspace(apiCount))
  return json(null)
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  taskCount = 0
  apiCount = 2
  requests = []
  openPrint.mockClear()
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

async function settle() {
  for (let step = 0; step < 8; step += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  }
}

async function render(initial: FbsWorkspace) {
  window.sessionStorage.setItem(`wms:fbs:${SUPPLY_ID}:stage`, 'packing')
  await act(async () => {
    root.render(<FfFbsSupplyWorkspace
      token="token-wms666" authHeaders={() => ({ Authorization: 'Bearer token-wms666' })}
      supplyId={SUPPLY_ID} initialWorkspace={initial} open onClose={() => undefined}
    />)
  })
  await settle()
}

it('WMS-666 does not let a stale task shortage hide the refreshed current per-order pool', async () => {
  // First ordering: the task read is stale at 0; the subsequent workspace read is current at 2.
  taskCount = 0
  apiCount = 2
  await render(workspace(apiCount))
  expect(requests).toContain(`GET /operations/packaging-tasks/${TASK_ID}`)
  expect.soft(document.body.textContent).toContain('2 · нужно 1')
  await act(async () => document.body.querySelector<HTMLButtonElement>('[aria-label="Печать ЧЗ и ШК"]')!.click())
  expect.soft(openPrint).toHaveBeenLastCalledWith(expect.objectContaining({ markingAvailable: 2 }), expect.anything())
})

it('WMS-666 does not let a stale task count expose depleted current per-order pool', async () => {
  // Reverse ordering: an old task count must not hide depletion reported by the refreshed workspace.
  taskCount = 2
  apiCount = 0
  await render(workspace(apiCount))
  expect.soft(document.body.textContent).toContain('0 · нужно 1')
  await act(async () => document.body.querySelector<HTMLButtonElement>('[aria-label="Печать ЧЗ и ШК"]')!.click())
  expect.soft(openPrint).toHaveBeenLastCalledWith(expect.objectContaining({ markingAvailable: 0 }), expect.anything())
})
