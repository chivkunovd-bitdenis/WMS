// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FfBillingScreen } from './FfBillingScreen'

// WMS-491, правка F2 (перекрёстное ревью Astra №1, docs/reviews/artifacts/wms-491/review-astra-1.md).
// Переход из карточки селлера (?seller_id=<id>, кнопка «Выставить счёт»)
// выставлял фильтр «Селлер» в «Расчётах», но повторный клик по пункту меню
// «Расчёты» на уже смонтированном экране его не сбрасывал — react-router не
// размонтирует компонент при переходе на тот же маршрут. Нарушение R9/C9.
// Тест монтирует настоящий компонент (createRoot, реальные эффекты, реальный
// клик по ссылке меню), не статический рендер.

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const sellers = [
  { id: 'seller-a', name: 'WMS-491 Селлер А' },
  { id: 'seller-b', name: 'WMS-491 Селлер Б' },
]

let host: HTMLDivElement
let root: Root

function Nav() {
  return <Link data-testid="menu-billing" to="/app/ff/billing">Расчёты</Link>
}

function response(data: unknown): Response {
  return { ok: true, json: async () => data } as Response
}

async function flush() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/seller-report/summary')) {
        return response({ rows: [], totals: { seller_count: 0, operation_count: 0, item_quantity: 0, not_billable_count: 0 } })
      }
      if (url.includes('/storage-total')) return response({ liter_days: 0 })
      return response([])
    }),
  )
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

async function mount(entry: string) {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[entry]}>
        <Nav />
        <Routes>
          <Route
            path="/app/ff/billing"
            element={<FfBillingScreen token="test" sellers={sellers} onOpenInbound={() => {}} />}
          />
        </Routes>
      </MemoryRouter>,
    )
  })
  await flush()
}

function sellerFilterValue(): string {
  return (document.querySelector('select[data-testid="billing-seller"]') as HTMLSelectElement | null)?.value ?? ''
}

async function clickMenuBilling() {
  await act(async () => {
    (host.querySelector('[data-testid="menu-billing"]') as HTMLElement).click()
  })
  await flush()
}

describe('FfBillingScreen — filter applied from ?seller_id= survives only until a fresh menu entry', () => {
  it('menu click after entry via seller card link resets the filter to «Все селлеры»', async () => {
    await mount('/app/ff/billing?seller_id=seller-a')
    expect(sellerFilterValue()).toBe('seller-a')

    await clickMenuBilling()
    expect(sellerFilterValue()).toBe('all')
  })

  it('menu click does not revert a filter the operator picked manually', async () => {
    await mount('/app/ff/billing')
    expect(sellerFilterValue()).toBe('all')

    const select = document.querySelector('select[data-testid="billing-seller"]') as HTMLSelectElement
    await act(async () => {
      select.value = 'seller-b'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()
    expect(sellerFilterValue()).toBe('seller-b')

    await clickMenuBilling()
    expect(sellerFilterValue()).toBe('seller-b')
  })
})
