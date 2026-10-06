// @vitest-environment jsdom
// Owner instruction 2026-10-06 replaces former C16 row forms with one Boxes checkbox.
// Preservation and restart protections remain in backend contracts.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import type { FbsWorkspace } from './fbsApi'

vi.mock('../ff/unload-pick/FfUnloadPickPage', () => ({ FfUnloadPickPage: () => null }))
vi.mock('../../utils/useMarkingCodePrint', () => ({ useMarkingCodePrint: () => ({ openPrint: vi.fn(), dialog: null }) }))
vi.mock('./FbsSupplyHistoryDialog', () => ({ FbsSupplyHistoryDialog: () => null }))
vi.mock('./FbsPrintPreviewDialog', () => ({ FbsPrintPreviewDialog: () => null }))
vi.mock('./FbsTransferSupplyDialog', () => ({ FbsTransferSupplyDialog: () => null, makeFbsTransferSupplyDeps: () => ({}) }))

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})

const SUPPLY_ID = 'supply-wms663'
const ORDER_ID = 'order-wms663'
const DOCUMENTS_PATH = `/operations/fbs-orders/${ORDER_ID}/ozon-exemplar-documents`

let marketplace: 'ozon' | 'wb'
function workspace(): FbsWorkspace {
  return {
    supply: {
      id: SUPPLY_ID,
      marketplace,
      wb_supply_id: 'OZON-WMS663',
      source: 'wms',
      name: 'Ozon WMS-663',
      status: 'assembling',
      delivery_type: 'warehouse_sc',
      seller: { id: 'seller-663', name: 'Продавец Ozon' },
      wb_warehouse: { id: 663, name: 'Ozon FBS' },
      wms_warehouse: { id: 'warehouse-663', name: 'Основной склад' },
      planned_destination: null,
      planned_shipment_date: null,
      nearest_deadline_at: new Date(Date.now() + 86_400_000).toISOString(),
      packaging_task_id: 'task-wms663',
      barcode_asset: null,
    },
    stage: 'packing',
    progress: { picked: 3, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 3 },
    blockers: [],
    orders: [{
      id: ORDER_ID,
      marketplace,
      external_order_id: '019663-0001-1',
      wb_order_id: -1,
      status: 'assembling',
      wb_status: 'awaiting_packaging',
      supplier_status: 'awaiting_packaging',
      seller: { id: 'seller-663', name: 'Продавец Ozon' },
      wb_warehouse: { id: 663, name: 'Ozon FBS' },
      wms_warehouse: { id: 'warehouse-663', name: 'Основной склад' },
      product: {
        id: 'product-663-a',
        name: 'Очень длинное название импортного товара для проверки строки документа',
        image_url: null,
        seller_article: 'ART-GTD',
        wb_article: null,
        barcode: '4600000000663',
        sku: '663001',
        chrt_id: null,
        category: 'Тест',
        color: null,
        size: null,
      },
      positions: [
        {
          id: 'position-663-a',
          product_id: 'product-663-a',
          name: 'Очень длинное название импортного товара для проверки строки документа',
          seller_article: 'ART-GTD',
          sku: '663001',
          quantity: 2,
          reserved_quantity: 2,
          picked_quantity: 2,
        },
        {
          id: 'position-663-b',
          product_id: 'product-663-b',
          name: 'Второй товар с РНПТ',
          seller_article: 'ART-RNPT',
          sku: '663002',
          quantity: 1,
          reserved_quantity: 1,
          picked_quantity: 1,
        },
      ],
      inventory: { available_unpacked: 5, locations: [] },
      buyer_type: 'individual',
      cargo_type: 'mgt',
      can_pvz: false,
      metadata: { required: [], optional: [], states: [], delivery_allowed: false, last_checked_at: null },
      sticker: { code: 'OZON-663', status: 'print_opened', asset_url: null, applied_at: null },
      pick: { status: 'picked', location_code: 'A-01', picked_at: null },
      pack: { status: 'pending', packed_at: null },
      created_at_wb: new Date().toISOString(),
      deadline_at: new Date(Date.now() + 86_400_000).toISOString(),
      supply_id: SUPPLY_ID,
      selection_blockers: [],
      tape_order_index: 0,
    }],
    cargo_places: [],
    boxes: [],
    delivery_preflight: null,
    last_wb_sync_at: null,
    server_now: new Date().toISOString(),
  } as unknown as FbsWorkspace
}

const packagingTask = {
  id: 'task-wms663',
  document_number: '000663',
  display_number: '000663',
  status: 'in_progress',
  lines: [
    {
      id: 'line-663-a', product_id: 'product-663-a', sku_code: '663001',
      product_name: 'Очень длинное название импортного товара для проверки строки документа',
      requires_honest_sign: true, packaging_instructions: '', qty_total: 2, qty_need_pack: 2,
      marking_available_count: 2,
    },
    {
      id: 'line-663-b', product_id: 'product-663-b', sku_code: '663002',
      product_name: 'Второй товар с РНПТ', requires_honest_sign: false,
      packaging_instructions: '', qty_total: 1, qty_need_pack: 1, marking_available_count: 0,
    },
  ],
}

const documentState = {
  posting_number: '019663-0001-1',
  state: 'editable',
  version: 4,
  products: [
    {
      product_id: 663001,
      name: 'Очень длинное название импортного товара для проверки строки документа',
      sku: '663001',
      exemplars: [
        { exemplar_id: 81, ordinal: 1, gtd_required: true, rnpt_required: false, gtd: '', is_gtd_absent: false, rnpt: '', is_rnpt_absent: false, state: 'editable', errors: [] },
        { exemplar_id: 82, ordinal: 2, gtd_required: true, rnpt_required: false, gtd: '0000/663-82', is_gtd_absent: false, rnpt: '', is_rnpt_absent: false, state: 'editable', errors: [] },
      ],
    },
    {
      product_id: 663002,
      name: 'Второй товар с РНПТ',
      sku: '663002',
      exemplars: [
        { exemplar_id: 91, ordinal: 1, gtd_required: false, rnpt_required: true, gtd: '', is_gtd_absent: false, rnpt: '', is_rnpt_absent: false, state: 'editable', errors: [] },
      ],
    },
  ],
}

let cabinet: typeof documentState
let rejectAbsent: boolean
const originalFetch = globalThis.fetch
let requests: Array<{ method: string; path: string; body: unknown }>

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

async function server(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const path = url.pathname.replace(/^\/api/, '')
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = typeof init?.body === 'string' ? JSON.parse(init.body) : null
  requests.push({ method, path, body })
  if (path.startsWith('/operations/packaging-tasks/')) return json(packagingTask)
  if (path === `/operations/fbs-supplies/${SUPPLY_ID}/workspace`) return json(workspace())
  if (path === DOCUMENTS_PATH && method === 'GET') return json(cabinet)
  if (path === DOCUMENTS_PATH + '/absent' && method === 'POST') {
    if (rejectAbsent) return json({ detail: { code: 'gtd_invalid', message: 'Ozon: gtd_invalid' } }, 409)
    cabinet = { ...cabinet, state: 'unknown', version: 5, products: cabinet.products.map(product => ({ ...product, exemplars: product.exemplars.map(exemplar => ({ ...exemplar, gtd: exemplar.gtd_required ? '' : exemplar.gtd, rnpt: exemplar.rnpt_required ? '' : exemplar.rnpt, is_gtd_absent: exemplar.gtd_required || exemplar.is_gtd_absent, is_rnpt_absent: exemplar.rnpt_required || exemplar.is_rnpt_absent })) })) }
    return json(cabinet)
  }
  if (path === DOCUMENTS_PATH && method === 'PUT') {
    return json({
      ...documentState,
      state: 'rejected',
      version: 5,
      products: [{
        ...documentState.products[0],
        exemplars: [{
          ...documentState.products[0].exemplars[0],
          gtd: '001/ABC-09',
          state: 'rejected',
          errors: ['gtd_invalid'],
        }, documentState.products[0].exemplars[1]],
      }, documentState.products[1]],
    })
  }
  return json(null)
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  requests = []
  marketplace = 'ozon'
  cabinet = JSON.parse(JSON.stringify(documentState))
  rejectAbsent = false
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

async function openWorkspace() {
  await act(async () => {
    root.render(
      <FfFbsSupplyWorkspace
        token="token-wms663"
        authHeaders={() => ({ Authorization: 'Bearer token-wms663' })}
        supplyId={SUPPLY_ID}
        initialWorkspace={workspace()}
        open
        onClose={() => undefined}
      />,
    )
  })
  await settle()
}

function button(name: string) {
  return [...document.querySelectorAll<HTMLButtonElement>('button')]
    .find((element) => element.textContent?.trim() === name)
}

const choice = () => [...document.querySelectorAll('label')]
  .filter(label => label.textContent?.trim() === 'Без ГТД и РНПТ')
  .map(label => label.querySelector<HTMLInputElement>('input[type="checkbox"]'))
const writes = () => requests.filter(call => call.method !== 'GET')
async function boxes() {
  const tab = [...document.querySelectorAll<HTMLElement>('[role="tab"]')].find(node => node.textContent === 'Короба')
  expect(tab).toBeTruthy()
  await act(async () => tab!.click())
  await settle()
}

it('owner663 A1: packing has no per-row customs form or customs action', async () => {
  await openWorkspace()
  expect(document.querySelectorAll('[data-testid^="ozon-documents-"]')).toHaveLength(0)
  expect(button('ГТД / РНПТ')).toBeUndefined()
  expect(document.querySelector('input[aria-label^="Номер ГТД"]')).toBeNull()
  expect(document.querySelector('input[aria-label^="Номер РНПТ"]')).toBeNull()
  expect(choice()).toHaveLength(0)
  expect(writes()).toHaveLength(0)
})

it('owner663 A2: boxes expose exactly one unchecked Ozon checkbox; opening writes nothing', async () => {
  await openWorkspace(); await boxes()
  expect(choice()).toHaveLength(1)
  expect(choice()[0]?.checked).toBe(false)
  expect(document.querySelector('[data-testid="fbs-boxes"]')?.contains(choice()[0]!)).toBe(true)
  expect(button('ГТД / РНПТ')).toBeUndefined()
  expect([...document.querySelectorAll<HTMLButtonElement>('[data-testid="fbs-boxes"] button')].some(node => node.textContent?.trim() === 'Сохранить')).toBe(false)
  expect(document.querySelector('input[aria-label^="Номера ГТД нет"]')).toBeNull()
  expect(document.querySelector('input[aria-label^="Номера РНПТ нет"]')).toBeNull()
  expect(writes()).toHaveLength(0)
})

it('owner663 A3: WB boxes keep their own actions and have no Ozon customs checkbox', async () => {
  marketplace = 'wb'
  await openWorkspace(); await boxes()
  expect(choice()).toHaveLength(0)
  expect(document.querySelector('[data-testid="fbs-boxes-without-distribution"]')).not.toBeNull()
  expect(writes()).toHaveLength(0)
})

it('owner663 A4: explicit click posts the current order and version without a save dialog', async () => {
  await openWorkspace(); await boxes()
  expect(choice()).toHaveLength(1)
  await act(async () => choice()[0]!.click()); await settle()
  expect(writes()).toEqual([{ method: 'POST', path: DOCUMENTS_PATH + '/absent', body: { expected_version: 4 } }])
  expect(document.querySelectorAll('[data-testid^="ozon-documents-"]')).toHaveLength(0)
  expect([...document.querySelectorAll<HTMLButtonElement>('[data-testid="fbs-boxes"] button')].some(node => node.textContent?.trim() === 'Сохранить')).toBe(false)
})

it('owner663 A5: persisted unknown intent survives reopening; reverse click cannot erase or repeat', async () => {
  await openWorkspace(); await boxes()
  expect(choice()).toHaveLength(1)
  await act(async () => choice()[0]!.click()); await settle()
  expect(choice()[0]?.checked).toBe(true)
  expect(document.body.textContent).not.toContain('Принято')
  await act(async () => root.render(null)); await openWorkspace(); await boxes()
  expect(choice()[0]?.checked).toBe(true)
  await act(async () => choice()[0]!.click()); await settle()
  expect(choice()[0]?.checked).toBe(true)
  expect(writes()).toEqual([{ method: 'POST', path: DOCUMENTS_PATH + '/absent', body: { expected_version: 4 } }])
})

it('owner663 A6: concrete Ozon failure stays visible next to the shared choice; close remains usable', async () => {
  rejectAbsent = true
  await openWorkspace(); await boxes()
  expect(choice()).toHaveLength(1)
  await act(async () => choice()[0]!.click()); await settle()
  expect(document.body.textContent).toContain('gtd_invalid')
  expect(choice()[0]?.checked).toBe(false)
  expect(writes()).toHaveLength(1)
  expect(document.querySelectorAll('[data-testid^="ozon-documents-"]')).toHaveLength(0)
  const close = document.querySelector<HTMLButtonElement>('button[aria-label="Закрыть"]')!
  expect(close.disabled).toBe(false)
  close.focus(); expect(document.activeElement).toBe(close)
})

it('owner666 A7: packing keeps the baseline printed/packed wording', async () => {
  await openWorkspace()
  expect(document.body.textContent).toMatch(/Напечатано .*· упаковано 0 из 3/)
  expect(document.body.textContent).not.toContain('Обработано')
})
