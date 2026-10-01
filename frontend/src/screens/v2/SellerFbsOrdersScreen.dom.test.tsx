// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { SellerFbsOrdersScreen } from './SellerFbsOrdersScreen'

// WMS-616 DOM-проверки: что экран действительно шлёт выбранные фильтры в
// backend и честно показывает подписанные группы в таблице. Чистые хелперы
// проверяются в sellerFbsOrdersApi.test.ts; здесь — только то, что без
// рендера проверить нельзя.

vi.setConfig({ testTimeout: 30000 })

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

let root: Root | null = null
let host: HTMLDivElement | null = null
async function mount(element: React.ReactElement) {
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => {
    root!.render(element)
  })
}

afterEach(async () => {
  if (root) {
    await act(async () => {
      root!.unmount()
    })
  }
  root = null
  host?.remove()
  host = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

const flush = () => act(async () => { await Promise.resolve() })

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function orderPayload(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'order-1',
    marketplace: 'wb',
    external_order_id: 'WB-123',
    status_group: 'new',
    items_quantity: null,
    received_at: '2026-10-01T09:00:00.000Z',
    ...overrides,
  }
}

describe('SellerFbsOrdersScreen — WMS-616 end-to-end wiring', () => {
  it('loads the first page on mount without a marketplace or status filter in the URL (R1 default)', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, { items: [orderPayload()], total: 1, server_now: '2026-10-01T12:00:00.000Z' }),
    )
    vi.stubGlobal('fetch', fetchImpl)

    await mount(<SellerFbsOrdersScreen token="t" authHeaders={() => ({})} />)
    await flush()
    await flush()

    expect(fetchImpl).toHaveBeenCalled()
    const calls = fetchImpl.mock.calls as unknown as Array<[RequestInfo | URL, unknown]>
    expect(calls.length).toBeGreaterThan(0)
    const url = String(calls[0]![0])
    expect(url).toContain('/seller-fbs/orders')
    expect(url).toContain('limit=50')
    expect(url).toContain('offset=0')
    expect(url).not.toContain('marketplace=')
    expect(url).not.toContain('status=')
  })

  it('renders the mapped status label and WB "1 шт." quantity for a WB order', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(200, {
          items: [
            orderPayload({ marketplace: 'wb', items_quantity: null, status_group: 'in_work' }),
          ],
          total: 1,
          server_now: '2026-10-01T12:00:00.000Z',
        }),
      ),
    )

    await mount(<SellerFbsOrdersScreen token="t" authHeaders={() => ({})} />)
    await flush()
    await flush()

    const text = host!.textContent ?? ''
    expect(text).toContain('В работе')
    expect(text).toContain('1 шт.')
  })

  it('renders the Ozon summed quantity "3 шт." for an Ozon order with items_quantity=3', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(200, {
          items: [orderPayload({ marketplace: 'ozon', items_quantity: 3 })],
          total: 1,
          server_now: '2026-10-01T12:00:00.000Z',
        }),
      ),
    )

    await mount(<SellerFbsOrdersScreen token="t" authHeaders={() => ({})} />)
    await flush()
    await flush()

    expect(host!.textContent ?? '').toContain('3 шт.')
  })

  it('shows a retry alert instead of a fake empty success when the backend returns 500', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, { detail: 'boom' })))

    await mount(<SellerFbsOrdersScreen token="t" authHeaders={() => ({})} />)
    await flush()
    await flush()

    const alert = host!.querySelector('[data-testid="seller-fbs-error"]')
    expect(alert).not.toBeNull()
    const retry = host!.querySelector('[data-testid="seller-fbs-retry"]')
    expect(retry).not.toBeNull()
  })

  // Astra P2 (ревью после 6605df5b): forceAgeTick в прошлой версии вызывал
  // перерисовку, но useMemo resolvedNowIso не зависел от счётчика — возраст
  // замирал на старом значении. Регрессия: при реальном «прошло больше часа»
  // возраст должен обновиться от «< 1 ч» до «1 ч» без перезагрузки страницы.
  it('updates the age cell after the tick fires, instead of freezing at the first render', async () => {
    // Фиксируем клиентские часы фиктивным таймером и performance.now, чтобы
    // elapsed рос по нашему расписанию. perfRef — монотонный счётчик,
    // который возвращает performance.now() при обоих вызовах (на монтировании
    // и в useMemo).
    vi.useFakeTimers()
    let perfNowMs = 0
    const perfSpy = vi.spyOn(performance, 'now').mockImplementation(() => perfNowMs)
    try {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () =>
          jsonResponse(200, {
            items: [
              {
                id: 'order-1',
                marketplace: 'wb',
                external_order_id: 'WB-1',
                status_group: 'new',
                items_quantity: null,
                received_at: '2026-10-01T12:00:00.000Z',
              },
            ],
            total: 1,
            server_now: '2026-10-01T12:00:30.000Z',
          }),
        ),
      )

      await mount(<SellerFbsOrdersScreen token="t" authHeaders={() => ({})} />)
      // Прокручиваем микро/макро-задачи, чтобы fetch завершился и effect
      // поставил perfAnchor.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      // На этом моменте возраст < 1 ч: сервер показывает 12:00:30, заказ
      // пришёл в 12:00:00 — прошло 30 секунд.
      let ageCell = host!.querySelector('[data-testid="seller-fbs-order-age-order-1"]')
      expect(ageCell?.textContent).toBe('< 1 ч')

      // Монотонное время продвинулось на 65 минут. Один tick AGE_TICK_MS
      // (60_000 ms) должен сдвинуть счётчик ageTick → useMemo пересчитается
      // с новым performance.now() → возраст станет «1 ч».
      perfNowMs = 65 * 60_000
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000)
      })
      ageCell = host!.querySelector('[data-testid="seller-fbs-order-age-order-1"]')
      expect(ageCell?.textContent).toBe('1 ч')
    } finally {
      perfSpy.mockRestore()
      vi.useRealTimers()
    }
  })
})
