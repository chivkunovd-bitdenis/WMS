// @vitest-environment jsdom
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  click, flush, installNetwork, json, mount, order, page, refresh, select, SERVER_NOW, tab,
} from './test-support/fbsOrdersDom'

// Companion to the HTTP contract in test_wms716_fbs_counts.py. Only the
// external network boundary is controlled; screen and fbsApi remain real.
type Counts = { tabs: { new: number; active: number; delivery: number }; sellers: Record<string, number> }
const initial: Counts = { tabs: { new: 3, active: 6, delivery: 5 }, sellers: { 'seller-a': 1, 'seller-b': 2, 'seller-zero': 0 } }
let dispose: (() => Promise<void>) | undefined
afterEach(async () => { await dispose?.(); dispose = undefined; vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

function network(readCounts: (url: URL) => Response | Promise<Response>) {
  return installNetwork((url) => {
    if (url.pathname.endsWith('/fbs-orders/counts')) return readCounts(url)
    if (url.pathname.endsWith('/fbs-orders/worklist')) {
      const seller = url.searchParams.get('seller_id')
      const items = [order('one'), order('two'), order('three')].filter((item) => !seller || item.seller.id === seller)
      return json(page(items))
    }
    if (url.pathname.endsWith('/fbs-supplies/worklist')) return json({ items: [], total: 0, server_now: SERVER_NOW })
    throw new Error(`Unexpected request: ${url}`)
  })
}

function numericLabel(element: Element | null, value: number) {
  expect(element).toBeTruthy()
  const labels = Array.from(element!.querySelectorAll('*')).filter((node) => node.childElementCount === 0 && node.textContent?.trim() === String(value))
  expect(labels, `visible order count ${value} inside ${element?.textContent}`).toHaveLength(1)
}
function tabElement(label: string) {
  return Array.from(document.querySelectorAll('[role="tab"]')).find((node) => node.textContent?.includes(label)) ?? null
}
function badges(expected: Counts['tabs']) {
  numericLabel(tabElement('Новые'), expected.new)
  numericLabel(tabElement('В работе'), expected.active)
  numericLabel(tabElement('В доставке'), expected.delivery)
}
function deferred() {
  let resolve!: (value: Response) => void
  return { promise: new Promise<Response>((next) => { resolve = next }), resolve: (value: Response) => resolve(value) }
}

describe('WMS-716 real FBS counts and refresh lifecycle', () => {
  it('C1 displays counts on exactly three tabs, including successful zero and refresh', async () => {
    let current = structuredClone(initial)
    dispose = await mount(network(() => json(current)))
    for (const label of ['Новые', 'В работе', 'В доставке', 'Завершённые', 'Отменённые']) {
      await tab(label)
      badges(initial.tabs)
      for (const extra of ['Завершённые', 'Отменённые', 'Просрочены']) {
        const element = tabElement(extra)
        if (element) expect(element.textContent).toBe(extra)
      }
    }
    await refresh(); badges(initial.tabs)
    current = { tabs: { new: 0, active: 0, delivery: 0 }, sellers: { 'seller-a': 0, 'seller-b': 0, 'seller-zero': 0 } }
    await refresh(); badges(current.tabs)
  })

  it('C4 shows other sellers and selectable zero after selecting A and changing tabs', async () => {
    const countsByGroup: Record<string, Counts> = {
      new: initial,
      active: { ...initial, sellers: { 'seller-a': 2, 'seller-b': 4, 'seller-zero': 0 } },
      delivery: { ...initial, sellers: { 'seller-a': 3, 'seller-b': 2, 'seller-zero': 0 } },
    }
    dispose = await mount(network((url) => json(countsByGroup[url.searchParams.get('status_group') ?? 'new'] ?? initial)))
    await select('Селлер', 'Селлер А')
    for (const [label, expected] of [['Новые', 2], ['В работе', 4], ['В доставке', 2]] as const) {
      await tab(label)
      const control = document.querySelector('[aria-labelledby~="fbs-worklist-seller-label"][role="combobox"]')!
      await act(async () => control.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }))); await flush()
      const options = Array.from(document.querySelectorAll('[role="option"]'))
      numericLabel(options.find((node) => node.textContent?.startsWith('Селлер Б')) ?? null, expected)
      const zero = options.find((node) => node.textContent?.startsWith('Селлер без заказов'))!
      numericLabel(zero, 0)
      expect(zero.getAttribute('aria-disabled')).not.toBe('true')
      await click(options.find((node) => node.textContent?.startsWith('Селлер А')) ?? null)
    }
  })

  it('C4 keeps the warehouse reset when changing seller and reads counts after the reset', async () => {
    const reads: URL[] = []
    const fetch = network((url) => { reads.push(url); return json(initial) })
    dispose = await mount(fetch)
    await select('Склад селлера / маркетплейс', 'Склад 101')
    await select('Селлер', 'Селлер Б')
    const lastList = fetch.mock.calls.map(([input]) => new URL(String(input), 'http://localhost')).filter((url) => url.pathname.endsWith('/fbs-orders/worklist')).at(-1)!
    expect(lastList.searchParams.get('seller_id')).toBe('seller-b')
    expect(lastList.searchParams.has('wb_warehouse_id')).toBe(false)
    const lastCount = reads.at(-1)
    expect(lastCount, 'counts are re-read for the new seller').toBeTruthy()
    expect(lastCount!.searchParams.get('seller_id')).toBe('seller-b')
    expect(lastCount!.searchParams.has('wb_warehouse_id')).toBe(false)
    badges(initial.tabs)
  })

  it('C6 discards delayed A after B and hides old counts while the new context loads', async () => {
    const delayed = deferred(); const nextContext = deferred()
    let aReads = 0
    const forA: Counts = { tabs: { new: 1, active: 2, delivery: 3 }, sellers: initial.sellers }
    const forB: Counts = { tabs: { new: 7, active: 8, delivery: 9 }, sellers: initial.sellers }
    dispose = await mount(network((url) => {
      if (url.searchParams.get('seller_id') === 'seller-b') return nextContext.promise
      aReads += 1
      return aReads > 1 ? delayed.promise : json(forA)
    }))
    try {
      badges(forA.tabs)
      // Trigger an unfinished A refresh without awaiting its network response.
      await refresh()
      await select('Селлер', 'Селлер Б')
      expect(tabElement('Новые')!.textContent).not.toMatch(/\d/)
      nextContext.resolve(json(forB)); await flush(); badges(forB.tabs)
      delayed.resolve(json({ tabs: { new: 99, active: 99, delivery: 99 }, sellers: initial.sellers }))
      await flush(); badges(forB.tabs)
    } finally {
      delayed.resolve(json(forA)); nextContext.resolve(json(forB)); await flush()
    }
  })

  it('C6 distinguishes first failure from zero and restores counts after retry', async () => {
    let fail = true
    dispose = await mount(network(() => fail ? json({ detail: 'Counts read failed' }, 500) : json(initial)))
    expect(tabElement('Новые')!.textContent).not.toMatch(/\d/)
    expect(document.querySelector('[role="alert"]')).toBeTruthy()
    fail = false; await refresh(); badges(initial.tabs)
  })

  it('C6 retains successful counts only for the same context during failed refresh', async () => {
    let fail = false
    dispose = await mount(network(() => fail ? json({ detail: 'Counts read failed' }, 500) : json(initial)))
    badges(initial.tabs)
    fail = true; await refresh(); badges(initial.tabs)
    expect(document.querySelector('[role="alert"]')).toBeTruthy()
    await select('Селлер', 'Селлер Б')
    expect(tabElement('Новые')!.textContent).not.toMatch(/\d/)
    fail = false; await refresh(); badges(initial.tabs)
  })

  it('C7 refreshes changed counts manually, on the background tick and on visibility return', async () => {
    vi.useFakeTimers(); vi.setSystemTime(SERVER_NOW)
    const originalHidden = Object.getOwnPropertyDescriptor(document, 'hidden')
    let hidden = false
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden })
    let current = structuredClone(initial)
    const fetch = network(() => json(current))
    try {
      dispose = await mount(fetch); badges(initial.tabs)
      current = { ...initial, tabs: { new: 4, active: 7, delivery: 6 } }
      await refresh(); badges(current.tabs)
      current = { ...initial, tabs: { new: 5, active: 8, delivery: 7 } }
      await act(async () => { await vi.advanceTimersByTimeAsync(30_000) }); await flush(); badges(current.tabs)
      hidden = true
      await act(async () => document.dispatchEvent(new Event('visibilitychange')))
      current = { ...initial, tabs: { new: 6, active: 9, delivery: 8 } }
      hidden = false
      await act(async () => document.dispatchEvent(new Event('visibilitychange'))); await flush(); badges(current.tabs)
      expect(fetch.mock.calls.every(([, init]) => (init?.method ?? 'GET') === 'GET')).toBe(true)
    } finally {
      if (originalHidden) Object.defineProperty(document, 'hidden', originalHidden)
      else delete (document as unknown as Record<string, unknown>).hidden
    }
  })
})
