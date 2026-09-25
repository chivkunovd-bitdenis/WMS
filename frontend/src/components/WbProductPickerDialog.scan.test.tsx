// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { PRODUCT_SCAN_AMBIGUOUS_MESSAGE } from '../utils/productScanResolver'
import { WbProductPickerDialog, type WbProductPickerCatalogRow } from './WbProductPickerDialog'

// F/S-PICKER-01 в настоящем React-рендере: Enter в поле поиска — это скан.
// Фикстуры — раздел 9 docs/requirements/WMS-536.md.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const WB_P = '4601234567893'
const WB_A = '4601234567886'
const OZN = 'OZN-987654'
const CYR = 'ФА_МОД8-4а/083/42'
const DUP = 'DUP-536'
const KIZ_GS = '010460123456789321SERIAL536\x1d91ABCD\x1d92SIGNATURE536'
const PREFIX = 'ff-inbound-picker'

function row(id: string, fields: Partial<WbProductPickerCatalogRow> = {}): WbProductPickerCatalogRow {
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

const CATALOG: WbProductPickerCatalogRow[] = [
  row('P', {
    name: 'Платье летнее',
    sku_code: 'AbC-42',
    wb_primary_barcode: WB_P,
    wb_barcodes: [WB_P, WB_A],
    marketplace_bindings: [
      { marketplace: 'ozon', external_sku: '987654', external_offer_id: 'offer-536', external_barcodes: [OZN] },
    ],
  }),
  row('Q', { name: 'Юбка', marketplace_bindings: [{ marketplace: 'ozon', external_barcodes: [DUP] }] }),
  row('D', { name: 'Шорты', sku_code: DUP }),
  row('C', { name: 'Фабрика', sku_code: CYR }),
  row('L', { name: 'Куртка', sku_code: 'Chin-56005' }),
  row('N13', { name: 'Тринадцать', wb_primary_barcode: '4601234567899' }),
  row('N14', { name: 'Четырнадцать', wb_barcodes: ['04601234567899'] }),
]

let root: Root | null = null
let host: HTMLDivElement | null = null

afterEach(() => {
  act(() => root?.unmount())
  host?.remove()
  root = null
  host = null
  document.body.innerHTML = ''
})

function mount(onApply = vi.fn()) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  act(() => {
    root!.render(
      <WbProductPickerDialog
        open
        busy={false}
        catalog={CATALOG}
        disabledProductIds={new Set()}
        testIdPrefix={PREFIX}
        variant="ff"
        qtyColumnLabel="Принято"
        onClose={() => undefined}
        onApply={onApply}
      />,
    )
  })
  return onApply
}

function search(): HTMLInputElement {
  return document.querySelector<HTMLInputElement>(`[data-testid="${PREFIX}-search"]`)!
}

function type(value: string) {
  const input = search()
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  act(() => {
    setter.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

function enter() {
  act(() => {
    search().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
  })
}

function scan(value: string) {
  type(value)
  enter()
}

function errorText(): string | null {
  return document.querySelector(`[data-testid="${PREFIX}-scan-error"]`)?.textContent ?? null
}

async function apply(): Promise<void> {
  const button = document.querySelector<HTMLButtonElement>(`[data-testid="${PREFIX}-apply"]`)!
  await act(async () => {
    button.click()
  })
}

describe('F/S-PICKER-01: Enter принимает только точный код карточки', () => {
  it.each([
    ['основной WB', WB_P, 'P'],
    ['дополнительный WB', WB_A, 'P'],
    ['Ozon-штрихкод', OZN, 'P'],
    ['SKU в другом регистре', 'aBc-42', 'P'],
    ['кириллический SKU', CYR, 'C'],
    ['13 знаков', '4601234567899', 'N13'],
    ['14 знаков с ведущим нулём', '04601234567899', 'N14'],
  ])('%s прибавляет единицу своей карточке', async (_label, code, productId) => {
    const onApply = mount()
    scan(code)
    expect(errorText()).toBeNull()
    expect(search().value).toBe('')
    await apply()
    expect(onApply).toHaveBeenCalledWith({ [productId]: 1 })
  })

  it('каждый новый скан — ещё одна единица', async () => {
    const onApply = mount()
    scan(WB_P)
    scan(OZN)
    await apply()
    expect(onApply).toHaveBeenCalledWith({ P: 2 })
  })

  it('код двух карточек — понятная ошибка, ничего не выбрано', () => {
    mount()
    scan(DUP)
    expect(errorText()).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    expect(search().value).toBe(DUP)
    expect(document.querySelector<HTMLButtonElement>(`[data-testid="${PREFIX}-apply"]`)!.disabled).toBe(true)
  })

  it('единственная строка частичного фильтра больше не считается сканом (D6)', () => {
    mount()
    type('Платье')
    expect(document.querySelectorAll(`[data-testid="${PREFIX}-row"]`)).toHaveLength(1)
    enter()
    expect(errorText()).toBe('Товар не найден в каталоге селлера')
    expect(document.querySelector<HTMLButtonElement>(`[data-testid="${PREFIX}-apply"]`)!.disabled).toBe(true)
  })

  it.each([
    ['external_sku', '987654'],
    ['external_offer_id', 'offer-536'],
    ['SKU в русской раскладке (поле раскладку не исправляет)', 'Сршт-56005'],
    ['КИЗ с GS', KIZ_GS],
    ['префикс штрихкода', `4601234`],
  ])('%s — «не найден»', (_label, code) => {
    mount()
    scan(code)
    expect(errorText()).toBe('Товар не найден в каталоге селлера')
  })
})
