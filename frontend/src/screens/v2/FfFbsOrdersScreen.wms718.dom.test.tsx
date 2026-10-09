// @vitest-environment jsdom
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { click, flush, headers, installNetwork, json, mount, order, page, refresh, row, SERVER_NOW, tab } from './test-support/fbsOrdersDom'
import type { FbsAssemblyTask, FbsSupplyWorklistItem, FbsWorklistOrder } from './fbsApi'
import { muiTheme } from '../../mui/theme'
import { alpha } from '@mui/material/styles'

let dispose: (() => Promise<void>) | undefined
afterEach(async () => { await dispose?.(); dispose = undefined; vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

function supply(id = 'supply-b'): FbsSupplyWorklistItem {
  return {
    id, marketplace: 'wb', wb_supply_id: 'WB-GI-718', name: 'Поставка нового контекста',
    status: 'assembling', seller: order().seller, wb_warehouse: order().wb_warehouse,
    wms_warehouse: order().wms_warehouse, orders_count: 2, units_count: 2,
    picked_units_count: 0, boxes_count: 1, planned_shipment_date: null, can_add_orders: true,
  }
}

async function open(items: FbsWorklistOrder[], withTask = false) {
  const supplied = supply()
  const task: FbsAssemblyTask = {
    id: 'task-718', number: '718', created_at: SERVER_NOW, created_by: { id: null, name: 'Оператор' },
    supplies: [{ id: supplied.id, marketplace: 'wb', name: supplied.name, seller: supplied.seller,
      status: 'assembling', orders_count: 2, picked_count: 0, units_count: 2, picked_units_count: 0, packed_count: 0 }],
  }
  const base = installNetwork((url) => {
    if (url.pathname.endsWith('/fbs-orders/worklist')) return json(page(items))
    if (url.pathname.endsWith('/fbs-supplies/worklist')) return json({ items: [supplied], server_now: SERVER_NOW })
    throw new Error(`Unexpected WMS-718 request: ${url}`)
  })
  const network = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).split('?')[0].endsWith('/fbs-assembly-tasks')) {
      expect(init?.method ?? 'GET').toBe('GET')
      return json({ items: withTask ? [task] : [] })
    }
    return base(input, init)
  })
  dispose = await mount(network, muiTheme)
}

function table(): HTMLTableElement {
  const element = document.querySelector('table[data-testid="fbs-worklist-table"], table[data-testid="fbs-18-supplies-table"]')
  expect(element).toBeTruthy()
  return element as HTMLTableElement
}
function container() { return table().closest('.MuiTableContainer-root') as HTMLElement }

function assertStickyStructure() {
  const current = table()
  expect(document.querySelectorAll('thead')).toHaveLength(1)
  expect(current.tHead).toBeTruthy()
  expect(current.tBodies).toHaveLength(1)
  expect(current.tHead!.closest('table')).toBe(current)
  expect(current.tBodies[0].closest('table')).toBe(current)
  const area = container()
  expect(area.contains(current.tHead)).toBe(true)
  expect(area.contains(current.tBodies[0])).toBe(true)
  const areaStyle = getComputedStyle(area)
  expect(areaStyle.maxHeight).toMatch(/calc\(.*100vh.*\)/)
  // jsdom does not compute overflow-y's implicit "auto" from overflow-x.
  expect(areaStyle.overflowY || areaStyle.overflow || areaStyle.overflowX).toMatch(/auto|scroll/)
  const bodyLayer = Math.max(0, ...Array.from(
    current.tBodies[0].querySelectorAll('td, [data-testid^="fbs-product-photo-"]'),
    (node) => Number.parseInt(getComputedStyle(node).zIndex, 10) || 0,
  ))
  for (const cell of Array.from(current.tHead!.rows[0].cells)) {
    const style = getComputedStyle(cell)
    expect(style.position).toBe('sticky')
    expect(style.top).toBe('0px')
    expect(style.backgroundColor).not.toBe('')
    const channels = style.backgroundColor.match(/^rgba?\(([^)]+)\)$/)?.[1].split(',').map(Number)
    expect(channels, 'header background must resolve to an RGB color').toBeTruthy()
    expect(channels!.length === 4 ? channels![3] : 1, 'header background alpha must be 1').toBe(1)
    expect(style.backgroundColor).toBe('rgb(255, 255, 255)')
    const tint = alpha(muiTheme.palette.primary.main, 0.08)
    expect(style.backgroundImage).toBe(`linear-gradient(${tint}, ${tint})`)
    expect(Number.parseInt(style.zIndex, 10)).toBeGreaterThan(bodyLayer)
  }
}

function consistentCells(currentRow: HTMLTableRowElement) {
  const head = table().tHead!.rows[0]
  expect(currentRow.cells).toHaveLength(head.cells.length)
  Array.from(currentRow.cells).forEach((cell, index) => {
    const bodyWidth = getComputedStyle(cell).minWidth
    const headerWidth = getComputedStyle(head.cells[index]).minWidth
    if (bodyWidth && bodyWidth !== '0px' && headerWidth && headerWidth !== '0px') expect(bodyWidth).toBe(headerWidth)
  })
}

describe('WMS-718 applied header styles and DOM state, without layout claims', () => {
  it('C2 keeps one opaque sticky header with the body in a bounded scroll container', async () => {
    await open(Array.from({ length: 24 }, (_, index) => order(`order-${index}`)))
    expect(table().tBodies[0].rows).toHaveLength(24)
    assertStickyStructure()
  })

  it.each(['Новые', 'Отменённые'])('C3 aligns semantic cells and width rules after size replaces SKU on %s', async (label) => {
    const wb = order('wb-long'); wb.product.name = 'Очень длинное название товара '.repeat(8)
    wb.product.seller_article = 'ДЛИННЫЙ-АРТИКУЛ-718'; wb.product.size = 'Универсальный'
    const ozon = order('ozon-long'); ozon.marketplace = 'ozon'
    ozon.positions = [
      { id: 'pos-1', product_id: 'pos-1', name: 'Длинный Ozon товар '.repeat(10), seller_article: 'ART-1', sku: 'SKU-1', barcode: 'BAR-1', size: 'S', quantity: 3, reserved_quantity: 3, picked_quantity: 0 },
      { id: 'pos-2', product_id: 'pos-2', name: 'Вторая позиция', seller_article: 'ART-2', sku: 'SKU-2', barcode: 'BAR-2', size: 'XL', quantity: 1, reserved_quantity: 1, picked_quantity: 0 },
    ]
    await open([wb, ozon]); if (label !== 'Новые') await tab(label)
    expect(headers()).toEqual(['', 'Товар', 'Артикул продавца', 'Размер', 'ШК', 'Селлер', 'Маршрут сдачи', 'Отгрузить до', ...(label === 'Новые' ? [] : ['Статус'])])
    for (const item of [wb, ozon]) {
      consistentCells(row(item.id))
      expect(row(item.id).closest('table')).toBe(table())
      expect(row(item.id).cells[2].textContent).toContain(item === wb ? 'ДЛИННЫЙ-АРТИКУЛ-718' : 'ART-1')
      expect(row(item.id).cells[3].textContent).toBe(item === wb ? 'Универсальный' : 'SXL')
      expect(row(item.id).cells[4].textContent).toContain(item === wb ? 'BAR-719' : 'BAR-1')
    }
    assertStickyStructure()
  })

  it('C4 reserves measured panel space and keeps selection and header through resize and refresh', async () => {
    vi.useFakeTimers(); vi.setSystemTime(SERVER_NOW)
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
    let panelHeight = 80
    const callbacks: Array<() => void> = []
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: () => void) { callbacks.push(callback) }
      observe() {} unobserve() {} disconnect() {}
    })
    const originalRect = HTMLElement.prototype.getBoundingClientRect
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      return this.getAttribute('data-testid') === 'fbs-selection-bar'
        ? new DOMRect(0, 0, 600, panelHeight) : originalRect.call(this)
    })
    try {
      await open([order()])
      const unselectedHeight = getComputedStyle(container()).maxHeight
      await click(row().querySelector('input[type="checkbox"]'))
      expect((row().querySelector('input') as HTMLInputElement).checked).toBe(true)
      expect(document.querySelector('[data-testid="fbs-selection-bar"]')).toBeTruthy()
      expect(getComputedStyle(container()).maxHeight).toContain('110px')
      panelHeight = 120
      await act(async () => { window.dispatchEvent(new Event('resize')); callbacks.forEach((callback) => callback()) })
      expect(getComputedStyle(container()).maxHeight).toContain('150px')
      await act(async () => callbacks.forEach((callback) => callback()))
      expect(getComputedStyle(container()).maxHeight).toContain('150px')
      await refresh(); assertStickyStructure()
      await act(async () => { await vi.advanceTimersByTimeAsync(30_000) }); await flush()
      expect((row().querySelector('input') as HTMLInputElement).checked).toBe(true)
      assertStickyStructure()
      await click(row().querySelector('input[type="checkbox"]'))
      expect(document.querySelector('[data-testid="fbs-selection-bar"]')).toBeNull()
      expect(getComputedStyle(container()).maxHeight).toBe(unselectedHeight)
      assertStickyStructure()
    } finally { delete (document as unknown as Record<string, unknown>).hidden }
  })

  it.each(['В работе', 'В доставке', 'Завершённые', 'Отменённые'])('C5 preserves %s columns, row spans and one sticky header', async (label) => {
    await open([order()], true); await tab(label)
    if (label === 'Отменённые') {
      expect(headers()).toEqual(expect.arrayContaining(['Товар', 'Селлер', 'Маршрут сдачи', 'Отгрузить до', 'Статус']))
      consistentCells(row())
    } else {
      expect(headers()).toEqual(['Номер / название поставки', 'Селлер', 'Склад', 'Заказы / единицы', 'Короба', 'Статус', 'Печать'])
      const regular = document.querySelector('[data-testid="fbs-18-supply-supply-b"]') as HTMLTableRowElement
      expect(regular).toBeTruthy(); consistentCells(regular)
      if (label === 'В работе') {
        const task = document.querySelector('[data-testid="fbs-assembly-task-task-718"]') as HTMLTableRowElement
        expect(task).toBeTruthy(); expect(task.cells).toHaveLength(1); expect(task.cells[0].colSpan).toBe(7)
      }
      for (const current of Array.from(table().tBodies[0].rows)) {
        expect(Array.from(current.cells).reduce((sum, cell) => sum + cell.colSpan, 0)).toBe(7)
      }
    }
    assertStickyStructure()
    if (label === 'Отменённые' && Array.from(document.querySelectorAll('[role="tab"]')).some((node) => node.textContent === 'Просрочены')) {
      await tab('Просрочены')
      expect(headers()).toEqual(expect.arrayContaining(['Товар', 'Селлер', 'Маршрут сдачи', 'Отгрузить до', 'Статус']))
      consistentCells(row()); assertStickyStructure()
    }
    // No requirement to add an overdue tab when WMS-692 removes it.
  })

  it.each(['Новые', 'В работе', 'В доставке', 'Завершённые', 'Отменённые'])('R2-R4 retains a usable minimum and recalculates after page scroll in a short window on %s', async (label) => {
    const originalHeight = Object.getOwnPropertyDescriptor(window, 'innerHeight')!
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 600 })
    let top = 632
    const originalRect = HTMLElement.prototype.getBoundingClientRect
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      return this.classList.contains('MuiTableContainer-root')
        ? new DOMRect(0, top, 800, 128) : originalRect.call(this)
    })
    try {
      await open([order()]); if (label !== 'Новые') await tab(label)
      const area = container()
      const header = table().tHead
      expect(document.querySelector('[data-testid="fbs-selection-bar"]')).toBeNull()
      expect(getComputedStyle(area).maxHeight).toContain('656px')
      expect(Number.parseFloat(getComputedStyle(area).minHeight)).toBeGreaterThanOrEqual(128)
      assertStickyStructure()
      // Controlled input to the scroll listener; jsdom does not lay out or
      // scroll a page. Actual header visibility is still a browser check.
      top = 100
      await act(async () => window.dispatchEvent(new Event('scroll'))); await flush()
      expect(getComputedStyle(area).maxHeight).toContain('124px')
      expect(table().tHead).toBe(header)
      assertStickyStructure()
      await act(async () => area.dispatchEvent(new Event('scroll'))); await flush()
      expect(getComputedStyle(area).maxHeight).toContain('124px')
      expect(Number.parseFloat(getComputedStyle(area).minHeight)).toBeGreaterThanOrEqual(128)
      assertStickyStructure()
    } finally { Object.defineProperty(window, 'innerHeight', originalHeight) }
  })

  it('C6 ignores the old list response after switching context and preserves the new header on retry', async () => {
    let reads = 0
    let resolve!: (value: Response) => void
    const delayed = new Promise<Response>((next) => { resolve = next })
    dispose = await mount(installNetwork((url) => {
      if (url.pathname.endsWith('/fbs-orders/worklist')) {
        if (url.searchParams.get('status_group') === 'new') { reads += 1; return reads === 2 ? delayed : json(page([order('old-a')])) }
        return json(page([]))
      }
      if (url.pathname.endsWith('/fbs-supplies/worklist')) return json({ items: [supply()], server_now: SERVER_NOW })
      throw new Error(`Unexpected WMS-718 request: ${url}`)
    }), muiTheme)
    try {
      await refresh(); await tab('В работе')
      expect(document.body.textContent).toContain('Поставка нового контекста')
      resolve(json(page([order('late-a')]))); await flush()
      expect(document.body.textContent).toContain('Поставка нового контекста')
      expect(document.querySelector('[data-testid="fbs-order-late-a"]')).toBeNull()
      expect(headers()).not.toContain('Товар')
      assertStickyStructure(); await refresh(); assertStickyStructure()
      expect(document.body.textContent).not.toMatch(/Unexpected Application Error|служебная страница/)
    } finally { resolve(json(page([]))); await flush() }
  })
})
