// @vitest-environment jsdom
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flush, installNetwork, json, mount, order, page, refresh, row, SERVER_NOW, tab } from './test-support/fbsOrdersDom'
import type { FbsWorklistOrder } from './fbsApi'

// WMS-720 R3: фото, которое не загрузилось, при следующем обновлении списка проверяется
// снова по тому же адресу и показывается без перезагрузки строки и без смены размеров.
const FIRST = 'https://images.example/720-retry.jpg'
type ImageProbe = { src: string; onload: ((event: Event) => void) | null; onerror: ((event: Event) => void) | null }
type Visibility = { node: Element; emit: (visible: boolean) => void }
let dispose: (() => Promise<void>) | undefined
let probes: ImageProbe[]
let visibility: Visibility[]
let heights: Map<string, number>

beforeEach(() => {
  probes = []; visibility = []; heights = new Map()
  vi.stubGlobal('Image', class {
    src = ''; onload: ImageProbe['onload'] = null; onerror: ImageProbe['onerror'] = null
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
    observe() {} unobserve() {} disconnect() {}
  })
  const original = HTMLElement.prototype.getBoundingClientRect
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const owner = this.closest('[data-testid^="fbs-order-"]')?.getAttribute('data-testid')
    const height = owner ? heights.get(owner.slice('fbs-order-'.length)) : undefined
    return height == null ? original.call(this) : new DOMRect(0, 0, 600, height)
  })
})
afterEach(async () => {
  await dispose?.(); dispose = undefined
  vi.useRealTimers(); delete (document as { hidden?: boolean }).hidden
  vi.unstubAllGlobals(); vi.restoreAllMocks()
})

async function open(items: FbsWorklistOrder[]) {
  const network = installNetwork((url) => {
    if (url.pathname.endsWith('/fbs-orders/worklist')) return json(page(items))
    if (url.pathname.endsWith('/fbs-supplies/worklist')) return json({ items: [], server_now: SERVER_NOW })
    throw new Error(`Unexpected WMS-720 retry request: ${url}`)
  })
  dispose = await mount(network)
  return network
}
function photo(id = 'order-a'): HTMLElement {
  const node = document.querySelector(`[data-testid="fbs-product-photo-${id}"]`)
  expect(node).toBeTruthy(); return node as HTMLElement
}
async function enter(id = 'order-a') {
  await act(async () => visibility.filter(({ node }) => node.closest(`[data-testid="fbs-order-${id}"]`)).forEach(({ emit }) => emit(true)))
  await flush()
}
// Вызывает onload/onerror у всех попыток загрузки с этим адресом, как это делает браузер.
async function finish(src: string, success: boolean, candidates = attempts(src)) {
  await act(async () => candidates.forEach((probe) => (success ? probe.onload : probe.onerror)?.(new Event(success ? 'load' : 'error'))))
  await flush()
}
function attempts(src = FIRST): ImageProbe[] {
  return probes.filter((probe) => probe.src === src)
}
// Размеры области фото: сама миниатюра, её рамка и внешний контейнер строки.
function frame(id = 'order-a') {
  const avatar = photo(id)
  const anchor = avatar.parentElement!
  const slot = anchor.parentElement!
  return [avatar, anchor, slot].map((node) => {
    const css = getComputedStyle(node)
    return { width: css.width, height: css.height }
  })
}

describe('WMS-720 R3 retry of a failed photo after a list refresh', () => {
  it.each(['Новые', 'Отменённые'])('R3 shows the working photo after a same-address refresh on %s without remounting the row or its area', async (label) => {
    const item = order(); item.product.image_url = FIRST; heights.set(item.id, 80)
    await open([item]); if (label !== 'Новые') await tab(label)
    await enter(); await finish(FIRST, false)
    expect(photo().querySelector('img')).toBeNull(); expect(photo().querySelector('svg')).toBeTruthy()
    const stub = frame(); const avatar = photo(); const rowBefore = row()
    const before = attempts().length
    await refresh()
    const retry = attempts().slice(before)
    expect(retry.length, 'the failed address is requested again after the list refresh').toBeGreaterThan(0)
    await finish(FIRST, true, retry)
    expect(photo()).toBe(avatar); expect(row()).toBe(rowBefore)
    expect(photo().querySelector('img')?.getAttribute('src')).toBe(FIRST)
    expect(frame()).toEqual(stub)
  })

  it('R3 asks for a still-broken address once per list refresh and never on its own', async () => {
    const item = order(); item.product.image_url = FIRST
    await open([item]); await enter(); await finish(FIRST, false)
    const start = attempts().length
    await refresh()
    expect(attempts().length - start, 'one new attempt per list refresh').toBe(1)
    await finish(FIRST, false, attempts().slice(start))
    await flush(); await flush()
    expect(attempts().length, 'idle renders do not request the broken address').toBe(start + 1)
    await refresh()
    expect(attempts().length - start).toBe(2)
    expect(photo().querySelector('img')).toBeNull()
  })

  it('R3 applies the same retry on the 30 second background list refresh', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    const item = order(); item.product.image_url = FIRST; heights.set(item.id, 80)
    const network = await open([item]); await enter(); await finish(FIRST, false)
    const stub = frame(); const avatar = photo()
    const callsBefore = network.mock.calls.length; const before = attempts().length
    await act(async () => { vi.advanceTimersByTime(30000) }); await flush()
    expect(network.mock.calls.length, 'the background timer reloads the list').toBeGreaterThan(callsBefore)
    const retry = attempts().slice(before)
    expect(retry.length, 'the failed address is requested again on the background refresh').toBeGreaterThan(0)
    await finish(FIRST, true, retry)
    expect(photo()).toBe(avatar)
    expect(photo().querySelector('img')?.getAttribute('src')).toBe(FIRST)
    expect(frame()).toEqual(stub)
  })
})
