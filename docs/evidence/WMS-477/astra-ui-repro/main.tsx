import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { FfFbsSupplyWorkspace } from '../../src/screens/v2/FfFbsSupplyWorkspace'
import { ErrorBoundary } from '../../src/components/errors/ErrorBoundary'
import type { FbsWorkspace, FbsWorklistOrder } from '../../src/screens/v2/fbsApi'

const now = '2026-09-21T10:00:00Z'
const seller = { id: 'fixture-seller', name: 'Тестовый селлер' }
const wbWarehouse = { id: 1, name: 'Тестовый склад WB' }
const wmsWarehouse = { id: 'fixture-wh', name: 'Полка 1' }

function order(id: string, name: string, size: string | null, marketplace: 'wb' | 'ozon', sticker: string | null, positions?: Array<[string, string | null]>): FbsWorklistOrder & { tape_order_index: number } {
  return {
    id, marketplace, external_order_id: marketplace === 'ozon' ? `OZ-${id}` : null,
    wb_order_id: Number(id.replace(/\D/g, '')) || 5813479884,
    status: 'assembling', wb_status: null, supplier_status: null,
    seller, wb_warehouse: wbWarehouse, wms_warehouse: wmsWarehouse,
    product: { id: `p-${id}`, name, image_url: null, seller_article: `art-${id}`, wb_article: null,
      barcode: `barcode-${id}`, sku: `sku-${id}`, chrt_id: null, category: null, color: null, size },
    positions: (positions ?? []).map(([positionName, positionSize], index) => ({
      id: `${id}-pos-${index}`, product_id: `${id}-product-${index}`, name: positionName,
      seller_article: `OZ-${index}`, sku: `oz-sku-${index}`, size: positionSize,
      quantity: 1, reserved_quantity: 1, picked_quantity: 1,
    })),
    inventory: { available_unpacked: 1, locations: [{ id: 'loc-1', code: 'A-1', available_unpacked: 1 }] },
    buyer_type: 'individual', cargo_type: 'standard', can_pvz: true,
    metadata: { required: [], optional: [], states: [], delivery_allowed: true, last_checked_at: null },
    sticker: { code: sticker, status: sticker ? 'ready' : 'not_requested', asset_url: null, applied_at: null },
    pick: { status: 'picked', location_code: 'A-1', picked_at: now }, pack: { status: 'pending', packed_at: null },
    created_at_wb: now, deadline_at: '2026-09-23T12:00:00Z', supply_id: 'fixture-supply', selection_blockers: [],
    tape_order_index: Number(id.replace(/\D/g, '')) || 1,
  }
}

function workspace(supplyId = 'A', verdict = 'pending', added = false): FbsWorkspace {
  const orders = [order(`${supplyId}1`, `Товар поставки ${supplyId}`, null, 'wb', '901001234')]
  if (added) orders.push(order('6', 'Добавленный товар L', 'L', 'wb', '901000006'))
  for (const row of orders) {
    row.supply_id = supplyId
    row.metadata.required = ['sgtin']
    row.metadata.states = [{ kind: 'sgtin', status: verdict as 'pending', reason: null, value_tail: 'QA-CODE' }]
  }
  return {
    supply: { id: supplyId, marketplace: 'wb', wb_supply_id: `WB-GI-${supplyId}`,
      source: 'wms', name: `Поставка ${supplyId}`, status: 'assembling', delivery_type: 'warehouse_sc',
      seller, wb_warehouse: wbWarehouse, wms_warehouse: wmsWarehouse, planned_destination: null,
      planned_shipment_date: null, nearest_deadline_at: '2026-09-23T12:00:00Z', packaging_task_id: 'fixture-task',
      barcode_asset: null, honest_sign_skipped: false, boxes_without_distribution: false },
    stage: 'packing', progress: { picked: orders.length, packed: 0, metadata_ready: orders.length,
      stickers_ready: orders.length, total: orders.length },
    blockers: [], orders, cargo_places: [], boxes: [], delivery_preflight: null, last_wb_sync_at: null,
    server_now: now, marking_pool: { required: 0, available: 0, shortage: 0, orders_without_code: [] },
  }
}
const initials = { A: workspace('A'), B: workspace('B') }
const log: Array<Record<string, unknown>> = []
const pending = new Map<number, (value: Response) => void>()
let seq = 0
let latency = 0
function response(value: unknown) { return new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } }) }
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(input)
  const method = init?.method ?? 'GET'
  if (url.includes('/operations/packaging-tasks/fixture-task')) return response({id:'fixture-task', document_number:'QA',warehouse_id:'fixture-wh',status:'open',marketplace_unload_request_id:null,inbound_intake_request_id:null,is_complete:false,lines:[],events:[]})
  const match = url.match(/\/fbs-supplies\/([^/]+)\/(workspace|markings\/sync|orders\/batch)/)
  if (match) {
    const id = ++seq
    log.push({ event: 'request', id, supply: match[1], path: match[2], at: Date.now() })
    if (match[2] === 'orders/batch') {
      log.push({event: 'response', id, added: true, at: Date.now()})
      return response(workspace(match[1], 'pending', true))
    }
    return new Promise<Response>(resolve => {
      pending.set(id, resolve)
      if (latency && match[2] === 'workspace') {
        window.setTimeout(() => resolveRequest(id, match[1], 'accepted', false), latency)
      }
    })
  }
  if (url.includes('/operations/fbs-orders/worklist')) {
    return response({items: [order('6','Добавленный товар L','L','wb',null)], next_cursor:null, server_now:now,warehouse_options:[]})
  }
  if (url.includes('/client-errors')) { log.push({event:'client-error',body:init?.body}); return new Response(null,{status:204}) }
  throw new Error(`Unmocked API ${method} ${url}`)
}
function resolveRequest(id: number, supply='A', verdict='pending', added=false) {
  const callback = pending.get(id)
  if (!callback) throw new Error(`Pending request ${id} missing`)
  pending.delete(id)
  log.push({ event:'response', id, supply, verdict, added, at:Date.now() })
  callback(response(workspace(supply, verdict, added)))
}
;(window as any).qa = {
  log, resolve: resolveRequest,
  setLatency: (value:number) => { latency=value },
  pending: () => Array.from(pending.keys()),
}
const headers=() => ({})
function App() {
  const [supplyId,setSupplyId]=useState<'A'|'B'>('A')
  return <>
    <div style={{position:'sticky',top:0,zIndex:9999,background:'#e3f2fd',padding:8}}>
      Изолированная QA оснастка — mock API, настоящий компонент из проверяемого SHA
      <button id="open-A" onClick={()=>setSupplyId('A')}>Открыть A</button>
      <button id="open-B" onClick={()=>setSupplyId('B')}>Открыть B</button>
      <span id="requested-supply">requested: {supplyId}</span>
    </div>
    <ErrorBoundary component="FfFbsSupplyWorkspace" resetKey={supplyId}>
      <FfFbsSupplyWorkspace token="synthetic-only" authHeaders={headers}
        supplyId={supplyId} initialWorkspace={initials[supplyId]} open onClose={()=>{}} />
    </ErrorBoundary>
  </>
}
createRoot(document.getElementById('root')!).render(<App />)
