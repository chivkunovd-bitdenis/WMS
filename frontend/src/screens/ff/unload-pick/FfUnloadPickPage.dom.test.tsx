// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { PRODUCT_SCAN_AMBIGUOUS_MESSAGE } from '../../../utils/productScanResolver'
import { FfUnloadPickPage } from './FfUnloadPickPage'

// WMS-536 · S-OUT-01 «Подбор» отгрузки и поставки ФБС в настоящем React-рендере.
// Сеть подменена: проверяется, какую подсказку товара и какой физический
// источник экран отправляет вместе с кодом и что видит оператор.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

// Фикстуры — раздел 9 docs/requirements/WMS-536.md.
const WB_P = '4601234567893'
const WB_A = '4601234567886'
const OZN = 'OZN-987654'

type Call = { url: string; method: string; body: Record<string, unknown> | null }
let calls: Call[] = []
let routes: Record<string, () => { status: number; body: unknown }> = {}

function looseLocation(cellId: string, code: string, available: number) {
  return {
    storage_location_id: cellId,
    location_code: code,
    quantity: available,
    reserved: 0,
    available,
    picked: 0,
    sources: [{ quantity: available, available, is_loose: true, source_label: 'Россыпью', container_path: [], picked: 0 }],
  }
}

function pickOption(productId: string, sku: string | null, locations: unknown[], extra: Record<string, unknown> = {}) {
  return {
    product_id: productId,
    sku_code: sku,
    product_name: `Товар ${productId}`,
    seller_article: null,
    barcode: null,
    planned_qty: 3,
    picked_qty: 0,
    locations,
    ...extra,
  }
}

function catalogRow(id: string, fields: Record<string, unknown> = {}) {
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

const P = catalogRow('P', {
  sku_code: 'AbC-42',
  wb_primary_barcode: WB_P,
  wb_barcodes: [WB_P, WB_A],
  marketplace_bindings: [
    { marketplace: 'ozon', external_sku: '987654', external_offer_id: 'offer-536', external_barcodes: [OZN] },
  ],
})

const MP_DETAIL = {
  id: 'REQ',
  document_number: 'MP-1',
  display_number: null,
  status: 'collecting',
  seller_id: 'S',
  seller_name: 'ИП Тест',
  planned_shipment_date: null,
  lines: [
    { id: 'L-P', product_id: 'P', sku_code: 'AbC-42', product_name: 'Товар P', quantity: 3, picked_qty: 0 },
    { id: 'L-Q', product_id: 'Q', sku_code: 'SKU-Q', product_name: 'Товар Q', quantity: 3, picked_qty: 0 },
  ],
}

function productReply(productId: string) {
  return {
    kind: 'product',
    storage_location_id: 'CELL-1',
    location_code: 'A-01',
    product_id: productId,
    sku_code: `SKU-${productId}`,
    product_name: `Товар ${productId}`,
    picked_qty: 1,
    allocation_quantity: 1,
    container_kind: null,
    container_id: null,
    container_code: null,
  }
}

function mpRoutes(options: unknown[], catalog: unknown[]) {
  return {
    'GET /api/operations/marketplace-unload-requests/REQ': () => ({ status: 200, body: MP_DETAIL }),
    'GET /api/operations/marketplace-unload-requests/REQ/pick-options': () => ({ status: 200, body: options }),
    'GET /api/products/linked-wb-catalog?seller_id=S': () => ({ status: 200, body: catalog }),
    'POST /api/operations/marketplace-unload-requests/REQ/pick/scan': () => ({ status: 200, body: productReply('P') }),
  }
}

beforeEach(() => {
  calls = []
  routes = {}
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null
    calls.push({ url, method, body })
    const route = routes[`${method} ${url}`]
    if (!route) throw new Error(`unexpected request ${method} ${url}`)
    const reply = route()
    return new Response(JSON.stringify(reply.body), { status: reply.status })
  }))
})

let root: Root | null = null
let host: HTMLDivElement | null = null
afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

const settle = () => act(async () => {
  for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0))
})

async function mount(source?: 'unload' | 'fbs') {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(
      <MemoryRouter>
        <FfUnloadPickPage token="t" requestId="REQ" source={source} />
      </MemoryRouter>,
    )
  })
  await settle()
}

/** Код в поле подбора и Enter — так его отдаёт и сканер, и рука. */
async function scan(text: string) {
  const input = document.querySelector<HTMLInputElement>('[data-testid="pick-scan"]')
  if (!input) throw new Error('поле подбора не отрисовано')
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  await act(async () => {
    setter.call(input, text)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => {
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
  await settle()
}

const scanCalls = () => calls.filter((call) => call.method === 'POST' && call.url.endsWith('/pick/scan'))
const pageText = () => document.body.textContent ?? ''

describe('WMS-536 · S-OUT-01 подбор отгрузки: единый поиск товара', () => {
  it.each([
    ['основной WB-ШК', WB_P],
    ['дополнительный WB-ШК', WB_A],
    ['Ozon-ШК', OZN],
    ['SKU в другом регистре', 'aBc-42'],
  ])('%s находит товар плана: подсказка и единственный источник уходят вместе с кодом', async (_name, code) => {
    routes = mpRoutes(
      [pickOption('P', 'AbC-42', [looseLocation('CELL-1', 'A-01', 5)]), pickOption('Q', 'SKU-Q', [])],
      [P, catalogRow('Q')],
    )
    await mount()
    await scan(code)
    expect(scanCalls()).toHaveLength(1)
    expect(scanCalls()[0].body).toEqual({
      barcode: code,
      product_id: 'P',
      storage_location_id: 'CELL-1',
      container_kind: null,
      container_id: null,
    })
  })

  it('код у двух товаров плана: понятная ошибка, на сервер ничего не уходит (R2)', async () => {
    routes = mpRoutes(
      [pickOption('P', 'AbC-42', [looseLocation('CELL-1', 'A-01', 5)]), pickOption('Q', 'SKU-Q', [])],
      [
        catalogRow('P', { sku_code: 'DUP-536' }),
        catalogRow('Q', { marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: ['DUP-536'] }] }),
      ],
    )
    await mount()
    await scan('DUP-536')
    expect(scanCalls()).toHaveLength(0)
    expect(pageText()).toContain(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
  })

  it('незнакомый код уходит без подсказки товара: ячейку и тару распознаёт сервер (R8)', async () => {
    routes = mpRoutes([pickOption('P', 'AbC-42', [looseLocation('CELL-1', 'A-01', 5)])], [P])
    routes['POST /api/operations/marketplace-unload-requests/REQ/pick/scan'] = () => ({
      status: 200,
      body: { kind: 'location', storage_location_id: 'CELL-1', location_code: 'A-01' },
    })
    await mount()
    await scan('A-01')
    expect(scanCalls()[0].body).toEqual({
      barcode: 'A-01',
      storage_location_id: null,
      container_kind: null,
      container_id: null,
    })
    expect(document.querySelector('[data-testid="pick-source"]')?.textContent).toBe('A-01')
  })

  it('дополнительный WB-ШК товара в двух местах без выбранного места — прежняя просьба уточнить место (R-19)', async () => {
    routes = mpRoutes(
      [pickOption('P', 'AbC-42', [looseLocation('CELL-1', 'A-01', 5), looseLocation('CELL-2', 'A-02', 2)])],
      [P],
    )
    await mount()
    await scan(WB_A)
    expect(scanCalls()).toHaveLength(0)
    expect(pageText()).toContain('AbC-42 лежит в 2 местах')
  })

  it('неоднозначность, найденная сервером, показывается понятным текстом (R2)', async () => {
    routes = mpRoutes([pickOption('P', 'AbC-42', [looseLocation('CELL-1', 'A-01', 5)])], [P])
    routes['POST /api/operations/marketplace-unload-requests/REQ/pick/scan'] = () => ({
      status: 409,
      body: { detail: 'barcode_ambiguous' },
    })
    await mount()
    await scan(WB_A)
    expect(pageText()).toContain(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
  })

  it('русская раскладка в поле подбора не исправляется, товар вне плана не подсказывается', async () => {
    routes = mpRoutes([pickOption('Q', 'SKU-Q', [])], [catalogRow('P', { sku_code: 'Chin-56005' }), catalogRow('Q')])
    await mount()
    await scan('Сршт-56005')
    await scan(WB_A)
    expect(scanCalls().map((call) => call.body?.product_id)).toEqual([undefined, undefined])
  })
})

describe('WMS-536 · S-OUT-01 подбор Ozon-поставки ФБС', () => {
  const OZON_DETAIL = {
    id: 'REQ',
    marketplace: 'ozon',
    name: 'Ozon 1',
    document_number: null,
    display_number: null,
    status: 'open',
    seller_id: 'S',
    seller_name: 'ИП Тест',
    planned_shipment_date: null,
  }

  function ozonRoutes(options: unknown[]) {
    return {
      'GET /api/operations/fbs-supplies/REQ': () => ({ status: 200, body: OZON_DETAIL }),
      'GET /api/operations/fbs-supplies/REQ/pick-options': () => ({ status: 200, body: options }),
      'POST /api/operations/fbs-supplies/REQ/pick/scan': () => ({ status: 200, body: productReply('P') }),
    }
  }

  it('Ozon SKU и Ozon-ШК строки плана подсказывают товар, как и до WMS-536; каталог не грузится', async () => {
    routes = ozonRoutes([
      pickOption('P', '987654', [looseLocation('CELL-1', 'A-01', 5)], { barcode: OZN, seller_article: 'offer-536' }),
    ])
    await mount('fbs')
    await scan('987654')
    await scan(OZN)
    await scan('offer-536')
    expect(scanCalls().map((call) => call.body?.product_id)).toEqual(['P', 'P', undefined])
    expect(calls.some((call) => call.url.includes('linked-wb-catalog'))).toBe(false)
  })

  it('scan_codes из pick-options, если сервер их отдал, тоже находят товар', async () => {
    routes = ozonRoutes([
      pickOption('P', '987654', [looseLocation('CELL-1', 'A-01', 5)], {
        barcode: OZN,
        scan_codes: [OZN, 'OZN-SECOND'],
      }),
    ])
    await mount('fbs')
    await scan('ozn-second')
    expect(scanCalls()[0].body).toMatchObject({ barcode: 'ozn-second', product_id: 'P', storage_location_id: 'CELL-1' })
  })
})
