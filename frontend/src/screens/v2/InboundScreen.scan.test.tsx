// @vitest-environment jsdom
import { act, type ComponentProps } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { PRODUCT_SCAN_AMBIGUOUS_MESSAGE } from '../../utils/productScanResolver'
import { InboundScreen } from './InboundScreen'

// F/S-INB-01: старая «Приёмка» → черновик → поиск товара по точному коду.
// Фикстуры — раздел 9 docs/requirements/WMS-536.md.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

type Props = ComponentProps<typeof InboundScreen>
type ProductRow = Props['products'][number]

const WB_P = '4601234567893'
const WB_A = '4601234567886'
const OZN = 'OZN-987654'
const CYR = 'ФА_МОД8-4а/083/42'
const DUP = 'DUP-536'

const PRODUCTS: ProductRow[] = [
  {
    id: 'P',
    name: 'Платье',
    sku_code: 'AbC-42',
    wb_primary_barcode: WB_P,
    wb_barcodes: [WB_P, WB_A],
    marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: [OZN] }],
  },
  { id: 'Q', name: 'Юбка', sku_code: 'SKU-Q', marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: [DUP] }] },
  { id: 'D', name: 'Шорты', sku_code: DUP },
  { id: 'C', name: 'Фабрика', sku_code: CYR },
  { id: 'N13', name: 'Тринадцать', sku_code: 'SKU-13', wb_primary_barcode: '4601234567899' },
  { id: 'N14', name: 'Четырнадцать', sku_code: 'SKU-14', wb_barcodes: ['04601234567899'] },
]

const noop = () => undefined

let root: Root | null = null
let host: HTMLDivElement | null = null

afterEach(() => {
  act(() => root?.unmount())
  host?.remove()
  root = null
  host = null
})

function mount() {
  const props: Props = {
    opsError: null,
    opsBusy: false,
    isFulfillmentAdmin: true,
    isFulfillmentSeller: false,
    canEditInboundDraft: true,
    warehouses: [{ id: 'w', name: 'Склад', code: 'W1' }],
    selectedWarehouseId: 'w',
    products: PRODUCTS,
    inboundSummaries: [],
    selectedInboundId: 'r',
    setSelectedInboundId: noop,
    inboundDetail: { id: 'r', warehouse_id: 'w', status: 'draft', planned_delivery_date: null, lines: [] },
    inboundRequestLocations: [],
    inboundMovements: [],
    postedInventoryRows: [],
    onCreateInboundRequest: noop,
    onAddInboundLine: noop,
    onSubmitInboundRequest: noop,
    onPrimaryAcceptInboundRequest: noop,
    onOpenInboundBoxByBarcode: noop,
    onScanInboundProductBarcode: noop,
    onCloseInboundBoxIntake: noop,
    onSetInboundLineActualQty: noop,
    onCompleteInboundVerification: noop,
    onSaveInboundLineStorage: noop,
    onReceiveInboundLine: noop,
    onPostInboundRequest: noop,
  }
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  act(() => root!.render(<InboundScreen {...props} />))
}

function type(value: string) {
  const input = host!.querySelector<HTMLInputElement>('[data-testid="inbound-line-product-search"]')!
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  act(() => {
    setter.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

function selected(): string {
  return host!.querySelector<HTMLSelectElement>('[data-testid="inbound-line-product"]')!.value
}

function ambiguityText(): string | null {
  return host!.querySelector('[data-testid="inbound-line-product-search-error"]')?.textContent ?? null
}

describe('F/S-INB-01: точный код в поиске черновика выбирает товар', () => {
  it.each([
    ['основной WB', WB_P, 'P'],
    ['дополнительный WB', WB_A, 'P'],
    ['Ozon-штрихкод, которого нет в полях текстового фильтра', OZN, 'P'],
    ['SKU в другом регистре', 'aBc-42', 'P'],
    ['кириллический SKU', CYR, 'C'],
    ['13 знаков', '4601234567899', 'N13'],
    ['14 знаков с ведущим нулём', '04601234567899', 'N14'],
  ])('%s', (_label, code, productId) => {
    mount()
    type(code)
    expect(selected()).toBe(productId)
    expect(ambiguityText()).toBeNull()
  })

  it('код двух карточек не выбирает ни одну и показывает понятную ошибку', () => {
    mount()
    type(WB_P)
    expect(selected()).toBe('P')
    type(DUP)
    expect(ambiguityText()).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    expect(selected()).toBe('')
  })

  it('external_sku, SKU в русской раскладке и частичный код товар не выбирают', () => {
    mount()
    for (const code of ['987654', 'Сршт-56005', '4601234']) {
      type(code)
      expect(selected()).toBe('')
      expect(ambiguityText()).toBeNull()
    }
  })
})
