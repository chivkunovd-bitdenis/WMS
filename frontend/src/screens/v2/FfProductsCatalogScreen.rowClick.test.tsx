// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfProductsCatalogScreen } from './FfProductsCatalogScreen'
import type { ProductCardData } from './product-card/productCardTypes'

// WMS-490 R1: строка каталога открывает карточку товара при нажатии в любом
// месте строки, кроме её собственных элементов управления (галочка, «ТЗ»,
// «Резервы», значки). Настоящее поведение по нажатиям — здесь; глазами в
// браузере проверено отдельно (см. отчёт куска D3).

vi.mock('../ff/products-fbs/FbsStockDialogContainer', () => ({
  // Окно «Остаток для FBS» — предмет отдельной задачи (WMS-469) со своими
  // тестами. Здесь важно только то, что оно НЕ карточка товара.
  FbsStockDialogContainer: () => <div data-testid="fbs-stock-dialog-stub" />,
}))

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

beforeEach(() => {
  stubFetch()
})

const PRODUCT_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

const catalogRow = {
  id: PRODUCT_ID,
  seller_id: 's-1',
  seller_name: 'Селлер Один',
  name: 'Рюкзак городской, чёрный',
  sku_code: 'BAG-CITY-BLK',
  wb_nm_id: 12345,
  wb_vendor_code: 'BAG-1',
  ozon_sku: null,
  ozon_offer_id: null,
  marketplaces: ['wb'],
  wb_subject_name: 'Рюкзаки',
  wb_primary_image_url: null,
  wb_barcodes: ['1234567890123'],
  wb_primary_barcode: '1234567890123',
  wb_size: null,
  wb_color: null,
  wb_brand: null,
  wb_composition: null,
  packaging_instructions: null,
  country_of_origin_iso_code: null,
  requires_honest_sign: false,
  has_packaging_instructions: false,
  marking_available_count: 0,
}

const cardResponse: ProductCardData = {
  id: PRODUCT_ID,
  seller_id: 's-1',
  seller_name: 'Селлер Один',
  name: 'Рюкзак городской, чёрный',
  sku_code: 'BAG-CITY-BLK',
  wb_nm_id: 12345,
  wb_vendor_code: 'BAG-1',
  ozon_sku: null,
  ozon_offer_id: null,
  wb_subject_name: 'Рюкзаки',
  wb_primary_image_url: null,
  marketplace_bindings: [],
  wb_barcodes: ['1234567890123'],
  wb_primary_barcode: '1234567890123',
  wb_size: null,
  wb_color: null,
  wb_brand: null,
  wb_composition: null,
  packaging_instructions: null,
  country_of_origin_iso_code: null,
  requires_honest_sign: false,
  marketplaces: ['wb'],
  length_mm: null,
  width_mm: null,
  height_mm: null,
  weight_g: null,
  location_warehouses: [],
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/products/ff-catalog-page')) {
        return jsonResponse(200, {
          items: [catalogRow],
          total: 1,
          scope_total: 1,
          limit: 100,
          offset: 0,
          categories: [],
        })
      }
      if (url.includes('/operations/inventory-balances/summary')) {
        return jsonResponse(200, [])
      }
      if (url.includes(`/products/${PRODUCT_ID}/card`)) {
        return jsonResponse(200, cardResponse)
      }
      if (url.includes(`/products/${PRODUCT_ID}/stock-directions`)) {
        return jsonResponse(200, [])
      }
      if (url.includes('/sellers')) {
        return jsonResponse(200, [])
      }
      return jsonResponse(200, [])
    }),
  )
}

let root: Root | null = null
let host: HTMLDivElement | null = null
async function mount() {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(
      <MemoryRouter>
        <FfProductsCatalogScreen
          token="t"
          authHeaders={() => ({ Authorization: 'Bearer t' })}
          sellers={[{ id: 's-1', name: 'Селлер Один' }]}
          warehouses={[]}
          canManageCatalog
          addressStorageEnabled
        />
      </MemoryRouter>,
    )
  })
}

afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

const $ = <T extends HTMLElement = HTMLElement>(testId: string): T => {
  const el = document.querySelector<T>(`[data-testid="${testId}"]`)
  if (!el) throw new Error(`no element ${testId}`)
  return el
}
const maybe = (testId: string) => document.querySelector(`[data-testid="${testId}"]`)

async function flush() {
  // Дать домонтироваться промисам загрузки каталога/карточки.
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
}

describe('WMS-490 R1: клик по строке каталога открывает карточку товара', () => {
  it('нажатие на название строки открывает карточку', async () => {
    await mount()
    await flush()
    expect(maybe('product-card-dialog')).toBeNull()

    await act(async () => { $('ff-product-row').click() })
    await flush()

    expect(maybe('product-card-dialog')).not.toBeNull()
    expect($('product-card-title').textContent).toContain('Рюкзак городской, чёрный')
  })

  it('галочка выбора не открывает карточку и делает своё', async () => {
    await mount()
    await flush()

    const checkboxInput = () =>
      document.querySelector<HTMLInputElement>(`[data-testid="ff-catalog-select-${PRODUCT_ID}"] input`)!

    await act(async () => { checkboxInput().click() })
    await flush()

    expect(maybe('product-card-dialog')).toBeNull()
    expect(checkboxInput().checked).toBe(true)
  })

  it('кнопка «ТЗ» не открывает карточку и открывает окно ТЗ', async () => {
    await mount()
    await flush()

    await act(async () => { $(`ff-packaging-edit-${PRODUCT_ID}`).click() })
    await flush()

    expect(maybe('product-card-dialog')).toBeNull()
    expect(maybe('ff-packaging-dialog')).not.toBeNull()
  })

  it('кнопка «Резервы» не открывает карточку', async () => {
    await mount()
    await flush()

    await act(async () => { $(`ff-catalog-reserves-${PRODUCT_ID}`).click() })
    await flush()

    expect(maybe('product-card-dialog')).toBeNull()
    expect(maybe(`ff-stock-directions-panel-${PRODUCT_ID}`)).not.toBeNull()
  })

  it('значок «Остаток для FBS» не открывает карточку', async () => {
    await mount()
    await flush()

    await act(async () => { $(`ff-catalog-fbs-row-${PRODUCT_ID}`).click() })
    await flush()

    expect(maybe('product-card-dialog')).toBeNull()
    expect(maybe('fbs-stock-dialog-stub')).not.toBeNull()
  })

  it('ревью №1 F7: пустое место ячейки «Резервы» вокруг кнопки открывает карточку', async () => {
    // Раньше stopPropagation стоял на всей TableCell, а не на самой кнопке —
    // клик рядом с кнопкой, не по ней, ничего не делал (ни кнопки, ни карточки).
    await mount()
    await flush()

    const cell = document.querySelector(`[data-testid="ff-catalog-reserves-cell-${PRODUCT_ID}"]`)
    expect(cell).not.toBeNull()
    await act(async () => { cell!.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await flush()

    expect(maybe('product-card-dialog')).not.toBeNull()
    expect(maybe(`ff-stock-directions-panel-${PRODUCT_ID}`)).toBeNull()
  })
})
