// @vitest-environment jsdom
// WMS-756 R1/R2: фото строки заказа FBS — квадрат 72×72 px одного размера во всех строках и
// вкладках, фото видно целиком (object-fit: contain). jsdom не делает раскладку, поэтому
// проверяются применённые стили, которые задают поведение в браузере.
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cascadedValue, flush, installNetwork, json, mount, order, page, SERVER_NOW, tab } from './test-support/fbsOrdersDom'
import type { FbsWorklistOrder } from './fbsApi'

const WORKING = 'https://images.example/756-working.jpg'
type ImageProbe = { src: string; onload: ((event: Event) => void) | null; onerror: ((event: Event) => void) | null }
let dispose: (() => Promise<void>) | undefined
let probes: ImageProbe[]
let heights: Map<string, number>

beforeEach(() => {
  probes = []
  heights = new Map()
  vi.stubGlobal('Image', class {
    src = ''
    onload: ImageProbe['onload'] = null
    onerror: ImageProbe['onerror'] = null
    constructor() { probes.push(this) }
  })
  // Разная высота строк: до WMS-756 от неё зависела ширина фото.
  const original = HTMLElement.prototype.getBoundingClientRect
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const owner = this.closest('[data-testid^="fbs-order-"]')?.getAttribute('data-testid')
    const height = owner ? heights.get(owner.slice('fbs-order-'.length)) : undefined
    return height == null ? original.call(this) : new DOMRect(0, 0, 600, height)
  })
})
afterEach(async () => {
  await dispose?.()
  dispose = undefined
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function open(items: FbsWorklistOrder[]) {
  const network = installNetwork((url) => {
    if (url.pathname.endsWith('/fbs-orders/worklist')) return json(page(items))
    if (url.pathname.endsWith('/fbs-supplies/worklist')) return json({ items: [], total: 0, server_now: SERVER_NOW })
    throw new Error(`Unexpected WMS-756 request: ${url}`)
  })
  dispose = await mount(network)
}

function photo(id: string): HTMLElement {
  const node = document.querySelector(`[data-testid="fbs-product-photo-${id}"]`)
  expect(node, `photo of ${id} is rendered`).toBeTruthy()
  return node as HTMLElement
}

/** Рамка фото — первый ребёнок ячейки «Товар»; блок текста идёт сразу за ней. */
function productCell(id: string) {
  const cell = photo(id).closest('td') as HTMLTableCellElement
  const frame = cell.firstElementChild as HTMLElement
  const text = frame.nextElementSibling as HTMLElement
  expect(frame.contains(photo(id)), 'the photo sits in the first child of the cell').toBe(true)
  expect(text, 'the text block follows the photo frame').toBeTruthy()
  return { frame, text }
}

async function finishLoad(src: string) {
  await act(async () => probes.filter((probe) => probe.src === src).forEach((probe) => probe.onload?.(new Event('load'))))
  await flush()
}

function ozon(id: string) {
  const item = order(id)
  item.marketplace = 'ozon'
  item.positions = [
    { id: `${id}-1`, product_id: 'p1', name: 'Длинное название первой позиции '.repeat(5), seller_article: 'A', sku: '1', barcode: 'B1', size: 'Универсальный', quantity: 1, reserved_quantity: 1, picked_quantity: 0 },
    { id: `${id}-2`, product_id: 'p2', name: 'Вторая позиция', seller_article: 'B', sku: '2', barcode: 'B2', size: 'XS', quantity: 1, reserved_quantity: 1, picked_quantity: 0 },
  ]
  return item
}

describe('WMS-756 R1: фото строки заказа FBS — один квадрат 72×72 px', () => {
  it.each(['Новые', 'Отменённые'])('gives a short WB row, a tall WB row and a two-position Ozon row the same 72 px square on %s', async (label) => {
    const short = order('short')
    const tall = order('tall'); tall.product.name = 'Очень длинное название товара '.repeat(12)
    const oz = ozon('oz')
    heights.set('short', 80); heights.set('tall', 200); heights.set('oz', 160)
    await open([short, tall, oz])
    if (label !== 'Новые') await tab(label)
    for (const id of ['short', 'tall', 'oz']) {
      const { frame, text } = productCell(id)
      const css = getComputedStyle(frame)
      expect(css.width, `photo frame of ${id} width`).toBe('72px')
      expect(css.height, `photo frame of ${id} height`).toBe('72px')
      expect(css.position, `photo frame of ${id} is taken out of the text flow`).toBe('absolute')
      expect(css.top, `photo frame of ${id} is centred vertically in the row`).toBe('50%')
      expect(getComputedStyle(photo(id)).width, `photo of ${id} width`).toBe('72px')
      expect(getComputedStyle(photo(id)).height, `photo of ${id} height`).toBe('72px')
      expect(getComputedStyle(text).marginLeft, `text of ${id} keeps a constant gap after the photo`).toBe('84px')
      expect(getComputedStyle(text).minWidth, `text of ${id} keeps its minimum width`).toBe('300px')
    }
  })

  it.each(['Новые', 'Отменённые'])('shows the whole photo with object-fit contain on a light neutral background on %s', async (label) => {
    const item = order('pic'); item.product.image_url = WORKING
    await open([item])
    if (label !== 'Новые') await tab(label)
    await finishLoad(WORKING)
    const image = photo('pic').querySelector('img')
    expect(image, 'the loaded photo is rendered as an image').toBeTruthy()
    expect(cascadedValue(image!, 'object-fit'), 'the whole picture is visible, nothing is cropped').toBe('contain')
    expect(getComputedStyle(image!).backgroundColor, 'the empty area around a narrow picture is the theme light grey (grey 100)').toBe('rgb(245, 245, 245)')
  })
})
