// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { WbProductPickerCatalogRow } from '../../components/WbProductPickerDialog'
import { PRODUCT_SCAN_AMBIGUOUS_MESSAGE } from '../../utils/productScanResolver'
import { FfMarketplaceUnloadBoxAddDialog } from './FfMarketplaceUnloadBoxAddDialog'

// WMS-536 · S-OUT-02 «Наполнить короб» отгрузки на маркетплейс в настоящем
// React-рендере: работает и глобальный клавиатурный сканер, и ручное поле.
// Сеть подменена — проверяется, что именно окно отправляет на сервер.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

// Фикстуры — раздел 9 docs/requirements/WMS-536.md.
const WB_P = '4601234567893'
const WB_A = '4601234567886'
const OZN = 'OZN-987654'
const CYR = 'ФА_МОД8-4а/083/42'
const GS = '\x1d'

function catalogRow(id: string, fields: Partial<WbProductPickerCatalogRow> = {}): WbProductPickerCatalogRow {
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

function planRow(productId: string, sku: string) {
  return {
    product_id: productId,
    sku_code: sku,
    product_name: `Товар ${productId}`,
    planned_qty: 5,
    picked_qty: 0,
    boxed_qty: 0,
    locations: [],
  }
}

type Call = { url: string; method: string; body: Record<string, unknown> | null }
let calls: Call[] = []
let pickOptions: unknown[] = []
let scanReply: (body: Record<string, unknown>) => { status: number; body: unknown } = () => ({
  status: 200,
  body: productReply('P'),
})

function productReply(productId: string) {
  return {
    kind: 'product',
    product_id: productId,
    picked_qty: 1,
    id: `line-${productId}`,
    sku_code: `SKU-${productId}`,
    product_name: `Товар ${productId}`,
    quantity: 1,
    storage_location_id: null,
  }
}

beforeEach(() => {
  calls = []
  pickOptions = [planRow('P', 'AbC-42'), planRow('Q', 'SKU-Q')]
  scanReply = () => ({ status: 200, body: productReply('P') })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null
    calls.push({ url, method, body })
    if (url.endsWith('/pick-options')) {
      return new Response(JSON.stringify(pickOptions), { status: 200 })
    }
    if (url.endsWith('/boxes/BOX/scan') && body) {
      const reply = scanReply(body)
      return new Response(JSON.stringify(reply.body), { status: reply.status })
    }
    throw new Error(`unexpected request ${method} ${url}`)
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

async function mount(catalog: WbProductPickerCatalogRow[]) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(
      <FfMarketplaceUnloadBoxAddDialog
        open
        onClose={() => {}}
        requestId="REQ"
        boxId="BOX"
        boxLabel="Короб 1"
        readOnly={false}
        token="t"
        addressStorageEnabled
        catalogById={new Map(catalog.map((row) => [row.id, row]))}
        warehouseStockByProductId={new Map()}
        onUpdated={async () => {}}
      />,
    )
  })
  await settle()
}

// Физические клавиши русской раскладки для символов, которые встречаются в тестах.
const RU_KEYS: Record<string, [code: string, shift: boolean]> = {
  С: ['KeyC', true], р: ['KeyH', false], ш: ['KeyI', false], т: ['KeyN', false],
  Ф: ['KeyA', true], А: ['KeyF', true], М: ['KeyV', true], О: ['KeyJ', true], Д: ['KeyL', true],
  а: ['KeyF', false],
}

/** Быстрая пачка клавиатурного сканера вне поля ввода; `\x1d` — это Ctrl+]. */
async function wedgeScan(text: string) {
  await act(async () => {
    for (const ch of text) {
      const [code, shift] = RU_KEYS[ch] ?? ['', false]
      const init = ch === GS
        ? { key: ']', code: 'BracketRight', ctrlKey: true }
        : { key: ch, code, shiftKey: shift }
      document.body.dispatchEvent(new KeyboardEvent('keydown', { ...init, bubbles: true, cancelable: true }))
    }
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  })
  await settle()
}

/** Ручной ввод в поле окна и Enter. */
async function manualScan(text: string) {
  const input = document.querySelector<HTMLInputElement>('[data-testid="ff-mp-box-add-scan-input"]')!
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

const scanCalls = () => calls.filter((call) => call.url.endsWith('/boxes/BOX/scan'))
const errorText = () =>
  document.querySelector('[data-testid="ff-mp-box-add-error"]')?.textContent ?? null

describe('WMS-536 · S-OUT-02 наполнение короба: единый поиск товара', () => {
  it.each([
    ['основной WB-ШК', WB_P, WB_P],
    ['дополнительный WB-ШК', WB_A, WB_A],
    ['Ozon-ШК', OZN, OZN],
    ['SKU в другом регистре', 'aBc-42', 'aBc-42'],
  ])('сканер: %s находит товар плана и уходит подсказкой вместе с кодом', async (_name, scanned, sent) => {
    await mount([P, catalogRow('Q')])
    await wedgeScan(scanned)
    expect(scanCalls()).toHaveLength(1)
    expect(scanCalls()[0].body).toMatchObject({ barcode: sent, product_id: 'P', quantity: 1 })
    expect(errorText()).toBeNull()
  })

  it('Ozon SKU из привязки не становится кодом товара на клиенте (R4)', async () => {
    await mount([P])
    await wedgeScan('987654')
    expect(scanCalls()[0].body).toEqual({ barcode: '987654', quantity: 1, allow_over_plan: false })
  })

  it('кириллический SKU со сканера уходит исходными символами, а не латиницей (R7)', async () => {
    await mount([catalogRow('P', { sku_code: CYR })])
    await wedgeScan(CYR)
    expect(scanCalls()[0].body).toMatchObject({ barcode: CYR, product_id: 'P' })
  })

  it('русская раскладка: сканер находит латинский SKU запасным кандидатом, ручной ввод — нет', async () => {
    await mount([catalogRow('P', { sku_code: 'Chin-56005' })])
    await wedgeScan('Сршт-56005')
    expect(scanCalls()[0].body).toMatchObject({ barcode: 'Chin-56005', product_id: 'P' })

    await manualScan('Сршт-56005')
    expect(scanCalls()).toHaveLength(2)
    expect(scanCalls()[1].body).toEqual({ barcode: 'Сршт-56005', quantity: 1, allow_over_plan: false })
  })

  it('код у двух товаров плана уходит без подсказки; отказ сервера — понятный текст, следующий скан работает (R2)', async () => {
    await mount([
      catalogRow('P', { sku_code: 'DUP-536', wb_barcodes: [WB_A] }),
      catalogRow('Q', { marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: ['DUP-536'] }] }),
    ])
    scanReply = (body) =>
      body.barcode === WB_A
        ? { status: 200, body: productReply('P') }
        : { status: 409, body: { detail: 'barcode_ambiguous' } }
    await wedgeScan('DUP-536')
    expect(errorText()).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    expect(scanCalls().map((call) => call.body)).toEqual([
      { barcode: 'DUP-536', quantity: 1, allow_over_plan: false },
    ])

    await manualScan('dup-536')
    expect(errorText()).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    expect(scanCalls()[1].body).toEqual({ barcode: 'dup-536', quantity: 1, allow_over_plan: false })

    await wedgeScan(WB_A)
    expect(scanCalls()).toHaveLength(3)
    expect(scanCalls()[2].body).toMatchObject({ barcode: WB_A, product_id: 'P' })
    expect(errorText()).toBeNull()
  })

  it('товар вне плана не подсказывается, даже если он есть в каталоге селлера (R5)', async () => {
    pickOptions = [planRow('Q', 'SKU-Q')]
    await mount([P, catalogRow('Q')])
    await wedgeScan(WB_A)
    expect(scanCalls()[0].body).toEqual({ barcode: WB_A, quantity: 1, allow_over_plan: false })
  })

  it('ячейка по-прежнему распознаётся сервером раньше товара, даже если её код — код товара (R8)', async () => {
    pickOptions = [{
      ...planRow('P', 'CELL-PROD-536'),
      locations: [{ storage_location_id: 'CELL-1', location_code: 'A-01', quantity: 3, reserved: 0, available: 3 }],
    }]
    await mount([catalogRow('P', { sku_code: 'CELL-PROD-536' })])
    scanReply = () => ({ status: 200, body: { kind: 'location', storage_location_id: 'CELL-1', location_code: 'A-01' } })
    await wedgeScan('CELL-PROD-536')
    expect(scanCalls()[0].body).toMatchObject({ barcode: 'CELL-PROD-536' })
    expect(document.querySelector('[data-testid="ff-mp-box-add-active-location"]')?.textContent).toContain('A-01')

    // Выбранная сканом ячейка уходит со следующим сканом товара, как раньше.
    scanReply = () => ({ status: 200, body: productReply('P') })
    await wedgeScan('cell-prod-536')
    expect(scanCalls()[1].body).toMatchObject({ product_id: 'P', storage_location_id: 'CELL-1' })
  })

  describe('код ячейки или тары совпал с двумя товарами плана (R8, ревью F2)', () => {
    // CELL-DUP и BOX-DUP — одновременно WB-ШК товара P и Ozon-ШК товара Q.
    const catalog = () => [
      catalogRow('P', { sku_code: 'AbC-42', wb_barcodes: [WB_A, 'CELL-DUP', 'BOX-DUP', 'BOX-DUP-2'] }),
      catalogRow('Q', { marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: ['CELL-DUP', 'BOX-DUP', 'BOX-DUP-2'] }] }),
    ]
    beforeEach(() => {
      const cell = { storage_location_id: 'CELL-1', location_code: 'A-01', quantity: 3, reserved: 0, available: 3 }
      pickOptions = [{ ...planRow('P', 'AbC-42'), locations: [cell] }, { ...planRow('Q', 'SKU-Q'), locations: [cell] }]
    })
    const containerReply = (id: string, code: string) => ({
      status: 200,
      body: { kind: 'container', storage_location_id: 'CELL-1', location_code: 'A-01', container_kind: 'box', container_id: id, container_code: code },
    })

    it('ячейка: запрос уходит без подсказки, ячейка выбирается, следующий товар идёт с ней', async () => {
      await mount(catalog())
      scanReply = (body) =>
        body.barcode === 'CELL-DUP'
          ? { status: 200, body: { kind: 'location', storage_location_id: 'CELL-1', location_code: 'A-01' } }
          : { status: 200, body: productReply('P') }
      await wedgeScan('CELL-DUP')
      expect(scanCalls().map((call) => call.body)).toEqual([
        { barcode: 'CELL-DUP', quantity: 1, allow_over_plan: false },
      ])
      expect(errorText()).toBeNull()
      expect(document.querySelector('[data-testid="ff-mp-box-add-active-location"]')?.textContent).toContain('A-01')

      await wedgeScan(WB_A)
      expect(scanCalls()[1].body).toEqual({
        barcode: WB_A,
        product_id: 'P',
        quantity: 1,
        allow_over_plan: false,
        storage_location_id: 'CELL-1',
      })
    })

    it('тара A → тара B таким же кодом: выбранная тара уходит как есть, сервер меняет её, товар идёт из B', async () => {
      await mount(catalog())
      scanReply = (body) => {
        if (body.barcode === 'BOX-DUP') return containerReply('BOX-A', 'WHB-A')
        if (body.barcode === 'BOX-DUP-2') return containerReply('BOX-B', 'WHB-B')
        return { status: 200, body: productReply('P') }
      }
      await wedgeScan('BOX-DUP')
      expect(scanCalls()[0].body).toEqual({ barcode: 'BOX-DUP', quantity: 1, allow_over_plan: false })
      expect(document.querySelector('[data-testid="ff-mp-box-add-active-location"]')?.textContent).toContain('WHB-A')

      await wedgeScan('BOX-DUP-2')
      expect(scanCalls()[1].body).toEqual({
        barcode: 'BOX-DUP-2',
        quantity: 1,
        allow_over_plan: false,
        storage_location_id: 'CELL-1',
        container_kind: 'box',
        container_id: 'BOX-A',
      })
      expect(document.querySelector('[data-testid="ff-mp-box-add-active-location"]')?.textContent).toContain('WHB-B')

      await wedgeScan(WB_A)
      expect(scanCalls()[2].body).toEqual({
        barcode: WB_A,
        product_id: 'P',
        quantity: 1,
        allow_over_plan: false,
        storage_location_id: 'CELL-1',
        container_kind: 'box',
        container_id: 'BOX-B',
      })
      expect(errorText()).toBeNull()
    })

    it('неоднозначность товара от сервера не меняет выбранную тару', async () => {
      await mount(catalog())
      scanReply = (body) =>
        body.barcode === 'BOX-DUP'
          ? containerReply('BOX-A', 'WHB-A')
          : { status: 409, body: { detail: 'barcode_ambiguous' } }
      await wedgeScan('BOX-DUP')
      await wedgeScan('CELL-DUP')
      expect(errorText()).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
      expect(scanCalls()[1].body).toEqual({
        barcode: 'CELL-DUP',
        quantity: 1,
        allow_over_plan: false,
        storage_location_id: 'CELL-1',
        container_kind: 'box',
        container_id: 'BOX-A',
      })
      expect(document.querySelector('[data-testid="ff-mp-box-add-active-location"]')?.textContent).toContain('WHB-A')
    })
  })

  it('КИЗ с GS не ищется как товар и уходит на сервер с разделителями (R9)', async () => {
    await mount([P])
    scanReply = () => ({ status: 422, body: { detail: 'barcode_unknown' } })
    const kiz = `010460123456789321SERIAL536${GS}91ABCD${GS}92SIGNATURE536`
    await wedgeScan(kiz)
    expect(scanCalls()[0].body).toEqual({ barcode: kiz, quantity: 1, allow_over_plan: false })
  })

  it('неоднозначность, найденная сервером, показывается понятным текстом (R2)', async () => {
    await mount([P])
    scanReply = () => ({ status: 409, body: { detail: 'barcode_ambiguous' } })
    await wedgeScan(WB_A)
    expect(errorText()).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
  })

  it('13 и 14 знаков — разные коды: GTIN-14 не подменяется товаром с EAN-13 (R-36)', async () => {
    await mount([P])
    await wedgeScan(`0${WB_P}`)
    expect(scanCalls()[0].body).toEqual({ barcode: `0${WB_P}`, quantity: 1, allow_over_plan: false })
  })
})
