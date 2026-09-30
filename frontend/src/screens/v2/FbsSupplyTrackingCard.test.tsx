// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FbsSupplyTrackingCard } from './FbsSupplyTrackingCard'
import type { FbsWorkspace } from './fbsApi'

const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` })
const workspace = {
  supply: {
    id: 'supply-a', marketplace: 'wb', wb_supply_id: 'WB-GI-A', name: 'Поставка А',
    status: 'in_delivery', seller: { id: 'seller', name: 'Селлер' },
  },
  stage: 'tracking',
  orders: [
    { id: 'order-a', wb_order_id: 111, product: { name: 'Куртка' } },
    { id: 'order-b', wb_order_id: 222, product: { name: 'Рубашка' } },
  ],
  tracking_summary: {
    status: 'in_progress', last_wb_sync_at: null, checked_at: '',
    orders: [
      { order_id: 'order-a', wb_order_id: 111, tracking_label: 'in_progress', wb_status: 'waiting', supplier_status: 'complete', local_status: 'in_delivery' },
      { order_id: 'order-b', wb_order_id: 222, tracking_label: 'in_progress', wb_status: 'waiting', supplier_status: 'complete', local_status: 'in_delivery' },
    ],
  },
} as FbsWorkspace

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('WB supply tracking card', () => {
  it('polls only the open supply, preserves rows on failure, and stops on close', async () => {
    let calls = 0
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      paths.push(url)
      if (url.endsWith('/tracking-status')) {
        calls += 1
        if (calls === 2) return new Response('unavailable', { status: 502 })
        return new Response(JSON.stringify({
          supply_status: 'in_delivery', wb_closed_at: '2026-09-30T09:00:00Z', wb_scan_at: null,
          tracking_summary: {
            ...workspace.tracking_summary,
            orders: [
              { ...workspace.tracking_summary!.orders[0], wb_status: 'sorted' },
              workspace.tracking_summary!.orders[1],
            ],
          },
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/history')) return new Response(JSON.stringify({
        supply_id: 'supply-a', supply_number: 'WB-GI-A', status: 'in_delivery',
        order_count: 2, events: [{
          at: '2026-09-30T08:00:00Z', kind: 'packed', title: 'Упакованы заказы',
          actor: null, details: '2 заказа',
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      throw new Error(`unexpected request ${url}`)
    }))
    let poll: (() => void) | null = null
    const originalSetInterval = window.setInterval.bind(window)
    vi.spyOn(window, 'setInterval').mockImplementation(((handler: TimerHandler, timeout?: number) => {
      if (timeout === 90_000 && typeof handler === 'function') {
        poll = handler as () => void
        return 991
      }
      return originalSetInterval(handler, timeout)
    }) as typeof window.setInterval)
    const clear = vi.spyOn(window, 'clearInterval')

    await act(async () => {
      root.render(<FbsSupplyTrackingCard token="test" authHeaders={authHeaders} workspace={workspace} open onClose={() => undefined} />)
    })
    expect(paths).toEqual([expect.stringContaining('/supply-a/tracking-status')])
    expect(document.body.textContent).toContain('Отсортирован WB')
    expect(document.body.textContent).toContain('Рубашка')
    expect(document.body.textContent).toContain('Передана в доставку WB')

    await act(async () => {
      document.querySelector<HTMLButtonElement>('[data-testid="fbs-tracking-history-toggle"]')?.click()
    })
    expect(paths).toEqual([
      expect.stringContaining('/supply-a/tracking-status'),
      expect.stringContaining('/supply-a/history'),
    ])
    expect(document.body.textContent).toContain('Упакованы заказы')

    await act(async () => { poll?.() })
    expect(paths).toHaveLength(3)
    expect(document.body.textContent).toContain('Отсортирован WB')
    expect(document.body.textContent).toContain('Рубашка')
    expect(document.body.textContent).toContain('Не удалось обновить статусы WB')

    await act(async () => {
      root.render(<FbsSupplyTrackingCard token="test" authHeaders={authHeaders} workspace={workspace} open={false} onClose={() => undefined} />)
    })
    expect(clear).toHaveBeenCalledWith(991)
    await act(async () => { poll?.() })
    expect(paths).toHaveLength(3)
  })

  it('two open clients issue only addressed status requests', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      paths.push(String(input))
      return new Response(JSON.stringify({
        supply_status: 'in_delivery', wb_closed_at: null, wb_scan_at: null,
        tracking_summary: workspace.tracking_summary,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const secondHost = document.createElement('div')
    document.body.append(secondHost)
    const secondRoot = createRoot(secondHost)
    try {
      await act(async () => {
        root.render(<FbsSupplyTrackingCard token="test" authHeaders={authHeaders} workspace={workspace} open onClose={() => undefined} />)
        secondRoot.render(<FbsSupplyTrackingCard token="test" authHeaders={authHeaders} workspace={workspace} open onClose={() => undefined} />)
      })
      expect(paths).toHaveLength(2)
      expect(paths.every((path) => path.endsWith('/supply-a/tracking-status'))).toBe(true)
    } finally {
      await act(async () => secondRoot.unmount())
      secondHost.remove()
    }
  })
})
