// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { Link, MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { SellerCardScreen } from './SellerCardScreen'
import { FfBillingInvoicesPanel } from '../ff/FfBillingInvoicesPanel'

/**
 * WMS-491 — регрессионные проверки на независимое перекрёстное ревью Astra
 * (docs/reviews/artifacts/wms-491/review-astra-1.md, дефекты F1/F3/F4/F5).
 * Настоящий рендер (createRoot, эффекты, MemoryRouter), сеть подменена только
 * через fetch — как в исполняемых воспроизведениях ревьюера
 * (/private/tmp/wms491-astra-review/review.test.tsx), но на исправленном коде.
 */

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

const sellers = [
  { id: 'seller-a', name: 'Seller A' },
  { id: 'seller-b', name: 'Seller B' },
]
const authHeaders = () => ({ Authorization: 'Bearer test' })
const profile = (label: string) => ({ legal_name: `Legal ${label}`, inn: '7700000000' })

function response(data: unknown, ok = true): Response {
  return { ok, status: ok ? 200 : 500, json: async () => data } as Response
}

let host: HTMLDivElement
let root: Root
let navigateRef: ReturnType<typeof useNavigate>
let requests: Array<{ url: string; method: string }>

function NavProbe() {
  navigateRef = useNavigate()
  const loc = useLocation()
  return (
    <>
      <Link data-testid="go-list" to="/app/ff/sellers">
        Селлеры
      </Link>
      <span data-testid="location">
        {loc.pathname}
        {loc.search}
      </span>
    </>
  )
}

async function flush() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 10))
  })
}

// MUI Dialog рендерит содержимое порталом в document.body, а не внутрь host —
// искать нужно по всему документу, иначе кнопки открытого окна не найти.
async function click(testId: string) {
  await act(async () => {
    ;(document.querySelector(`[data-testid="${testId}"]`) as HTMLElement).click()
  })
  await flush()
}

async function mount(node: React.ReactNode, entry: string) {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[entry]}>
        <NavProbe />
        {node}
      </MemoryRouter>,
    )
  })
  await flush()
}

const cardRoutes = (list = sellers) => (
  <Routes>
    <Route path="/app/ff/sellers" element={<div>Список</div>} />
    <Route
      path="/app/ff/sellers/:sellerId"
      element={<SellerCardScreen token="test" authHeaders={authHeaders} sellers={list} />}
    />
  </Routes>
)

beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  requests = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown, init: RequestInit = {}) => {
      const url = String(input)
      requests.push({ url, method: init.method ?? 'GET' })
      if (url.includes('/billing/profiles/sellers/')) return response(profile(url.split('/').pop()!))
      if (url.includes('/invoices-v2?')) return response({ invoices: [], next_cursor: null })
      if (url.endsWith('/sellers')) return response(sellers)
      return response([])
    }),
  )
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

describe('SellerCardScreen keeps the requisites dialog bound to the displayed seller (F1)', () => {
  it('sends PUT to the seller shown after jumping back through browser history, not the seller visited last', async () => {
    await mount(cardRoutes(), '/app/ff/sellers/seller-a')
    await act(async () => navigateRef('/app/ff/sellers'))
    await flush()
    await act(async () => navigateRef('/app/ff/sellers/seller-b'))
    await flush()
    // "Назад" дважды — сразу на A, минуя список, как в отчёте ревью.
    await act(async () => navigateRef(-2))
    await flush()
    expect(host.querySelector('[data-testid="seller-card-requisites"]')?.textContent).toContain('Legal seller-a')

    requests = []
    await click('billing-profiles-open')
    await click('billing-profiles-save')
    expect(requests.filter((r) => r.method === 'PUT').map((r) => r.url)).toEqual([
      '/api/billing/profiles/sellers/seller-a',
    ])
  })
})

describe('SellerCardScreen ignores a stale profile response from a different seller (F4, cross-seller)', () => {
  it('a late seller-a response cannot overwrite the already-loaded seller-b profile', async () => {
    const original = globalThis.fetch
    let release!: (r: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
        String(input).endsWith('/profiles/sellers/seller-a')
          ? new Promise<Response>((r) => {
              release = r
            })
          : original(input, init),
      ),
    )
    await mount(cardRoutes(), '/app/ff/sellers/seller-a')
    await act(async () => navigateRef('/app/ff/sellers/seller-b'))
    await flush()
    expect(host.querySelector('[data-testid="seller-card-requisites"]')?.textContent).toContain('Legal seller-b')
    await act(async () => release(response(profile('seller-a'))))
    await flush()
    expect(host.querySelector('[data-testid="seller-card-requisites"]')?.textContent).toContain('Legal seller-b')
  })
})

describe('SellerCardScreen ignores a stale profile response for the same seller (F4, same seller)', () => {
  it('a late pre-save response cannot overwrite the successful post-save reload', async () => {
    const original = globalThis.fetch
    let release!: (r: Response) => void
    let calls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init: RequestInit = {}) => {
        if (!String(input).includes('/profiles/sellers/')) return original(input, init)
        if (init.method === 'PUT') return Promise.resolve(response(profile('NEW')))
        calls += 1
        if (calls === 1) {
          return new Promise<Response>((r) => {
            release = r
          })
        }
        return Promise.resolve(response(profile('NEW')))
      }),
    )
    await mount(cardRoutes(), '/app/ff/sellers/seller-a')
    await click('billing-profiles-open')
    await click('billing-profiles-save')
    expect(host.querySelector('[data-testid="seller-card-requisites"]')?.textContent).toContain('Legal NEW')
    await act(async () => release(response(profile('OLD'))))
    await flush()
    expect(host.querySelector('[data-testid="seller-card-requisites"]')?.textContent).toContain('Legal NEW')
  })
})

describe('SellerCardScreen tells a read failure apart from genuinely empty requisites (F5)', () => {
  it('shows a load-error notice instead of claiming the profile is unfilled', async () => {
    const original = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
        String(input).includes('/profiles/sellers/')
          ? Promise.resolve(response(null, false))
          : original(input, init),
      ),
    )
    await mount(cardRoutes(), '/app/ff/sellers/seller-a')
    expect(host.querySelector('[data-testid="seller-card-requisites-empty"]')).toBeNull()
    expect(host.querySelector('[data-testid="seller-card-requisites-error"]')?.textContent).toContain(
      'Не удалось загрузить реквизиты',
    )
  })
})

describe('FfBillingInvoicesPanel resets its state when the fixed seller changes (F3)', () => {
  it('never mixes rows, cursor or the loaded-more page across sellers', async () => {
    const original = globalThis.fetch
    const invoice = (id: string, seller: string) => ({
      id,
      number: id,
      origin: 'v2',
      seller_id: seller,
      seller_name: seller,
      issued_at: '2026-09-27T10:00:00Z',
      period_start: null,
      period_end: null,
      creation_mode: 'manual',
      status: 'issued',
      total_amount_kopecks: 100,
    })
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (!url.includes('/invoices-v2?')) return original(input, init)
        const params = new URL(url, 'http://localhost').searchParams
        const who = params.get('seller_id')!
        const hasCursor = params.has('cursor')
        return Promise.resolve(
          response({
            invoices: [invoice(who === 'seller-a' ? (hasCursor ? 'A-INVOICE-2' : 'A-INVOICE-1') : 'B-INVOICE-1', who)],
            next_cursor: who === 'seller-a' && !hasCursor ? 'CURSOR-A' : null,
          }),
        )
      }),
    )
    await act(async () => {
      root.render(<FfBillingInvoicesPanel token="test" fixedSellerId="seller-a" />)
    })
    await flush()
    await act(async () => {
      ;(Array.from(host.querySelectorAll('button')).find((b) => b.textContent?.includes('Загрузить ещё')) as HTMLElement).click()
    })
    await flush()
    expect(host.textContent).toContain('A-INVOICE-2')

    await act(async () => {
      root.render(<FfBillingInvoicesPanel token="test" fixedSellerId="seller-b" />)
    })
    await flush()
    expect(host.textContent).toContain('B-INVOICE-1')
    expect(host.textContent).not.toContain('A-INVOICE-1')
    expect(host.textContent).not.toContain('A-INVOICE-2')
    expect(host.querySelector('[data-testid="billing-invoice-open-B-INVOICE-1"]')).not.toBeNull()
  })
})
