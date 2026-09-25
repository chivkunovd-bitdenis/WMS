// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { WbProductCatalogRow } from '../../types/wbProductCatalog'
import { PRODUCT_SCAN_AMBIGUOUS_MESSAGE } from '../../utils/productScanResolver'
import { FfInboundRequestView } from './FfInboundRequestView'

// Документ приёмки в настоящем React-рендере: клавиатурный сканер →
// классификатор ЧЗ → единый поиск товара → запрос к серверу.
// F/S-INB-05 — непосредственная приёмка, F/S-INB-04 — добавление строки в черновик.
// Фикстуры — раздел 9 docs/requirements/WMS-536.md.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  Element.prototype.scrollIntoView = () => undefined
})

const WB_P = '4601234567893'
const WB_A = '4601234567886'
const OZN = 'OZN-987654'
const CYR = 'ФА_МОД8-4а/083/42'
const DUP = 'DUP-536'
const GS = '\x1d'
const KIZ_GS = `010460123456789321SERIAL536${GS}91ABCD${GS}92SIGNATURE536`
const KIZ_NO_GS = '010460123456789321SERIAL53691ABCD92SIGNATURE536'

function row(id: string, fields: Partial<WbProductCatalogRow> = {}): WbProductCatalogRow {
  return {
    id,
    name: `Товар ${id}`,
    sku_code: `SKU-${id}`,
    wb_nm_id: null,
    wb_vendor_code: null,
    wb_subject_name: null,
    wb_primary_image_url: null,
    wb_barcodes: [],
    wb_primary_barcode: null,
    wb_size: null,
    wb_color: null,
    ...fields,
  }
}

const P = row('P', {
  sku_code: 'AbC-42',
  wb_primary_barcode: WB_P,
  wb_barcodes: [WB_P, WB_A],
  marketplace_bindings: [
    { marketplace: 'ozon', external_sku: '987654', external_offer_id: 'offer-536', external_barcodes: [OZN] },
  ],
})
const Q = row('Q', { marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: [DUP] }] })
const D = row('D', { sku_code: DUP })
const LAT = row('LAT', { sku_code: 'Chin-56005' })
/** Есть в каталоге селлера, но не в документе. */
const CYRP = row('CYRP', { sku_code: CYR })
const CATALOG = [P, Q, D, LAT, CYRP]

function line(product: WbProductCatalogRow) {
  return {
    id: `line-${product.id}`,
    product_id: product.id,
    sku_code: product.sku_code,
    product_name: product.name,
    wb_barcode: product.wb_primary_barcode,
    requires_honest_sign: false,
    length_mm: null,
    width_mm: null,
    height_mm: null,
    weight_g: null,
    volume_liters: null,
    added_by_fulfillment: false,
    expected_qty: 5,
    actual_qty: 0,
    posted_qty: 0,
    storage_location_id: null,
    storage_location_code: null,
  }
}

function detail(status: string) {
  return {
    id: 'r1',
    document_number: 'IN-1',
    warehouse_id: 'w1',
    status,
    operation_type: 'inbound',
    marketplace: null,
    planned_delivery_date: null,
    planned_box_count: null,
    actual_box_count: null,
    boxes_discrepancy: false,
    has_discrepancy: false,
    seller_id: 's1',
    seller_name: 'Селлер',
    created_by_seller_id: null,
    distribution_completed_at: null,
    boxes: [],
    cargo_places: [],
    lines: status === 'draft' ? [] : [line(P), line(Q), line(D), line(LAT)],
  }
}

// Токен с полезной нагрузкой: черновик ФФ хранит неотправленный запрос по tenant/sub.
const TOKEN = `h.${btoa(JSON.stringify({ sub: 'u1', tenant_id: 't1' }))}.s`

type Call = { method: string; path: string; body: Record<string, unknown> | null }
let calls: Call[] = []
let status = 'receiving'
let root: Root | null = null
let host: HTMLDivElement | null = null

function json(value: unknown, code = 200): Response {
  return new Response(JSON.stringify(value), { status: code, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  calls = []
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.replace(/^\/api/, '')
    const method = init?.method ?? 'GET'
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null
    if (method !== 'GET') calls.push({ method, path, body })
    if (method === 'GET' && path === '/operations/inbound-intake-requests/r1') return json(detail(status))
    if (method === 'GET' && path.startsWith('/products/linked-wb-catalog')) return json(CATALOG)
    if (method === 'GET' && path.endsWith('/marking-codes')) return json({ items: [], checking: false })
    if (path === '/operations/inbound-intake-requests/r1/receiving/scan') {
      const productId = String(body?.product_id ?? 'CYRP')
      return json({ ...line(CATALOG.find((one) => one.id === productId)!), actual_qty: 1 })
    }
    if (path === '/operations/inbound-intake-requests/r1/marking-codes/scan') {
      return json({
        id: `kiz-${calls.length}`, line_id: body?.line_id, product_id: 'P', article: 'AbC-42',
        cis_code: body?.cis_code, cz_status: 'pending', cz_reason: '', outer_status: null, checked_at: null,
      })
    }
    if (path === '/operations/inbound-intake-requests/r1/lines') return json(line(P))
    return json([])
  }))
})

afterEach(() => {
  act(() => root?.unmount())
  host?.remove()
  root = null
  host = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

async function flush(times = 8) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

async function mount(documentStatus: string) {
  status = documentStatus
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  act(() => {
    root!.render(
      <FfInboundRequestView token={TOKEN} requestId="r1" isFulfillmentAdmin workspace="reception" onClose={() => undefined} />,
    )
  })
  await flush()
}

const RU_KEYS: Record<string, string> = {
  й: 'KeyQ', ц: 'KeyW', у: 'KeyE', к: 'KeyR', е: 'KeyT', н: 'KeyY', г: 'KeyU', ш: 'KeyI', щ: 'KeyO',
  з: 'KeyP', х: 'BracketLeft', ъ: 'BracketRight', ф: 'KeyA', ы: 'KeyS', в: 'KeyD', а: 'KeyF', п: 'KeyG',
  р: 'KeyH', о: 'KeyJ', л: 'KeyK', д: 'KeyL', ж: 'Semicolon', э: 'Quote', я: 'KeyZ', ч: 'KeyX', с: 'KeyC',
  м: 'KeyV', и: 'KeyB', т: 'KeyN', ь: 'KeyM', б: 'Comma', ю: 'Period', ё: 'Backquote',
}

function keyEvent(ch: string): KeyboardEventInit {
  if (ch === GS) return { key: ']', code: 'BracketRight', ctrlKey: true }
  const lower = ch.toLowerCase()
  const shiftKey = ch !== lower
  if (RU_KEYS[lower]) return { key: ch, code: RU_KEYS[lower], shiftKey }
  if (/[a-z]/.test(lower)) return { key: ch, code: `Key${lower.toUpperCase()}`, shiftKey }
  if (/[0-9]/.test(ch)) return { key: ch, code: `Digit${ch}` }
  const symbols: Record<string, KeyboardEventInit> = {
    '-': { key: '-', code: 'Minus' },
    _: { key: '_', code: 'Minus', shiftKey: true },
    '/': { key: '/', code: 'Slash' },
  }
  return symbols[ch] ?? { key: ch, code: '' }
}

/** Быстрая пачка клавиатурного сканера вне поля ввода, с Enter на конце. */
async function wedge(text: string) {
  act(() => {
    for (const ch of text) {
      document.body.dispatchEvent(new KeyboardEvent('keydown', { ...keyEvent(ch), bubbles: true, cancelable: true }))
    }
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
  await flush()
}

function scanCalls() {
  return calls.filter((call) => call.path.endsWith('/receiving/scan')).map((call) => call.body)
}

function kizCalls() {
  return calls.filter((call) => call.path.endsWith('/marking-codes/scan')).map((call) => call.body)
}

describe('F/S-INB-05: непосредственная приёмка', () => {
  it.each([
    ['основной WB', WB_P, WB_P, 'P'],
    ['дополнительный WB', WB_A, WB_A, 'P'],
    ['Ozon-штрихкод', OZN, OZN, 'P'],
    ['SKU в другом регистре', 'aBc-42', 'aBc-42', 'P'],
    ['SKU в русской раскладке — исправленным после промаха исходного', 'Сршт-56005', 'Chin-56005', 'LAT'],
  ])('%s уходит серверу с подсказкой товара документа', async (_label, typed, barcode, productId) => {
    await mount('receiving')
    await wedge(typed)
    expect(scanCalls()).toEqual([{ barcode, product_id: productId }])
  })

  it('кириллический артикул из каталога вне документа уходит исходными символами, без подсказки', async () => {
    await mount('receiving')
    await wedge(CYR)
    expect(scanCalls()).toEqual([{ barcode: CYR }])
  })

  it('код двух карточек документа: запроса нет, оператор видит понятную ошибку', async () => {
    await mount('receiving')
    await wedge(DUP)
    expect(scanCalls()).toEqual([])
    expect(document.querySelector('[data-testid="ff-inbound-scan-error-snackbar"]')?.textContent).toContain(
      PRODUCT_SCAN_AMBIGUOUS_MESSAGE,
    )
    await wedge(WB_A)
    expect(scanCalls()).toEqual([{ barcode: WB_A, product_id: 'P' }])
  })

  it('товар → КИЗ → товар: две единицы товара и одна привязка КИЗ к его строке (R-27)', async () => {
    await mount('receiving')
    await wedge(WB_A)
    await wedge(KIZ_GS)
    await wedge(WB_A)
    expect(scanCalls()).toEqual([
      { barcode: WB_A, product_id: 'P' },
      { barcode: WB_A, product_id: 'P' },
    ])
    expect(kizCalls()).toEqual([{ line_id: 'line-P', cis_code: KIZ_GS }])
  })

  it('КИЗ без GS тоже уходит в ЧЗ, а не в товарный поиск', async () => {
    await mount('receiving')
    await wedge(WB_A)
    await wedge(KIZ_NO_GS)
    expect(scanCalls()).toEqual([{ barcode: WB_A, product_id: 'P' }])
    expect(kizCalls()).toEqual([{ line_id: 'line-P', cis_code: KIZ_NO_GS }])
  })
})

describe('F/S-INB-04: добавление строки в черновик сканом', () => {
  function lineCalls() {
    return calls
      .filter((call) => call.path === '/operations/inbound-intake-requests/r1/lines')
      .map((call) => ({ product_id: call.body?.product_id, expected_qty: call.body?.expected_qty }))
  }

  it.each([
    ['дополнительный WB', WB_A, 'P'],
    ['Ozon-штрихкод', OZN, 'P'],
    ['кириллический SKU', CYR, 'CYRP'],
    ['SKU в русской раскладке', 'Сршт-56005', 'LAT'],
  ])('%s добавляет строку своей карточки', async (_label, typed, productId) => {
    await mount('draft')
    await wedge(typed)
    expect(lineCalls()).toEqual([{ product_id: productId, expected_qty: 1 }])
  })

  it('код двух карточек каталога: строка не добавляется, понятная ошибка', async () => {
    await mount('draft')
    await wedge(DUP)
    expect(lineCalls()).toEqual([])
    expect(document.querySelector('[data-testid="ff-inbound-doc-error"]')?.textContent).toContain(
      PRODUCT_SCAN_AMBIGUOUS_MESSAGE,
    )
  })

  it('external_sku не становится штрихкодом', async () => {
    await mount('draft')
    await wedge('987654')
    expect(lineCalls()).toEqual([])
    expect(document.querySelector('[data-testid="ff-inbound-doc-error"]')?.textContent).toContain(
      'Товар не найден в каталоге селлера',
    )
  })
})
