// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfInboundRequestView } from './FfInboundRequestView'

// WMS-755 C1, C2 (догон): скан наклейки короба в приёмке открывает окно наполнения
// этого короба; скан другого короба внутри окна сохраняет вписанное количество и
// переключает окно. Экран и окно настоящие, сеть перехватывается на уровне fetch.

// Сгенерированные ШК коробов: по ним подпись окна — «Короб № N».
const REQUEST_ID = 'request-755'
const BOX_1 = 'INB-V2KA7397PAX2M9'
const BOX_2 = 'INB-4JDZN6VTGZBH5Z'

function documentDetail() {
  const box = (boxNumber: number, barcode: string) => ({
    id: `box-${boxNumber}`, box_number: boxNumber, internal_barcode: barcode, free_text: null,
    pallet_id: null, pallet_code: null, storage_location_id: null, storage_location_code: null,
    label_printed_at: '2026-10-01T12:00:00Z', intake_opened_at: null, intake_closed_at: null,
    is_damaged: false, lines: [],
  })
  return {
    id: REQUEST_ID, document_number: 'INB-000755', display_number: '755', waybill_number: null,
    warehouse_id: 'warehouse-755', status: 'receiving', operation_type: 'inbound', marketplace: null,
    marketplace_warning: null, planned_delivery_date: null, planned_box_count: null,
    actual_box_count: null, boxes_discrepancy: false, has_discrepancy: false,
    seller_id: 'seller-755', seller_name: 'Селлер WMS-755', created_by_seller_id: null,
    created_at: '2026-10-09T00:00:00Z', distribution_completed_at: null, sorting_remaining_qty: 0,
    boxes: [box(1, BOX_1), box(2, BOX_2)],
    cargo_places: [],
    lines: [
      {
        id: 'line-A', product_id: 'product-A', sku_code: 'SKU-A', product_name: 'Товар А',
        wb_barcode: null, requires_honest_sign: false, length_mm: null, width_mm: null,
        height_mm: null, weight_g: null, volume_liters: null, added_by_fulfillment: false,
        expected_qty: 5, actual_qty: 0, effective_actual_qty: 0, posted_qty: 0,
        storage_location_id: null, storage_location_code: null,
      },
    ],
  }
}

let root: Root
let host: HTMLDivElement
let current: ReturnType<typeof documentDetail>
let boxLineWrites: Array<{ url: string; body: unknown }>
let scanPosts: string[]

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  current = documentDetail()
  boxLineWrites = []
  scanPosts = []
  // jsdom не реализует прокрутку, которую вызывает экран при показе ошибки.
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: vi.fn() })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (method === 'GET' && url.endsWith(`/operations/inbound-intake-requests/${REQUEST_ID}`)) return json(current)
    if (url.includes('/products/linked-wb-catalog')) return json([])
    if (url.endsWith('/marking-codes')) return json({ items: [], checking: false })
    if (url.includes('/locations?exclude_sorting_zone=true')) return json([])
    if (url.endsWith('/warehouses')) return json([{ id: 'warehouse-755', name: 'Склад' }])
    if (method === 'PUT' && /\/boxes\/box-\d+\/lines\/product-A$/.test(url)) {
      boxLineWrites.push({ url, body: JSON.parse(String(init?.body)) })
      return json({})
    }
    if (method === 'POST' && (url.endsWith('/receiving/scan') || /\/boxes\/box-\d+\/scan$/.test(url))) {
      scanPosts.push(url)
      return json({ detail: 'barcode_unknown' }, 404)
    }
    throw new Error(`Unexpected WMS-755 request: ${method} ${url}`)
  }))
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function byTestId(id: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(`[data-testid="${id}"]`)
  expect(element, id).toBeTruthy()
  return element!
}

async function waitFor(check: () => void) {
  let last: unknown
  for (let attempt = 0; attempt < 200; attempt++) {
    try {
      check()
      return
    } catch (error) {
      last = error
    }
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)) })
  }
  throw last
}

/** Значение поля задаём так же, как браузер: нативный сеттер и событие input. */
function typeInto(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  setter.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

/** Клавиатурный сканер: пачка символов в текущий фокус и Enter. */
async function wedgeScan(code: string) {
  const target = document.activeElement ?? document.body
  await act(async () => {
    for (const key of code) {
      target.dispatchEvent(new KeyboardEvent('keydown', {
        key, code: key === '-' ? 'Minus' : /\d/.test(key) ? `Digit${key}` : `Key${key.toUpperCase()}`,
        bubbles: true, cancelable: true,
      }))
    }
    target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
}

/** Скан в поле «Штрихкод товара» открытого окна короба: текст в поле и Enter. */
async function scanIntoOpenBox(code: string) {
  const input = byTestId('ff-inbound-box-add-scan-input') as HTMLInputElement
  await act(async () => { typeInto(input, code) })
  await act(async () => {
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
}

const dialogLabel = () => document.querySelector('[data-testid="ff-inbound-box-add-box-label"]')?.textContent ?? ''
const manualQtyOf = (productId: string) => document.querySelector<HTMLInputElement>(
  `[data-testid="ff-inbound-box-add-manual-qty"][data-product-id="${productId}"]`,
)

async function mountReception() {
  await act(async () => {
    root.render(
      <FfInboundRequestView
        token="wms755-token"
        requestId={REQUEST_ID}
        isFulfillmentAdmin
        workspace="reception"
        numberedInboundBoxLabels
        onClose={() => undefined}
      />,
    )
  })
  await waitFor(() => expect(document.querySelector('[data-testid="ff-inbound-packages-toggle"]')).toBeTruthy())
}

describe('WMS-755 скан наклейки короба в приёмке', () => {
  it('C1: глобальный скан кода короба открывает окно наполнения этого короба, без скана товара', async () => {
    await mountReception()
    await wedgeScan(BOX_2)
    await waitFor(() => {
      expect(document.querySelector('[data-testid="ff-inbound-box-add-dialog"]'), 'окно наполнения открыто').toBeTruthy()
      expect(dialogLabel()).toBe('Короб № 2')
    })
    expect(scanPosts, 'код короба не уходит как скан товара').toEqual([])
  })

  it('C2: скан другого короба внутри окна сохраняет вписанное количество и переключает окно', async () => {
    await mountReception()
    // Первый короб открывается штатной кнопкой «Наполнить», чтобы этот тест
    // проверял именно переключение, а не открытие по скану (его проверяет C1).
    if (!document.querySelector('[data-testid="ff-inbound-boxes-panel"]')) {
      await act(async () => byTestId('ff-inbound-packages-toggle').click())
    }
    await act(async () => byTestId('ff-inbound-box-fill-box-1').click())
    await waitFor(() => expect(dialogLabel()).toBe('Короб № 1'))

    await act(async () => { typeInto(manualQtyOf('product-A')!, '3') })
    await scanIntoOpenBox(BOX_2)

    await waitFor(() => expect(dialogLabel(), 'окно переключилось на второй короб').toBe('Короб № 2'))
    expect(boxLineWrites, 'вписанные 3 сохранены в коробе 1 до перехода').toEqual([
      { url: expect.stringMatching(/\/boxes\/box-1\/lines\/product-A$/), body: { quantity: 3 } },
    ])
    expect(scanPosts, 'код второго короба не отправлен как скан в первый короб').toEqual([])
  })
})
