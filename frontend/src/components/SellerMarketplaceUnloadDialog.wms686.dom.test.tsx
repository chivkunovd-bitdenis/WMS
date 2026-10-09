// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SellerMarketplaceUnloadDialog } from './SellerMarketplaceUnloadDialog'
import { filenameFromContentDisposition } from '../utils/downloadAuthorizedFile'

// Поле даты требует провайдера локали всего приложения; окну отгрузки оно не нужно для этих проверок.
vi.mock('./WmsDateField', () => ({ WmsDateField: () => null }))

// WMS-686 D6/D8.2: селлер в своей отгрузке видит короба с составом, скачивает XLSX для WB и
// открывает пропуск — всё только на чтение.

type Call = { url: string; method: string; headers: Record<string, string> }

const REQUEST_ID = 'unload-686'

function detail(overrides: Record<string, unknown> = {}) {
  return {
    id: REQUEST_ID,
    warehouse_id: 'w1',
    warehouse_name: 'Склад ФФ',
    status: 'confirmed',
    marketplace: 'wb',
    wb_mp_warehouse_id: 507,
    planned_shipment_date: '2026-10-12',
    lines: [
      { id: 'l1', product_id: 'p1', sku_code: 'SKU-1', product_name: 'Куртка', quantity: 5, picked_qty: 4, kiz_count: 2, requires_honest_sign: true },
      { id: 'l2', product_id: 'p2', sku_code: 'SKU-2', product_name: 'Шапка', quantity: 2, picked_qty: 2, kiz_count: 0, requires_honest_sign: false },
    ],
    boxes: [
      {
        id: 'box-a',
        box_preset: '60_40_40',
        internal_barcode: 'INB-0001',
        closed_at: null,
        lines: [
          { id: 'bl1', product_id: 'p1', sku_code: 'SKU-1', product_name: 'Куртка', quantity: 3 },
          { id: 'bl2', product_id: 'p2', sku_code: 'SKU-2', product_name: 'Шапка', quantity: 2 },
        ],
      },
      { id: 'box-empty', box_preset: '60_40_40', internal_barcode: 'INB-0002', closed_at: null, lines: [] },
    ],
    pick_allocations: [],
    ...overrides,
  }
}

let root: Root
let host: HTMLDivElement
let calls: Call[]
let detailBody: Record<string, unknown>
let xlsxResponse: () => Response
let downloads: string[]

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  calls = []
  downloads = []
  detailBody = detail()
  xlsxResponse = () =>
    new Response(new Blob(['xlsx']), {
      status: 200,
      headers: { 'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent('Упаковка WB.xlsx')}` },
    })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push({ url, method: init?.method ?? 'GET', headers: (init?.headers ?? {}) as Record<string, string> })
      if (url.endsWith('/wb-fbw-packaging.xlsx')) return xlsxResponse()
      if (url.endsWith(`/${REQUEST_ID}/marking-codes`)) {
        return json({
          items: [
            { marking_code_id: 'm1', cis_code: '0104600000000001215abc', product_id: 'p1', line_id: 'l1', intake_document_number: 'ПР-17' },
            { marking_code_id: 'm2', cis_code: '0104600000000001215def', product_id: 'p1', line_id: 'l1', intake_document_number: null },
            { marking_code_id: 'm3', cis_code: '0104600000000002215zzz', product_id: 'p2', line_id: 'l2', intake_document_number: null },
          ],
        })
      }
      if (url.endsWith(`/${REQUEST_ID}/pass`)) {
        return json({
          pass_details: {
            driver_last_name: 'Иванов',
            driver_first_name: 'Пётр',
            car_brand: 'Газель',
            car_number: 'А123ВС77',
          },
          editable: true,
        })
      }
      if (url.endsWith(`/${REQUEST_ID}`)) return json(detailBody)
      if (url.includes('/available-products')) return json([])
      if (url.endsWith('/wb-mp-warehouses')) return json([])
      if (url.endsWith('/products/wb-catalog')) return json([])
      return new Response('{}', { status: 404 })
    }),
  )
  URL.createObjectURL = vi.fn(() => 'blob:wb')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    downloads.push(this.download)
  })
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function render() {
  await act(async () => {
    root.render(
      <SellerMarketplaceUnloadDialog
        open
        requestId={REQUEST_ID}
        token="tok"
        authHeaders={(t) => ({ Authorization: `Bearer ${t}` })}
        warehouseId="w1"
        busy={false}
        onClose={() => {}}
        onRefreshList={async () => {}}
      />,
    )
  })
}

const byId = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`)

describe('SellerMarketplaceUnloadDialog · WMS-686', () => {
  it('WB: есть «Скачать XLSX для WB» и «Пропуск»', async () => {
    await render()
    expect(byId('seller-mp-wb-fbw-export')?.textContent).toBe('Скачать XLSX для WB')
    expect(byId('seller-mp-pass-open')?.textContent).toBe('Пропуск')
  })

  it('Ozon: выгрузки для WB нет, пропуск есть', async () => {
    detailBody = detail({ marketplace: 'ozon' })
    await render()
    expect(byId('seller-mp-wb-fbw-export')).toBeNull()
    expect(byId('seller-mp-pass-open')).not.toBeNull()
  })

  it('короба показаны на чтение: ШК и состав, без действий над ними', async () => {
    await render()
    const boxes = byId('seller-mp-boxes')!
    expect(boxes.textContent).toContain('Короб 1')
    expect(byId('seller-mp-box-barcode-box-a')?.textContent).toBe('INB-0001')
    const lines = byId('seller-mp-box-lines-box-a')!
    expect(lines.textContent).toContain('SKU-1')
    expect(lines.textContent).toContain('Шапка')
    const rows = [...lines.querySelectorAll('tbody tr')].map((tr) => tr.textContent)
    expect(rows).toEqual(['SKU-1Куртка3', 'SKU-2Шапка2'])
    // Пустой короб со ШК виден после коробов с товаром.
    expect(byId('seller-mp-box-barcode-box-empty')?.textContent).toBe('INB-0002')
    expect(boxes.textContent).toContain('Короб 2')
    expect(boxes.querySelectorAll('button, input')).toHaveLength(0)
  })

  it('без коробов блока коробов нет', async () => {
    detailBody = detail({ boxes: [] })
    await render()
    expect(byId('seller-mp-boxes')).toBeNull()
  })

  it('скачивание XLSX для WB идёт с токеном и сохраняет имя файла сервера', async () => {
    await render()
    await act(async () => byId('seller-mp-wb-fbw-export')!.click())
    const xlsx = calls.find((c) => c.url.endsWith('/wb-fbw-packaging.xlsx'))!
    expect(xlsx.url).toContain(`/operations/marketplace-unload-requests/${REQUEST_ID}/wb-fbw-packaging.xlsx`)
    expect(xlsx.headers.Authorization).toBe('Bearer tok')
    expect(downloads).toEqual(['Упаковка WB.xlsx'])
    expect(byId('seller-mp-wb-fbw-export-error')).toBeNull()
  })

  it('ошибка сервера при выгрузке показана в окне, окно остаётся открытым', async () => {
    xlsxResponse = () => json({ detail: 'Нет коробов для выгрузки' }, 409)
    await render()
    await act(async () => byId('seller-mp-wb-fbw-export')!.click())
    expect(byId('seller-mp-wb-fbw-export-error')?.textContent).toContain('Нет коробов для выгрузки')
    expect(downloads).toEqual([])
    expect(byId('seller-mp-unload-dialog')).not.toBeNull()
  })

  it('предупреждение о сроке годности показывается после успешной выгрузки', async () => {
    xlsxResponse = () =>
      new Response(new Blob(['xlsx']), { status: 200, headers: { 'x-wms-warning-code': 'wb-shelf-life-date-required' } })
    await render()
    await act(async () => byId('seller-mp-wb-fbw-export')!.click())
    expect(byId('seller-mp-wb-fbw-export-warning')?.textContent).toContain('дату партии')
    expect(downloads).toEqual(['wb-fbw-packaging.xlsx'])
  })

  it('WB-выгрузка видна в «Утверждено», «Сборка», «Отгружено» и скрыта в остальных статусах', async () => {
    for (const status of ['confirmed', 'collecting', 'shipped']) {
      detailBody = detail({ status })
      await act(async () => root.unmount())
      root = createRoot(host)
      await render()
      expect(byId('seller-mp-wb-fbw-export'), status).not.toBeNull()
    }
    for (const status of ['submitted', 'cancelled']) {
      detailBody = detail({ status })
      await act(async () => root.unmount())
      root = createRoot(host)
      await render()
      expect(byId('seller-mp-wb-fbw-export'), status).toBeNull()
      expect(byId('seller-mp-pass-open'), status).not.toBeNull()
    }
  })

  it('в черновике нет ни выгрузки, ни пропуска, ни коробов', async () => {
    detailBody = detail({ status: 'draft', boxes: [] })
    await render()
    expect(byId('seller-mp-wb-fbw-export')).toBeNull()
    expect(byId('seller-mp-pass-open')).toBeNull()
    expect(byId('seller-mp-boxes')).toBeNull()
  })

  it('таблица строк только на чтение: «Подобрано», «В коробах», «КИЗ»', async () => {
    await render()
    const table = byId('seller-mp-lines-table-readonly')!
    const headers = [...table.querySelectorAll('thead th')].map((th) => th.textContent)
    expect(headers).toEqual(['Артикул', 'Товар', 'Кол-во', 'Подобрано', 'В коробах', 'КИЗ'])
    expect(byId('seller-mp-line-picked-l1')?.textContent).toBe('4')
    expect(byId('seller-mp-line-in-boxes-l1')?.textContent).toBe('3')
    expect(byId('seller-mp-line-in-boxes-l2')?.textContent).toBe('2')
    expect(byId('seller-mp-kiz-toggle-l1')?.textContent).toBe('2')
    // Товару без Честного знака счётчик КИЗ не нужен.
    expect(byId('seller-mp-kiz-toggle-l2')).toBeNull()
    expect(byId('seller-mp-kiz-list-l1')).toBeNull()
  })

  it('счётчик КИЗ раскрывает список кодов товара и сворачивает его повторным нажатием', async () => {
    await render()
    await act(async () => byId('seller-mp-kiz-toggle-l1')!.click())
    const list = byId('seller-mp-kiz-list-l1')!
    const codes = [...list.querySelectorAll('[data-testid="seller-mp-kiz-code"]')].map((n) => n.textContent)
    expect(codes).toEqual(['0104600000000001215abc · приёмка №ПР-17', '0104600000000001215def'])
    expect(calls.some((c) => c.url.endsWith(`/${REQUEST_ID}/marking-codes`) && c.headers.Authorization === 'Bearer tok')).toBe(true)
    await act(async () => byId('seller-mp-kiz-toggle-l1')!.click())
    expect(byId('seller-mp-kiz-list-l1')).toBeNull()
  })

  it('«Пропуск» открывает сведения только на чтение, без сохранения', async () => {
    await render()
    await act(async () => byId('seller-mp-pass-open')!.click())
    expect(byId('fbo-pass-dialog')).not.toBeNull()
    expect(byId('fbo-pass-save')).toBeNull()
    const carNumber = byId('fbo-pass-car_number') as HTMLInputElement
    expect(carNumber.value).toBe('А123ВС77')
    expect(carNumber.readOnly).toBe(true)
    expect(carNumber.disabled).toBe(true)
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(0)
    await act(async () => byId('fbo-pass-close')!.click())
    // Закрытие окна идёт с затуханием: ждём, пока MUI уберёт его из страницы.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 500))
    })
    expect(byId('fbo-pass-dialog')).toBeNull()
  })
})

describe('filenameFromContentDisposition', () => {
  it('берёт закодированное имя, затем простое, затем запасное', () => {
    const encoded = `attachment; filename*=UTF-8''${encodeURIComponent('Пропуск № 5.xlsx')}`
    expect(filenameFromContentDisposition(encoded, 'x.xlsx')).toBe('Пропуск № 5.xlsx')
    expect(filenameFromContentDisposition('attachment; filename="plain.xlsx"', 'x.xlsx')).toBe('plain.xlsx')
    expect(filenameFromContentDisposition(null, 'x.xlsx')).toBe('x.xlsx')
    expect(filenameFromContentDisposition("attachment; filename*=UTF-8''%E0%A4%A", 'x.xlsx')).toBe('x.xlsx')
  })
})
