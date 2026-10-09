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
// WMS-709: сценарий текущего теста — маркетплейс поставки, ответы подбора и отказ сохранения.
let fixture: { marketplace: 'wb' | 'ozon'; options: unknown; setFails: boolean }

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
  if (path === '/operations/fbs-supplies/doc-1') return json({ ...DETAIL, marketplace: fixture.marketplace })
  if (path === '/operations/marketplace-unload-requests/doc-1') {
    return json({ ...DETAIL, lines: [{ id: 'line-1', product_id: 'p-1', sku_code: 'SKU-1', product_name: 'Куртка демо', quantity: 3, picked_qty: 0 }] })
  }
  if (path === '/operations/fbs-supplies/doc-1/pick/set') {
    return fixture.setFails ? json({ detail: 'Сервер не принял снятие' }, 500) : json({ quantity: 0 })
  }
  if (/^\/operations\/(fbs-supplies|marketplace-unload-requests)\/doc-1\/pick-options$/.test(path)) return json(fixture.options)
  return json({ detail: `unexpected ${path}` }, 404)
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  requested = []
  fixture = { marketplace: 'wb', options: PICK_OPTIONS, setFails: false }
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

// WMS-709 этап 2: собранный товар на вкладке «Подбор» поставки — зелёные места,
// скрытое место без снятий, отказ сохранения возвращает серверное число.
const COMPLETE = [{
  product_id: 'p-1', sku_code: 'SKU-1', product_name: 'Куртка демо', seller_article: null, barcode: null,
  planned_qty: 2, picked_qty: 2,
  locations: [
    {
      storage_location_id: 'loc-a', location_code: 'А-01', quantity: 2, reserved: 0, available: 1, picked: 1,
      sources: [{ quantity: 2, available: 1, is_loose: true, source_label: 'Россыпью', container_path: [], picked: 1 }],
    },
    {
      storage_location_id: 'loc-b', location_code: 'Б-02', quantity: 1, reserved: 0, available: 0, picked: 1,
      sources: [{
        quantity: 1, available: 0, is_loose: false, source_label: 'Короб КР-1', picked: 1,
        container_path: [{ kind: 'box', id: 'box-1', code: 'КР-1', label: 'Короб КР-1' }],
      }],
    },
    {
      storage_location_id: 'loc-c', location_code: 'В-03', quantity: 3, reserved: 0, available: 3, picked: 0,
      sources: [{ quantity: 3, available: 3, is_loose: true, source_label: 'Россыпью', container_path: [], picked: 0 }],
    },
  ],
}]

function greenBy(testId: string): boolean {
  const row = byTestId(testId)?.closest('tr')
  if (!row) throw new Error(`нет строки с полем ${testId}`)
  const background = getComputedStyle(row).backgroundColor
  return background !== '' && background !== 'transparent' && background !== 'rgba(0, 0, 0, 0)'
}

function leftOf(testId: string): string | undefined {
  const row = byTestId(testId)?.closest('tr')
  const names = [...host.querySelectorAll('thead th')].map((th) => (th.textContent ?? '').replace(/\s+/g, ''))
  const index = names.indexOf('Осталосьподобрать')
  if (index < 0) throw new Error(`нет колонки «Осталось подобрать»; есть: ${names.join(' | ')}`)
  return row?.children[index]?.textContent?.trim()
}

async function typeValue(field: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, value)
    field.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

async function waitMs(ms: number) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms))
  })
}

describe('WMS-709 этап 2 · поставка: собранные места и отказ сохранения', () => {
  it('C13: Ozon FBS — собранные места зелёные', async () => {
    fixture.marketplace = 'ozon'
    fixture.options = COMPLETE
    await renderPage('fbs')

    expect(byTestId('fbs-cell-pick-table')).not.toBeNull()
    expect(greenBy(`pick-place-qty-p-1-${cellRef('loc-a')}`)).toBe(true)
    expect(greenBy(`pick-place-qty-p-1-${objRef('box-1')}`)).toBe(true)
    expect(byTestId(`pick-place-qty-p-1-${cellRef('loc-c')}`)).toBeNull()
    expect(leftOf(`pick-place-qty-p-1-${cellRef('loc-a')}`)).toBe('0')
  })

  it('C15: отказ сохранения — ошибка и перечитывание', async () => {
    fixture.setFails = true
    fixture.options = COMPLETE
    await renderPage('fbs')

    await typeValue(byTestId(`pick-place-qty-p-1-${cellRef('loc-a')}`) as HTMLInputElement, '0')
    await waitMs(600)

    expect(requested).toContain('/operations/fbs-supplies/doc-1/pick/set')
    expect(byTestId('unload-pick-error')?.textContent).toContain('Сервер не принял снятие')
    expect((byTestId(`pick-place-qty-p-1-${cellRef('loc-a')}`) as HTMLInputElement).value).toBe('1')
    expect(greenBy(`pick-place-qty-p-1-${cellRef('loc-a')}`)).toBe(true)
    expect(byTestId(`pick-place-qty-p-1-${cellRef('loc-c')}`)).toBeNull()
  })
})
