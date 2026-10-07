import { afterEach, describe, expect, it, vi } from 'vitest'
import { SameOriginSellerWithdrawalApi } from './sellerKizWithdrawalApi'

afterEach(() => vi.unstubAllGlobals())

describe('WMS-517 incident: optional registry dates (IC1, IC2)', () => {
  it.each([
    ['', '2026-10-07'],
    ['2026-10-01', ''],
    ['', ''],
    ['2026-10-01', '2026-10-07'],
  ])('omits empty date boundaries and preserves filled dates and query: %s / %s', async (dateFrom, dateTo) => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ rows: [], total: 0 }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    const api = new SameOriginSellerWithdrawalApi('test-seller-session')
    for (let repeat = 0; repeat < 2; repeat += 1) {
      await api.list({ dateFrom, dateTo, search: 'товар', productId: 'product-id', onlyNotWithdrawn: false, limit: 100, offset: 100 })
      const [raw, init] = fetchMock.mock.calls[repeat] as unknown as [string, RequestInit]
      const url = new URL(raw, 'https://wms.test')
      expect(url.pathname).toBe('/api/operations/marking-codes/self/withdrawals')
      expect(url.searchParams.has('date_from')).toBe(Boolean(dateFrom))
      expect(url.searchParams.has('date_to')).toBe(Boolean(dateTo))
      if (dateFrom) expect(url.searchParams.get('date_from')).toBe(dateFrom)
      if (dateTo) expect(url.searchParams.get('date_to')).toBe(dateTo)
      expect(url.searchParams.get('search')).toBe('товар')
      expect(url.searchParams.get('product_id')).toBe('product-id')
      expect(url.searchParams.get('only_not_withdrawn')).toBe('false')
      expect(url.searchParams.get('limit')).toBe('100')
      expect(url.searchParams.get('offset')).toBe('100')
      expect(new Headers(init.headers).get('Authorization')).toBe('Bearer test-seller-session')
      expect(init.method ?? 'GET').toBe('GET')
    }
  })
})
