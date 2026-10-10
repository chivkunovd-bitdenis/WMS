// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { cascadedValue, flush, headers, installNetwork, json, mount, order, page, refresh, row, select, SERVER_NOW, tab } from './test-support/fbsOrdersDom'
import type { FbsWorklistOrder } from './fbsApi'

const FIRST = 'https://images.example/720-first.jpg'
const SECOND = 'https://images.example/720-second.jpg'
const PRODUCT = 'https://images.example/720-product.jpg'
const WORKING = 'https://images.example/720-working.jpg'
type ImageProbe = { src: string; onload: ((event: Event) => void) | null; onerror: ((event: Event) => void) | null }
type Visibility = { node: Element; emit: (visible: boolean) => void }
let dispose: (() => Promise<void>) | undefined
let probes: ImageProbe[]
let visibility: Visibility[]
let resize: Array<() => void>
let heights: Map<string, number>

beforeEach(() => {
  probes = []; visibility = []; resize = []; heights = new Map()
  vi.stubGlobal('Image', class {
    src = ''; onload: ImageProbe['onload'] = null; onerror: ImageProbe['onerror'] = null
    get naturalWidth() { return this.src.includes('portrait') ? 60 : this.src.includes('landscape') ? 120 : 100 }
    get naturalHeight() { return this.src.includes('portrait') ? 120 : this.src.includes('landscape') ? 60 : 100 }
    constructor() { probes.push(this) }
  })
  vi.stubGlobal('IntersectionObserver', class {
    private callback: IntersectionObserverCallback
    private active = true
    constructor(callback: IntersectionObserverCallback) { this.callback = callback }
    observe(node: Element) {
      visibility.push({ node, emit: (visible) => {
        if (this.active) this.callback([{ target: node, isIntersecting: visible } as IntersectionObserverEntry], this as unknown as IntersectionObserver)
      } })
    }
    unobserve() {} disconnect() { this.active = false } takeRecords() { return [] }
  })
  vi.stubGlobal('ResizeObserver', class {
    private callback: ResizeObserverCallback
    private active = true
    constructor(callback: ResizeObserverCallback) { this.callback = callback }
    observe(node: Element) {
      resize.push(() => {
        if (!this.active) return
        const rect = node.getBoundingClientRect()
        this.callback([{ target: node, contentRect: rect, borderBoxSize: [{ blockSize: rect.height, inlineSize: rect.width }], contentBoxSize: [{ blockSize: rect.height, inlineSize: rect.width }] } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver)
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

async function open(items: FbsWorklistOrder[], read?: (url: URL) => Response | Promise<Response>) {
  const network = installNetwork((url) => {
    if (read) return read(url)
    if (url.pathname.endsWith('/fbs-orders/worklist')) return json(page(items))
    if (url.pathname.endsWith('/fbs-supplies/worklist')) return json({ items: [], server_now: SERVER_NOW })
    throw new Error(`Unexpected WMS-720 request: ${url}`)
  })
  dispose = await mount(network)
  return network
}
function photo(id = 'order-a'): HTMLElement {
  const node = document.querySelector(`[data-testid="fbs-product-photo-${id}"]`)
  expect(node).toBeTruthy(); return node as HTMLElement
}
async function enter(id = 'order-a', visible = true) {
  await act(async () => visibility.filter(({ node }) => node.closest(`[data-testid="fbs-order-${id}"]`)).forEach(({ emit }) => emit(visible)))
  await flush()
}
async function finish(src: string, success = true, candidates = probes.filter((probe) => probe.src === src)) {
  await act(async () => candidates.forEach((probe) => (success ? probe.onload : probe.onerror)?.(new Event(success ? 'load' : 'error'))))
  await flush()
}
async function resized() { await act(async () => resize.forEach((callback) => callback())); await flush() }
function sizing(id = 'order-a') {
  const nodes = []; let current: HTMLElement | null = photo(id)
  while (current && current.tagName !== 'TR') { nodes.push(current); current = current.parentElement }
  return nodes.map((node) => {
    const css = getComputedStyle(node)
    return { width: css.width, height: css.height, minHeight: css.minHeight, maxHeight: css.maxHeight, aspectRatio: css.aspectRatio, position: css.position, top: css.top, bottom: css.bottom }
  })
}
// WMS-756 R1 (заменяет WMS-720 R1): квадрат фото фиксирован 84×84 px и не тянется по высоте строки.
function fixedSquare(id: string) {
  const rules = sizing(id)
  expect(rules.some((rule) => rule.width === '84px' && rule.height === '84px'), 'rendered CSS keeps a fixed 84 px square').toBe(true)
}

function ozon() {
  const item = order(); item.marketplace = 'ozon'; item.product.image_url = PRODUCT
  item.positions = [
    { id: 'first', product_id: 'first', name: 'Первый длинный товар '.repeat(8), seller_article: 'A', sku: '1', image_url: FIRST, size: 'S', quantity: 3, reserved_quantity: 3, picked_quantity: 0 },
    { id: 'second', product_id: 'second', name: 'Вторая позиция', seller_article: 'B', sku: '2', image_url: SECOND, size: 'XL', quantity: 1, reserved_quantity: 1, picked_quantity: 0 },
  ]
  return item
}

describe('WMS-720 photo sizing rules, loading and neighboring calls without browser layout', () => {
  it.each(['Новые', 'Отменённые'])('R1/R3 keeps the same 84 px square for absent, failed and working images on %s', async (label) => {
    const item = order(); heights.set(item.id, 80)
    await open([item]); if (label !== 'Новые') await tab(label)
    await resized(); await enter()
    const assertFilledSquare = () => {
      const avatar = photo()
      const wrapper = avatar.parentElement!   // обёртка с tabindex: 100% от слоя фото
      const slot = wrapper.parentElement!     // слой фото (LazyProductPhotoThumb): 84 px
      const frame = slot.parentElement!       // рамка в ячейке «Товар»: 84 px, по центру строки
      expect(getComputedStyle(wrapper).width).toBe('100%')
      expect(getComputedStyle(wrapper).height).toBe('100%')
      expect(getComputedStyle(slot).width).toBe('84px')
      expect(getComputedStyle(slot).height).toBe('84px')
      expect(getComputedStyle(slot).flexShrink).toBe('0')
      expect(getComputedStyle(avatar).width).toBe('84px')
      expect(getComputedStyle(avatar).height).toBe('84px')
      expect(getComputedStyle(frame).width).toBe('84px')
      expect(getComputedStyle(frame).height).toBe('84px')
      fixedSquare(item.id)
    }
    expect(photo().querySelector('img')).toBeNull(); assertFilledSquare()
    const before = sizing()
    item.product.image_url = FIRST; await refresh(); await finish(FIRST, false)
    expect(photo().querySelector('img')).toBeNull(); assertFilledSquare()
    item.product.image_url = WORKING; await refresh(); await finish(WORKING)
    expect(photo().querySelector('img')?.getAttribute('src')).toBe(WORKING)
    expect(cascadedValue(photo().querySelector('img')!, 'object-fit')).toBe('contain')
    assertFilledSquare(); expect(sizing()).toEqual(before)
  })

  it.each(['Новые', 'Отменённые'])('C1 keeps the 84 px square for short and tall rows, whatever their measured height, on %s', async (label) => {
    const short = order('short'); const long = order('long'); long.product.name = 'Длинное название '.repeat(15)
    heights.set('short', 80); heights.set('long', 160)
    await open([short, long]); if (label !== 'Новые') await tab(label)
    await resized(); fixedSquare('short'); fixedSquare('long')
    const before = sizing('long'); await resized(); expect(sizing('long')).toEqual(before)
    heights.set('long', 200); await resized(); fixedSquare('long')
  })

  it.each([['Новые', true], ['Новые', false], ['Отменённые', true], ['Отменённые', false]] as const)('C2 preserves one Ozon photo and all positions on %s with first photo present=%s', async (label, present) => {
    const item = ozon(); if (!present) item.positions[0].image_url = null
    await open([item]); if (label !== 'Новые') await tab(label)
    await enter(); await finish(present ? FIRST : PRODUCT)
    expect(document.querySelectorAll('[data-testid="fbs-order-order-a"]')).toHaveLength(1)
    expect(row().querySelectorAll('[data-testid^="fbs-product-photo-"]')).toHaveLength(1)
    expect(photo().querySelector('img')?.getAttribute('src')).toBe(present ? FIRST : PRODUCT)
    expect(row().textContent).toContain(item.positions[0].name)
    expect(row().textContent).toContain('Вторая позиция')
    expect(row().querySelectorAll('img')).toHaveLength(1)
    await refresh(); await finish(present ? FIRST : PRODUCT)
    expect(photo().querySelector('img')?.getAttribute('src')).toBe(present ? FIRST : PRODUCT)
  })

  it('C2 keeps one 84 px square for a multi-position Ozon row, not sized by the first position', async () => {
    heights.set('order-a', 180); await open([ozon()]); await resized(); fixedSquare('order-a')
  })

  it.each(['square', 'portrait', 'landscape'])('C3 keeps contain scaling and stable sizing rules for a %s source on refresh', async (shape) => {
    const item = order(); item.product.image_url = `https://images.example/720-${shape}.jpg`
    await open([item]); await enter(); await finish(item.product.image_url)
    const image = photo().querySelector('img')!
    expect(image).toBeTruthy(); expect(cascadedValue(image, 'object-fit')).toBe('contain')
    const before = sizing(); await refresh(); await finish(item.product.image_url)
    expect(sizing()).toEqual(before)
    expect(photo().querySelector('img')?.getAttribute('src')).toBe(item.product.image_url)
  })

  it('C3 gives every image source the same fixed 84 px square', async () => {
    const items = ['square', 'portrait', 'landscape'].map((shape) => {
      const item = order(shape); item.product.image_url = `https://images.example/720-${shape}.jpg`
      heights.set(shape, 120); return item
    })
    await open(items); await resized()
    items.forEach((item) => fixedSquare(item.id))
  })

  it.each([undefined, null, ''])('C4 restores a missing photo source %s without replacing the area or hiding actions', async (source) => {
    const item = order(); item.product.image_url = source as string | null
    await open([item]); await enter()
    expect(probes.filter((probe) => probe.src)).toHaveLength(0)
    expect(photo().querySelector('img')).toBeNull(); expect(photo().querySelector('svg')).toBeTruthy()
    const before = sizing()
    expect(row().textContent).toContain('Товар WB'); expect(row().querySelector('input[type="checkbox"]')).toBeTruthy()
    item.product.image_url = WORKING; await refresh(); await finish(WORKING)
    expect(photo().querySelector('img')?.getAttribute('src')).toBe(WORKING)
    expect(sizing()).toEqual(before)
    expect(document.querySelector('[role="alert"]')).toBeNull()
  })

  it('C4 recovers from a failed image probe with the same sizing area after a source refresh', async () => {
    const item = order(); item.product.image_url = FIRST
    await open([item]); await enter(); const before = sizing(); await finish(FIRST, false)
    expect(photo().querySelector('img')).toBeNull(); expect(photo().querySelector('svg')).toBeTruthy()
    expect(sizing()).toEqual(before); expect(row().textContent).toContain('Товар WB')
    expect((row().querySelector('input') as HTMLInputElement).disabled).toBe(false)
    item.product.image_url = WORKING; await refresh(); await finish(WORKING)
    expect(photo().querySelector('img')?.getAttribute('src')).toBe(WORKING)
    expect(sizing()).toEqual(before)
  })

  it('C5 keeps B after late A loading and gates new sources with viewport entry on reopening', async () => {
    const a = order('a'); a.product.image_url = FIRST
    const b = order('b'); b.product.image_url = SECOND; b.seller = { id: 'seller-b', name: 'Селлер Б' }
    const read = (url: URL) => {
      if (url.pathname.endsWith('/fbs-orders/worklist')) return json(page(url.searchParams.get('seller_id') === 'seller-b' ? [b] : [a]))
      throw new Error(`Unexpected WMS-720 request: ${url}`)
    }
    await open([a], read)
    await enter('a', false)
    expect(probes.filter((probe) => probe.src)).toHaveLength(0)
    await enter('a'); const old = probes.filter((probe) => probe.src === FIRST)
    expect(old.length).toBeGreaterThan(0)
    await select('Селлер', 'Селлер Б')
    await enter('b', false)
    expect(probes.filter((probe) => probe.src === SECOND)).toHaveLength(0)
    await enter('b'); await finish(SECOND); const before = sizing('b')
    await finish(FIRST, true, old)
    expect(photo('b').querySelector('img')?.getAttribute('src')).toBe(SECOND)
    expect(sizing('b')).toEqual(before)
    await dispose?.(); dispose = undefined; probes = []; visibility = []
    await open([b]); expect(probes.filter((probe) => probe.src)).toHaveLength(0)
    await enter('b'); await finish(SECOND)
    expect(photo('b').querySelector('img')?.getAttribute('src')).toBe(SECOND)
    expect(sizing('b')).toEqual(before)
  })

  it('C5 ignores a stale image failure after the source changes on the same order', async () => {
    const item = order(); item.product.image_url = FIRST
    await open([item]); await enter(); const old = probes.filter((probe) => probe.src === FIRST)
    item.product.image_url = SECOND; await refresh(); await finish(SECOND)
    expect(photo().querySelector('img')?.getAttribute('src')).toBe(SECOND)
    const before = sizing(); await finish(FIRST, false, old)
    expect(photo().querySelector('img')?.getAttribute('src')).toBe(SECOND)
    expect(sizing()).toEqual(before)
  })

  it('C7 preserves the ordinary shared photo defaults and hover/focus preview events outside FBS', async () => {
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    const host = document.createElement('div'); document.body.append(host); const root = createRoot(host)
    dispose = async () => { await act(async () => root.unmount()); host.remove() }
    // Same src-only call used in SellerCatalogSelectionDialog; no FBS row sizing.
    await act(async () => root.render(<ProductPhotoThumb src={WORKING} />)); await finish(WORKING)
    const avatar = host.querySelector('.MuiAvatar-root')!; const css = getComputedStyle(avatar)
    expect(css.width).toBe('44px'); expect(css.height).toBe('44px')
    const anchor = avatar.closest('[tabindex]')!
    await act(async () => anchor.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))); await flush()
    let preview = document.querySelector('[data-testid="product-photo-enlarged"]')!
    expect(preview).toBeTruthy(); expect(getComputedStyle(preview).width).toBe('240px')
    expect(getComputedStyle(preview).height).toBe('240px'); expect(getComputedStyle(preview).pointerEvents).toBe('none')
    await act(async () => anchor.dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: document.body }))); await flush()
    expect(document.querySelector('[data-testid="product-photo-enlarged"]')).toBeNull()
    await act(async () => anchor.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))); await flush()
    preview = document.querySelector('[data-testid="product-photo-enlarged"]')!
    expect(preview).toBeTruthy()
    await act(async () => anchor.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))); await flush()
    expect(document.querySelector('[data-testid="product-photo-enlarged"]')).toBeNull()
  })

  it('C7 keeps the supply table and sends only reads during photo preview and refresh', async () => {
    const item = order(); item.product.image_url = WORKING; const before = structuredClone(item)
    const network = await open([item]); await enter(); await finish(WORKING)
    const anchor = photo().closest('[tabindex]')!
    await act(async () => anchor.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))); await flush()
    const preview = document.querySelector('[data-testid="product-photo-enlarged"]')!
    expect(preview).toBeTruthy(); expect(getComputedStyle(preview).width).toBe('280px')
    await act(async () => anchor.dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: document.body })))
    await refresh()
    for (const label of ['В работе', 'В доставке', 'Завершённые']) {
      await tab(label)
      expect(headers()).toEqual(['Номер / название поставки', 'Селлер', 'Склад', 'Заказы / единицы', 'Короба', 'Статус', 'Печать'])
    }
    expect(network.mock.calls.every(([, init]) => (init?.method ?? 'GET') === 'GET')).toBe(true)
    expect(item).toEqual(before)
    // Do not introduce a required overdue tab: WMS-692 owns its removal.
  })
})
