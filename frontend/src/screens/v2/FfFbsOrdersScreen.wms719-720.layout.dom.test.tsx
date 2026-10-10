// @vitest-environment jsdom
// WMS-719 R3 (размер читается целым словом) и WMS-720 R1/R3 (фото не раздувает строку и таблицу).
// jsdom не делает раскладку, поэтому проверяются применённые стили, которые задают поведение
// в браузере; фактическая геометрия снята в настоящем браузере (fix-report-lead-2.md).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flush, headers, installNetwork, json, mount, order, page, refresh, row, SERVER_NOW, tab } from './test-support/fbsOrdersDom'
import type { FbsWorklistOrder } from './fbsApi'
import { act } from 'react'

const WORKING = 'https://images.example/719-720-working.jpg'
const MIN_TEXT = 300
type ImageProbe = { src: string; onload: ((event: Event) => void) | null; onerror: ((event: Event) => void) | null }
let dispose: (() => Promise<void>) | undefined
let probes: ImageProbe[]
let resize: Array<() => void>
let heights: Map<string, number>

beforeEach(() => {
  probes = []; resize = []; heights = new Map()
  vi.stubGlobal('Image', class {
    src = ''; onload: ImageProbe['onload'] = null; onerror: ImageProbe['onerror'] = null
    constructor() { probes.push(this) }
  })
  vi.stubGlobal('ResizeObserver', class {
    private callback: ResizeObserverCallback
    private active = true
    constructor(callback: ResizeObserverCallback) { this.callback = callback }
    observe(node: Element) {
      resize.push(() => {
        if (!this.active) return
        const rect = node.getBoundingClientRect()
        this.callback([{ target: node, contentRect: rect } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver)
      })
    }
    unobserve() {} disconnect() { this.active = false }
  })
  const original = HTMLElement.prototype.getBoundingClientRect
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const owner = this.closest('[data-testid^="fbs-order-"]')?.getAttribute('data-testid')
    const height = owner ? heights.get(owner.slice('fbs-order-'.length)) : undefined
    return height == null ? original.call(this) : new DOMRect(0, 0, 600, height)
  })
})
afterEach(async () => { await dispose?.(); dispose = undefined; vi.unstubAllGlobals(); vi.restoreAllMocks() })

async function open(items: FbsWorklistOrder[]) {
  const network = installNetwork((url) => {
    if (url.pathname.endsWith('/fbs-orders/worklist')) return json(page(items))
    if (url.pathname.endsWith('/fbs-supplies/worklist')) return json({ items: [], total: 0, server_now: SERVER_NOW })
    throw new Error(`Unexpected request: ${url}`)
  })
  dispose = await mount(network)
}
async function resized() { await act(async () => resize.forEach((callback) => callback())); await flush() }
function photo(id = 'order-a'): HTMLElement {
  const node = document.querySelector(`[data-testid="fbs-product-photo-${id}"]`)
  expect(node).toBeTruthy(); return node as HTMLElement
}
/** Рамка фото в ячейке «Товар» и соседний с ней блок текста. */
function productCell(id = 'order-a') {
  const cell = photo(id).closest('td') as HTMLTableCellElement
  const frame = cell.firstElementChild as HTMLElement
  const text = frame.nextElementSibling as HTMLElement
  expect(frame.contains(photo(id)), 'the first child of the cell is the photo frame').toBe(true)
  expect(text, 'the text block follows the photo frame').toBeTruthy()
  return { cell, frame, text }
}
function sizeCell(id = 'order-a') { return row(id).cells[headers().indexOf('Размер')] }
function ozon(id = 'order-a') {
  const item = order(id); item.marketplace = 'ozon'
  item.positions = [
    { id: 'p1', product_id: 'p1', name: 'Длинный товар первой позиции '.repeat(6), seller_article: 'A', sku: '1', barcode: 'B1', image_url: WORKING, size: 'Универсальный', quantity: 1, reserved_quantity: 1, picked_quantity: 0 },
    { id: 'p2', product_id: 'p2', name: 'Вторая', seller_article: 'B', sku: '2', barcode: 'B2', size: '200x220 см', quantity: 1, reserved_quantity: 1, picked_quantity: 0 },
    { id: 'p3', product_id: 'p3', name: 'Третья', seller_article: 'C', sku: '3', barcode: 'B3', size: 'XS', quantity: 1, reserved_quantity: 1, picked_quantity: 0 },
  ]
  return item
}

describe('WMS-719 R3: размер читается целым словом', () => {
  it.each(['Новые', 'Отменённые'])('C6 does not allow a break inside a word of a size on %s', async (label) => {
    const wb = order('wb'); wb.product.size = 'Универсальный'
    await open([wb, ozon('oz')]); if (label !== 'Новые') await tab(label)
    const values = [...sizeCell('wb').children, ...sizeCell('oz').children]
    expect(values.map((node) => node.textContent)).toEqual(['Универсальный', 'Универсальный', '200x220 см', 'XS'])
    for (const value of values) {
      const css = getComputedStyle(value)
      // anywhere / break-all дают точки разрыва внутри слова и сжимают колонку до «Универ/сальны/й».
      expect(css.overflowWrap, 'overflow-wrap must not offer break points inside a word').not.toBe('anywhere')
      expect(css.wordBreak).not.toBe('break-all')
      expect(css.wordBreak).not.toBe('break-word')
      // пробельные размеры по-прежнему переносятся по словам внутри своей ячейки
      expect(css.whiteSpace).not.toBe('nowrap')
    }
  })

  it.each(['Новые', 'Отменённые'])('C6 keeps the size column bounded so short sizes do not inflate the table on %s', async (label) => {
    await open([order()]); if (label !== 'Новые') await tab(label)
    const css = getComputedStyle(sizeCell())
    expect(css.minWidth).toBe('80px')
    expect(css.maxWidth).toBe('170px')
    expect(css.width === '' || css.width === 'auto', 'no fixed width for the size column').toBe(true)
  })
})

describe('WMS-720 R1/R3: фото не сужает название и не задаёт высоту строки', () => {
  it.each(['Новые', 'Отменённые'])('C1 guarantees the title block a minimum width that does not shrink with the photo on %s', async (label) => {
    const short = order('short'); const tall = order('tall'); tall.product.name = 'Очень длинное название '.repeat(14)
    heights.set('short', 70); heights.set('tall', 400)
    await open([short, tall]); if (label !== 'Новые') await tab(label)
    await resized()
    for (const id of ['short', 'tall']) {
      const { frame, text } = productCell(id)
      const css = getComputedStyle(text)
      // место под фото отведено внешним отступом, а не внутренним: иначе минимальная ширина
      // «съедается» фото и при высокой строке название превращается в узкую полосу.
      expect(css.minWidth, `title block of ${id} keeps its minimum width`).toBe(`${MIN_TEXT}px`)
      expect(['', '0px'], 'photo space must not be taken from the title block').toContain(css.paddingLeft)
      // WMS-756 R1 (заменяет WMS-720 R1): рамка фото фиксирована 84 px и не зависит от высоты строки;
      // текст отступает от фото на постоянные 84 + 12 px
      expect(getComputedStyle(frame).width, `photo frame of ${id} is 84 px wide`).toBe('84px')
      expect(css.marginLeft, `title block of ${id} keeps a constant gap after the photo`).toBe('96px')
    }
  })

  it.each(['Новые', 'Отменённые'])('C1 title block of every Ozon position keeps the same minimum width on %s', async (label) => {
    heights.set('order-a', 320)
    await open([ozon()]); if (label !== 'Новые') await tab(label)
    await resized()
    const { text } = productCell()
    expect(getComputedStyle(text).minWidth).toBe(`${MIN_TEXT}px`)
    for (const name of ['Длинный товар первой позиции', 'Вторая', 'Третья']) expect(text.textContent).toContain(name)
  })

  it.each(['Новые', 'Отменённые'])('C1 keeps the photo out of the row height calculation on %s', async (label) => {
    heights.set('order-a', 200)
    await open([order()]); if (label !== 'Новые') await tab(label)
    await resized()
    const { cell, frame, text } = productCell()
    const css = getComputedStyle(frame)
    expect(getComputedStyle(cell).position).toBe('relative')
    expect(css.position, 'photo frame is taken out of the flow').toBe('absolute')
    // WMS-756 R1: рамка центрируется по вертикали строки, а строка не ниже фото (84 px)
    expect(css.top, 'photo frame is centred vertically in the row').toBe('50%')
    expect(getComputedStyle(text).minHeight, 'the row is never shorter than the photo').toBe('84px')
  })

  it.each(['Новые', 'Отменённые'])('C8 image loading does not change the photo frame, the title offset or the row on %s', async (label) => {
    const item = order(); item.product.image_url = WORKING; heights.set(item.id, 198)
    await open([item]); if (label !== 'Новые') await tab(label)
    await resized()
    const snapshot = () => {
      const { frame, text } = productCell()
      const f = getComputedStyle(frame); const t = getComputedStyle(text)
      return [f.width, f.height, f.position, t.marginLeft, t.minWidth, t.paddingLeft, getComputedStyle(photo()).width, getComputedStyle(photo()).height]
    }
    const before = snapshot()
    await act(async () => probes.filter((probe) => probe.src === WORKING).forEach((probe) => probe.onload?.(new Event('load'))))
    await flush(); await refresh(); await act(async () => probes.filter((probe) => probe.src === WORKING).forEach((probe) => probe.onload?.(new Event('load'))))
    await flush()
    expect(snapshot()).toEqual(before)
  })
})
