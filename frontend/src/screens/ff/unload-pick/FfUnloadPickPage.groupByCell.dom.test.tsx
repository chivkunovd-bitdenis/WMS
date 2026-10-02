// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { FfUnloadPickPage } from './FfUnloadPickPage'
import { cellRef, objRef } from './pickStub'

// WMS-637 · C3: настоящий FfUnloadPickPage с настоящим экраном подбора.
// Поставка FBS (source="fbs") показывает список по ячейкам, как окно «Сборка»;
// отгрузка FBO (source не задан) — прежнюю таблицу от товара с кнопками
// «Отложить» и «Завершить подбор». Сервер подменён через fetch.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const originalFetch = globalThis.fetch
let requested: string[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

// Один товар в двух местах: россыпью в ячейке А-01 и в коробе в ячейке Б-02.
const PICK_OPTIONS = [{
  product_id: 'p-1',
  sku_code: 'SKU-1',
  product_name: 'Куртка демо',
  seller_article: null,
  barcode: null,
  planned_qty: 3,
  picked_qty: 0,
  locations: [
    {
      storage_location_id: 'loc-b',
      location_code: 'Б-02',
      quantity: 4,
      reserved: 0,
      available: 4,
      picked: 0,
      sources: [{
        quantity: 4, available: 4, is_loose: false, source_label: 'Короб КР-1', picked: 0,
        container_path: [{ kind: 'box', id: 'box-1', code: 'КР-1', label: 'Короб КР-1' }],
      }],
    },
    {
      storage_location_id: 'loc-a',
      location_code: 'А-01',
      quantity: 2,
      reserved: 0,
      available: 2,
      picked: 0,
      sources: [{ quantity: 2, available: 2, is_loose: true, source_label: 'Россыпью', container_path: [], picked: 0 }],
    },
  ],
}]

const DETAIL = {
  id: 'doc-1',
  document_number: 'D-1',
  display_number: 'D-1',
  status: 'picking',
  seller_id: 'seller-1',
  seller_name: 'Селлер',
  planned_shipment_date: null,
}

async function server(input: RequestInfo | URL): Promise<Response> {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms.test')
  const path = url.pathname.replace(/^\/api/, '')
  requested.push(path)
  if (path === '/products/linked-wb-catalog') return json([])
  if (path === '/operations/fbs-supplies/doc-1') return json({ ...DETAIL, marketplace: 'wb' })
  if (path === '/operations/marketplace-unload-requests/doc-1') {
    return json({ ...DETAIL, lines: [{ id: 'line-1', product_id: 'p-1', sku_code: 'SKU-1', product_name: 'Куртка демо', quantity: 3, picked_qty: 0 }] })
  }
  if (/^\/operations\/(fbs-supplies|marketplace-unload-requests)\/doc-1\/pick-options$/.test(path)) return json(PICK_OPTIONS)
  return json({ detail: `unexpected ${path}` }, 404)
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  requested = []
  globalThis.fetch = server as typeof fetch
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(() => {
  act(() => root.unmount())
  host.remove()
  globalThis.fetch = originalFetch
})

async function settle() {
  for (let step = 0; step < 5; step += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

async function renderPage(source?: 'fbs') {
  act(() => {
    root.render(
      <MemoryRouter>
        <FfUnloadPickPage token="t" requestId="doc-1" source={source} hideHeader />
      </MemoryRouter>,
    )
  })
  await settle()
}

const byTestId = (testId: string) => host.querySelector(`[data-testid="${testId}"]`)

describe('WMS-637 · FfUnloadPickPage: подбор поставки FBS — по ячейкам, отгрузка FBO — от товара', () => {
  it('source="fbs": таблица по ячейкам, как в «Сборке»; кнопок «Отложить»/«Завершить подбор» нет', async () => {
    await renderPage('fbs')

    expect(requested).toContain('/operations/fbs-supplies/doc-1/pick-options')
    expect(byTestId('fbs-cell-pick-table')).not.toBeNull()
    expect(byTestId('pick-table')).toBeNull()
    expect(byTestId('pick-pause')).toBeNull()
    expect(byTestId('pick-complete')).toBeNull()

    // Сначала ячейка, внутри неё тара и товар; ячейки — по порядку адресов.
    const items = [...host.querySelectorAll('[data-testid^="fbs-pick-item-"]')]
      .map((one) => one.getAttribute('data-testid')!.slice('fbs-pick-item-'.length))
    const cellA = cellRef('loc-a')
    const cellB = cellRef('loc-b')
    const box = objRef('box-1')
    expect(items.map((key) => key.split('|')[1] ?? key)).toEqual([cellA, cellA, cellB, box, box])
    expect(items[0]).toBe(cellA)
    expect(items[2]).toBe(cellB)
    expect(items[3]).toBe(box)

    // Поле «Снять» стоит прямо в строке места — как в «Сборке».
    expect(byTestId(`pick-place-qty-p-1-${cellA}`)).not.toBeNull()
    expect(byTestId(`pick-place-qty-p-1-${box}`)).not.toBeNull()
  })

  it('без source (отгрузка FBO): прежняя таблица от товара и кнопки «Отложить»/«Завершить подбор»', async () => {
    await renderPage()

    expect(requested).toContain('/operations/marketplace-unload-requests/doc-1/pick-options')
    expect(byTestId('pick-table')).not.toBeNull()
    expect(byTestId('fbs-cell-pick-table')).toBeNull()
    expect(host.querySelector('[data-testid^="fbs-pick-item-"]')).toBeNull()
    expect(byTestId('pick-pause')?.textContent).toContain('Отложить')
    expect(byTestId('pick-complete')?.textContent).toContain('Завершить подбор')
  })
})
