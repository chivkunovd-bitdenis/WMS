import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'

export function order(id: string, patch: Record<string, unknown> = {}) {
  return {
    id, marketplace: 'wb', external_order_id: id, wb_order_id: 100 + Number(id.replace(/\D/g, '') || 1),
    status: 'assembling', wb_status: 'confirm', supplier_status: 'confirm',
    seller: { id: 'seller', name: 'Селлер' }, wb_warehouse: { id: 507, name: 'Коледино' },
    wms_warehouse: { id: 'wh', name: 'Склад' },
    product: { id: `product-${id}`, name: `Товар ${id}`, image_url: null, seller_article: id,
      wb_article: 1, barcode: `460${id}`, sku: id, chrt_id: 1, category: 'Тест', color: null, size: null, requires_honest_sign: false },
    positions: [], inventory: { available_unpacked: 10, locations: [] }, buyer_type: 'individual', cargo_type: 'mgt', can_pvz: false,
    metadata: { required: [], optional: [], states: [], delivery_allowed: true, last_checked_at: null },
    sticker: { code: `*${id}`, status: 'print_opened', asset_url: null, applied_at: null },
    pick: { status: 'pending', location_code: null, picked_at: null }, pack: { status: 'pending', packed_at: null },
    created_at_wb: '2026-10-09T08:00:00Z', deadline_at: '2026-10-10T18:00:00Z', supply_id: 'supply-a',
    selection_blockers: [], tape_order_index: 0, ...patch,
  } as unknown as FbsWorkspace['orders'][number]
}

export function workspace(marketplace: 'wb' | 'ozon' = 'wb', orders = [order('o1')]): FbsWorkspace {
  return {
    supply: { id: 'supply-a', marketplace, wb_supply_id: marketplace === 'wb' ? 'WB-TEST' : null,
      source: 'wms', name: 'Поставка A', status: 'assembling', delivery_type: 'warehouse_sc',
      seller: { id: 'seller', name: 'Селлер' }, wb_warehouse: { id: 507, name: 'Коледино' },
      wms_warehouse: { id: 'wh', name: 'Склад' }, planned_destination: null, planned_shipment_date: null,
      nearest_deadline_at: '2026-10-10T18:00:00Z', packaging_task_id: 'task', barcode_asset: null },
    stage: 'composition', progress: { picked: 0, packed: 0, metadata_ready: 0, stickers_ready: orders.length, total: orders.length },
    blockers: [], orders: orders.map(o => ({ ...o, marketplace })), cargo_places: [], boxes: [],
    delivery_preflight: null, last_wb_sync_at: null, server_now: '2026-10-09T10:00:00Z',
  } as unknown as FbsWorkspace
}

export function box(id: string, number: number, ids: string[] = [], positions: string[] = []) {
  return { id, box_number: number, barcode: `BOX-${number}`, assigned_order_ids: ids,
    assigned_order_product_ids: positions, trbx_id: null, wb_trbx_id: null, qr_asset: null,
    without_distribution: false, ozon_assembled: false } as FbsWorkspace['boxes'][number]
}

export const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
export const authHeaders = () => ({ Authorization: 'Bearer contract-test' })
export const settle = async () => {
  for (let i = 0; i < 6; i++) await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
}
export async function click(node: Element | null | undefined) {
  if (!node) throw new Error('Ожидаемый элемент интерфейса отсутствует')
  await act(async () => (node as HTMLElement).click())
  await settle()
}
export function button(text: string, scope: ParentNode = document) {
  return [...scope.querySelectorAll<HTMLButtonElement>('button')].find(b => b.textContent?.trim() === text)
}
export async function input(node: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(node, value)
    node.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await settle()
}
export const selected = (scope: ParentNode = document) => [...scope.querySelectorAll<HTMLInputElement>('[data-testid="fbs-packing-select-order"] input')]
  .filter(n => n.checked).map(n => n.closest('[data-order-id]')!.getAttribute('data-order-id'))
export const deferred = <T,>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}

type Call = { path: string; method: string; body: any }
export class CardFixture {
  current = workspace()
  calls: Call[] = []
  close = vi.fn()
  lines: any[] = []
  hook?: (call: Call) => Promise<Response | undefined>
  host = document.createElement('div')
  root: Root
  originalFetch = globalThis.fetch
  constructor() {
    ;(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true
    Element.prototype.scrollIntoView = () => undefined
    window.sessionStorage.clear()
    window.localStorage.clear()
    document.body.append(this.host)
    this.root = createRoot(this.host)
    globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
      const parsed = new URL(typeof url === 'string' ? url : url instanceof URL ? url.href : url.url, 'http://test')
      const call = { path: parsed.pathname.replace(/^\/api/, ''), method: (init?.method ?? 'GET').toUpperCase(),
        body: typeof init?.body === 'string' ? JSON.parse(init.body) : null }
      this.calls.push(call)
      const custom = await this.hook?.(call)
      if (custom) return custom
      if (call.path.startsWith('/operations/packaging-tasks/')) return json({ id: 'task', status: 'in_progress', lines: this.lines })
      if (call.path.endsWith('/workspace')) return json(this.current)
      if (call.path.endsWith('/pick-options') || call.path.endsWith('/picking-context')) return json([])
      if (call.path.endsWith('/history')) return json({ events: [], discrepancies: [] })
      if (call.path.endsWith('/ozon-exemplar-documents')) return json({ version: 0, state: 'editable', absence_selected: false, requirements_complete: true, errors: [], products: [] })
      if (call.path === '/operations/fbs-orders/worklist') return json({ items: [order('new')], total: 1, server_now: this.current.server_now })
      if (call.path.endsWith('/orders/batch')) {
        for (const id of call.body.order_ids) if (!this.current.orders.some(o => o.id === id)) this.current.orders.push(order(id))
        return json(this.current)
      }
      if (/\/boxes\/[^/]+\/orders$/.test(call.path) && call.method === 'POST') {
        const target = this.current.boxes.find(b => b.id === call.path.split('/').at(-2))!
        target.assigned_order_ids = [...new Set([...target.assigned_order_ids, ...(call.body.order_ids ?? [])])]
        target.assigned_order_product_ids = [...new Set([...(target.assigned_order_product_ids ?? []), ...(call.body.order_product_ids ?? [])])]
        return json(this.current)
      }
      return json(null)
    }) as typeof fetch
  }
  async render(stage?: string, extra: Record<string, unknown> = {}) {
    if (stage) window.sessionStorage.setItem(`wms:fbs:${this.current.supply.id}:stage`, stage)
    await act(async () => this.root.render(<FfFbsSupplyWorkspace token="contract-test" authHeaders={authHeaders}
      supplyId={this.current.supply.id} initialWorkspace={structuredClone(this.current)} open onClose={this.close} {...extra} />))
    await settle()
  }
  writes() { return this.calls.filter(c => c.method !== 'GET') }
  dispose() { act(() => this.root.unmount()); this.host.remove(); globalThis.fetch = this.originalFetch; document.body.innerHTML = '' }
}
