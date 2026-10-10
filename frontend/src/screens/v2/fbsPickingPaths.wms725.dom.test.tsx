// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { beforeAll, beforeEach, afterEach, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import { FfFbsSupplyAssembly } from './FfFbsSupplyAssembly'
import type { FbsWorkspace } from './fbsApi'
vi.mock('@mui/icons-material', () => new Proxy({}, { has: () => true, get: (_target, key) => key === 'then' ? undefined : () => null }))
const authHeaders = () => ({ Authorization: 'Bearer test' })
function workspace(id: string, marketplace: 'wb' | 'ozon'): FbsWorkspace {
  const orders = [1, 0].map(index => {
    const product = { id: `p${index}`, name: `PRODUCT-${index}`, image_url: 'https://example.test/photo.png', seller_article: `ARTICLE-${index}`, sku: `SKU-${index}`, wb_article: 728000 + index, barcode: '4600000000017', chrt_id: index + 1, category: 'Одежда', color: `COLOR-${index}`, size: 'Универсальный' }
    return { id: `${id}-order-${index}`, marketplace, external_order_id: `${id}-POSTING-${index}`, wb_order_id: 725000 + index, status: 'assembling', wb_status: 'confirm', supplier_status: 'confirm', tape_order_index: index,
      seller: { id: 'seller', name: 'SELLER' }, wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'wh', name: 'WMS' }, product,
      positions: [{ ...product, product_id: product.id, quantity: index + 2, picked_quantity: 1, marketplace_bindings: [] }],
      inventory: { available_unpacked: 8, locations: [{ code: 'CELL-725', available_unpacked: 8 }] }, buyer_type: 'individual', cargo_type: 'mgt', can_pvz: false,
      metadata: { required: ['sgtin'], optional: [], states: [], delivery_allowed: true, last_checked_at: null }, sticker: { code: `${id}-STICKER-${index}`, status: 'ready', asset_url: null, applied_at: null },
      pick: { status: index === 0 ? 'picked' : 'pending', location_code: 'CELL-725', picked_at: null }, pack: { status: 'pending', packed_at: null }, created_at_wb: '2026-10-09T00:00:00Z', deadline_at: '2030-10-10T00:00:00Z', supply_id: id, selection_blockers: [], delivery_route: 'OZON-ROUTE' }
  })
  return { supply: { id, marketplace, wb_supply_id: `${id}-REF`, name: `SUPPLY-${id}`, status: 'assembling', source: 'wms', delivery_type: 'warehouse_sc', seller: { id: 'seller', name: 'SELLER' }, wb_warehouse: { id: 507, name: 'Коледино' }, wms_warehouse: { id: 'wh', name: 'WMS' }, planned_destination: null, planned_shipment_date: null, nearest_deadline_at: '2030-10-10T00:00:00Z', packaging_task_id: null, barcode_asset: null }, stage: 'composition', progress: { picked: 1, total: marketplace === 'ozon' ? 5 : 2, packed: 0, metadata_ready: 0, stickers_ready: 2 }, blockers: [], orders, cargo_places: [], boxes: [], delivery_preflight: null, last_wb_sync_at: null, server_now: '2026-10-09T00:00:00Z' } as unknown as FbsWorkspace
}
type Popup = { document: Document; html: string; closed: boolean; close: () => void; opener: unknown }
let host: HTMLDivElement, root: Root
let market: 'wb' | 'ozon'
let failure: 'options' | 'context' | null
let windows: Popup[]
let snapshots: Map<string, FbsWorkspace>
let holdId: string | null
let held: { resolve: (value: Response) => void }[]
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status })
const context = (id: string) => [0, 1].map(index => ({ product_id: `p${index}`, locations: [`CELL-${id}`], inbound_supplies: [`INBOUND-${id}`], source_groups: [{ key: id, title: `INBOUND-${id}`, lines: [`CELL-${id} · BOX-${id}: 8`] }] }))
beforeAll(() => { (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; Element.prototype.scrollIntoView = () => {} })
beforeEach(() => {
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  market = 'wb'; failure = null; windows = []; snapshots = new Map(); holdId = null; held = []; sessionStorage.clear()
  vi.spyOn(window, 'open').mockImplementation(() => {
    const doc = document.implementation.createHTMLDocument('')
    const popup: Popup = { document: doc, html: '', closed: false, close() { this.closed = true }, opener: null }
    doc.open = (() => { popup.html = ''; return doc }) as Document['open']
    doc.write = (...texts) => { popup.html += texts.join('') }
    doc.close = () => {}
    windows.push(popup); return popup as unknown as Window
  })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    expect(init?.method ?? 'GET').toBe('GET')
    const url = new URL(String(input), 'http://test')
    const id = url.pathname.match(/fbs-supplies\/([^/]+)/)?.[1] ?? 'A'
    if (url.pathname.endsWith('/workspace')) {
      if (!snapshots.has(id)) snapshots.set(id, workspace(id, market))
      return json(snapshots.get(id))
    }
    if (url.pathname.endsWith('/pick-options')) return failure === 'options' ? json({ detail: 'failed' }, 500) : json([])
    if (url.pathname.endsWith('/picking-context')) {
      if (holdId === id) return new Promise<Response>(resolve => { held.push({ resolve }) })
      return failure === 'context' ? json({ detail: 'failed' }, 500) : json(context(id))
    }
    if (url.pathname.endsWith('/ozon-exemplar-documents')) return json({ version: 0, state: 'editable', absence_selected: false, requirements_complete: true, errors: [], products: [] })
    return json([])
  }))
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
async function settle() { await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) }) }
async function open(kind: 'single' | 'group', id = 'A') {
  sessionStorage.setItem(`wms:fbs:assembly:${id},${id}2:stage`, 'composition')
  await act(async () => root.render(<MemoryRouter>{kind === 'single'
    ? <FfFbsSupplyWorkspace token="test" authHeaders={authHeaders} supplyId={id} open onClose={() => {}} />
    : <FfFbsSupplyAssembly token="test" authHeaders={authHeaders} supplyIds={[id, `${id}2`]} open onClose={() => {}} />}</MemoryRouter>))
  await settle()
}
async function print() {
  const button = document.querySelector('[data-testid="fbs-pick-list-print"]')
    ?? [...document.querySelectorAll('button')].find(el => el.textContent?.includes('Лист подбора'))
  expect(button, 'real picking print button').toBeDefined()
  await act(async () => (button as HTMLButtonElement).click()); await settle()
  return windows.at(-1)!
}
function assertNewLayout(popup: Popup, expected: number) {
  const doc = new DOMParser().parseFromString(popup.html, 'text/html')
  const labels = [...doc.querySelectorAll('th')].map(el => el.textContent)
  expect(labels).not.toContain('№')
  expect(doc.body.textContent?.match(/Общее количество:\s*\d+\s*шт\./g)).toEqual([`Общее количество: ${expected} шт.`])
  for (const tr of doc.querySelectorAll('tbody tr')) expect(tr.querySelectorAll('td')[labels.indexOf('Подобрано')]?.textContent?.trim()).toBe('')
  expect(popup.html).toMatch(/width:\s*84px;\s*height:\s*84px/)
  const reference = doc.querySelector('.subtitle')
  expect(reference?.parentElement).not.toBe(doc.body)
  expect(reference?.parentElement?.textContent).toContain('Склад WMS')
}
it.each([['single', 'wb'], ['single', 'ozon'], ['group', 'wb'], ['group', 'ozon']] as const)('c6_%s_%s_real_print_path_preserves_data_and_new_layout', async (kind, marketplace) => {
    market = marketplace; const id = `${kind}-${marketplace}`
    await open(kind, id)
    const before = JSON.stringify([...snapshots.values()])
    const popup = await print()
    expect(popup.closed).toBe(false)
    const doc = new DOMParser().parseFromString(popup.html, 'text/html')
    const names = [...doc.querySelectorAll('tbody tr')].map(tr => tr.querySelector('strong')?.textContent)
    expect(names).toEqual(['PRODUCT-0', 'PRODUCT-1'])
    for (const text of ['ARTICLE-0', 'ARTICLE-1', 'COLOR-0', 'COLOR-1', 'Универсальный', `INBOUND-${id}`, `CELL-${id}`, `BOX-${id}`, 'sgtin']) expect(doc.body.textContent).toContain(text)
    const compactText = doc.body.textContent?.replace(/\s+/g, '')
    expect(compactText).toContain(`${id}-STICKER-0`)
    expect(compactText).toContain(marketplace === 'wb' ? '№725000' : `${id}-POSTING-0`)
    if (kind === 'group') expect(compactText).toContain(`${id}2-STICKER-0`)
    const again = await print()
    expect(JSON.stringify([...snapshots.values()])).toBe(before)
    expect(again.closed).toBe(false)
    assertNewLayout(popup, (marketplace === 'wb' ? 2 : 5) * (kind === 'group' ? 2 : 1))
    assertNewLayout(again, (marketplace === 'wb' ? 2 : 5) * (kind === 'group' ? 2 : 1))
})
it.each(['single', 'group'] as const)('c8_%s_pick_options_failure_warns_context_failure_closes_and_recovers', async kind => {
  await open(kind)
  failure = 'options'; const fallback = await print()
  expect(fallback.closed).toBe(false); expect(fallback.html).toContain('Лист подбора FBS')
  expect(document.body.textContent).toContain('Не удалось получить ячейки и тару — лист подбора напечатан без них.')
  failure = 'context'; const failed = await print()
  expect(failed.closed).toBe(true); expect(failed.html).not.toContain('<table>')
  expect(document.body.textContent).toContain('Не удалось получить приёмки и все места хранения — обновите лист подбора.')
  failure = null; await open(kind, 'B'); const restored = await print()
  expect(restored.closed).toBe(false); expect(restored.html).toContain('B-REF'); expect(restored.html).not.toContain('A-REF')
  // The recovered real print path is also covered by C6's new-layout assertions.
})
it.each(['single', 'group'] as const)('c8_%s_stale_print_context_cannot_replace_new_supply', async kind => {
  await open(kind, 'OLD'); holdId = 'OLD'; await print(); const stale = windows.at(-1)!
  expect(held.length).toBeGreaterThan(0)
  await open(kind, 'NEW'); const current = await print()
  expect(current.html).toContain('NEW-REF')
  await act(async () => held.forEach(one => one.resolve(json(context('OLD'))))); await settle()
  expect(stale.closed).toBe(true); expect(stale.html).not.toContain('<table>')
  expect(current.html).toContain('NEW-REF'); expect(current.html).not.toContain('OLD-REF')
})
