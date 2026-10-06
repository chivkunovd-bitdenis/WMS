// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
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

function workspace(): FbsWorkspace {
  return {
    supply: {
      id: SUPPLY_ID,
      marketplace: 'ozon',
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
      marketplace: 'ozon',
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
  if (path === DOCUMENTS_PATH && method === 'GET') return json(documentState)
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

function input(label: string) {
  return document.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)
}

function setInput(element: HTMLInputElement, value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(element, value)
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

describe('WMS-663 · явный ГТД/РНПТ у экземпляра Ozon', () => {
  it('C16: выбор по экземпляру сохраняется, ошибка остаётся в строке и навигация не блокируется', async () => {
    await openWorkspace()

    const open = button('ГТД / РНПТ')
    expect(open, 'Ozon order must expose the customs-document action in its own row').toBeDefined()
    await act(async () => open!.click())
    await settle()

    expect(requests).toContainEqual({ method: 'GET', path: DOCUMENTS_PATH, body: null })
    expect(document.body.textContent).toContain('Очень длинное название импортного товара')
    expect(document.body.textContent).toContain('Экземпляр 1')
    expect(document.body.textContent).toContain('Экземпляр 2')

    const gtd = input('Номер ГТД · SKU 663001 · экземпляр 1')
    const absent = input('Номера ГТД нет · SKU 663001 · экземпляр 1')
    const rnpt = input('Номер РНПТ · SKU 663002 · экземпляр 1')
    expect(gtd).not.toBeNull()
    expect(absent).not.toBeNull()
    expect(rnpt).not.toBeNull()
    expect(absent!.checked).toBe(false)

    setInput(gtd!, '001/ABC-09')
    expect(absent!.checked).toBe(false)
    await act(async () => document.querySelector<HTMLButtonElement>('button[aria-label="Сохранить ГТД / РНПТ · SKU 663001 · экземпляр 1"]')!.click())
    await settle()

    expect(requests).toContainEqual({
      method: 'PUT',
      path: DOCUMENTS_PATH,
      body: {
        product_id: 663001,
        exemplar_id: 81,
        gtd: '001/ABC-09',
        is_gtd_absent: false,
        rnpt: null,
        is_rnpt_absent: false,
        expected_version: 4,
      },
    })
    expect(document.body.textContent).toContain('gtd_invalid')
    expect(input('Номер ГТД · SKU 663001 · экземпляр 1')!.value).toBe('001/ABC-09')

    setInput(input('Номер ГТД · SKU 663001 · экземпляр 1')!, '001/ABC-10')
    await act(async () => document.querySelector<HTMLButtonElement>('button[aria-label="Сохранить ГТД / РНПТ · SKU 663001 · экземпляр 1"]')!.click())
    await settle()
    expect(requests).toContainEqual({
      method: 'PUT',
      path: DOCUMENTS_PATH,
      body: {
        product_id: 663001,
        exemplar_id: 81,
        gtd: '001/ABC-10',
        is_gtd_absent: false,
        rnpt: null,
        is_rnpt_absent: false,
        expected_version: 5,
      },
    })

    const close = document.querySelector<HTMLButtonElement>('button[aria-label="Закрыть"]')
    expect(close).toBeDefined()
    close!.focus()
    expect(document.activeElement).toBe(close)
  })
})
