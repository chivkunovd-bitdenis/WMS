// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { FfBillingScreen } from './FfBillingScreen'

// WMS-706, R4 и R15: плашка «В работе» в ряду показателей «Расчётов» фулфилмента
// стоит сразу после «Отгружено FBS» и берёт значение totals.in_work_items. В кабинете
// селлера плашки нет. Экран монтируется настоящий, загрузка идёт через подменённый fetch.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const sellers = [{ id: 'seller-a', name: 'WMS706 Селлер А' }]

function summaryWith(extra: Record<string, number>) {
  return {
    rows: [],
    totals: {
      seller_count: 1,
      operation_count: 0,
      item_quantity: 0,
      not_billable_count: 0,
      inbound_items: 0,
      packing_items: 0,
      outbound_items: 0,
      fbs_items: 2,
      fbs_boxes: 0,
      return_items: 0,
      net_total_kopecks: 0,
      ...extra,
    },
  }
}

function response(data: unknown): Response {
  return { ok: true, json: async () => data } as Response
}

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/seller-report/summary')) return response(summaryWith({ in_work_items: 5 }))
      if (url.includes('/seller-billing/summary')) return response(summaryWith({}))
      if (url.includes('/storage-total')) return response({ liter_days: 0, amount_kopecks: 0, complete: true })
      if (url.includes('/details')) {
        return response({ seller_id: 'seller-a', seller_name: 'WMS706 Селлер А', entries: [], storage_row: null, next_cursor: null })
      }
      return response([])
    }),
  )
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

async function mountFulfillment() {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/app/ff/billing']}>
        <FfBillingScreen token="test" sellers={sellers} onOpenInbound={() => {}} />
      </MemoryRouter>,
    )
  })
  await flush()
}

async function mountCabinet() {
  await act(async () => {
    root.render(
      <MemoryRouter>
        <FfBillingScreen token="test" sellers={[]} onOpenInbound={() => {}} sellerScope />
      </MemoryRouter>,
    )
  })
  await flush()
}

function metricsText(): string {
  const strip = host.querySelector('[data-testid="billing-seller-metrics"]') as HTMLElement | null
  expect(strip, 'ряд показателей «Расчётов» должен быть на экране').not.toBeNull()
  return (strip as HTMLElement).textContent ?? ''
}

describe('WMS-706 · плашка «В работе» в сводке «Расчётов»', () => {
  it('C4: плашка «В работе» стоит после «Отгружено FBS» и показывает штуки заказов в работе', async () => {
    await mountFulfillment()
    const text = metricsText()
    const fbsAt = text.indexOf('Отгружено FBS')
    const workAt = text.indexOf('В работе')
    const boxesAt = text.indexOf('Коробов FBS')
    expect(workAt, `плашки «В работе» нет в ряду показателей: ${text}`).toBeGreaterThanOrEqual(0)
    expect(fbsAt, 'плашка «Отгружено FBS» должна остаться').toBeGreaterThanOrEqual(0)
    expect(workAt, '«В работе» должна стоять сразу после «Отгружено FBS», перед «Коробов FBS»').toBeGreaterThan(fbsAt)
    expect(workAt, '«В работе» должна стоять сразу после «Отгружено FBS», перед «Коробов FBS»').toBeLessThan(boxesAt)
    expect(text, 'значение плашки должно быть равно штукам заказов в работе').toMatch(/В работе\s*5/)
  })
})

describe('WMS-706 · кабинет селлера не меняется', () => {
  it('C19: в кабинете селлера плашки «В работе» нет', async () => {
    await mountCabinet()
    expect(metricsText(), 'в кабинете селлера плашки «В работе» быть не должно').not.toContain('В работе')
  })
})
