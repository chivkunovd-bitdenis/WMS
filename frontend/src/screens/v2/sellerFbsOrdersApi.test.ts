import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  buildSellerFbsOrdersParams,
  loadSellerFbsOrdersPage,
  sellerFbsAgeLabel,
  sellerFbsItemsLabel,
  sellerFbsMarketplaceShort,
  sellerFbsReceivedAtLabel,
  sellerFbsStatusLabel,
  type SellerFbsOrderRow,
} from './sellerFbsOrdersApi'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function row(overrides: Partial<SellerFbsOrderRow> = {}): SellerFbsOrderRow {
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

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('buildSellerFbsOrdersParams — WMS-616 R6/R10', () => {
  it('always sends limit/offset so the server can paginate before applying anything client-side', () => {
    const params = buildSellerFbsOrdersParams({
      limit: 50,
      offset: 100,
      marketplace: 'all',
      status: 'all',
    })
    expect(params.get('limit')).toBe('50')
    expect(params.get('offset')).toBe('100')
  })

  it('omits marketplace for "all" so the baseline request stays minimal', () => {
    const params = buildSellerFbsOrdersParams({
      limit: 50,
      offset: 0,
      marketplace: 'all',
      status: 'all',
    })
    expect(params.has('marketplace')).toBe(false)
  })

  it('includes marketplace=ozon as the server sees it', () => {
    const params = buildSellerFbsOrdersParams({
      limit: 50,
      offset: 0,
      marketplace: 'ozon',
      status: 'all',
    })
    expect(params.get('marketplace')).toBe('ozon')
  })

  it('includes status=cancelled when the seller filters by cancelled', () => {
    const params = buildSellerFbsOrdersParams({
      limit: 50,
      offset: 0,
      marketplace: 'all',
      status: 'cancelled',
    })
    expect(params.get('status')).toBe('cancelled')
  })

  it('combines marketplace and status in a single request (R6)', () => {
    const params = buildSellerFbsOrdersParams({
      limit: 25,
      offset: 25,
      marketplace: 'wb',
      status: 'in_work',
    })
    expect(params.get('marketplace')).toBe('wb')
    expect(params.get('status')).toBe('in_work')
    expect(params.get('limit')).toBe('25')
    expect(params.get('offset')).toBe('25')
  })
})

describe('loadSellerFbsOrdersPage — WMS-488/R8 session safety', () => {
  it('returns the loaded page for the session that asked for it', async () => {
    const page = { items: [row()], total: 1, server_now: '2026-10-01T12:00:00.000Z' }
    const fetchImpl = vi.fn(async () => jsonResponse(200, page))

    const result = await loadSellerFbsOrdersPage(
      fetchImpl,
      { Authorization: 'Bearer t' },
      buildSellerFbsOrdersParams({ limit: 50, offset: 0, marketplace: 'all', status: 'all' }),
      () => true,
    )

    expect(result).toEqual({ outcome: 'loaded', page })
  })

  it('discards a page that arrives after the session switched to another seller', async () => {
    const page = { items: [row()], total: 1, server_now: '2026-10-01T12:00:00.000Z' }
    const fetchImpl = vi.fn(async () => jsonResponse(200, page))
    let session = 'seller-a'

    const pending = loadSellerFbsOrdersPage(
      fetchImpl,
      { Authorization: 'Bearer t' },
      buildSellerFbsOrdersParams({ limit: 50, offset: 0, marketplace: 'all', status: 'all' }),
      () => session === 'seller-a',
    )
    session = 'seller-b'

    expect(await pending).toEqual({ outcome: 'stale' })
  })

  it('reports a 500 of the current session as a failure with its message, not as empty success', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(500, { detail: 'boom' }))

    const result = await loadSellerFbsOrdersPage(
      fetchImpl,
      { Authorization: 'Bearer t' },
      buildSellerFbsOrdersParams({ limit: 50, offset: 0, marketplace: 'all', status: 'all' }),
      () => true,
    )

    expect(result).toEqual({ outcome: 'failed', message: 'boom' })
  })

  it('does not show the server error of a session that already switched away (R8 late-answer protection)', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(500, { detail: 'boom' }))
    let session: string | null = 'seller-a'

    const pending = loadSellerFbsOrdersPage(
      fetchImpl,
      { Authorization: 'Bearer t' },
      buildSellerFbsOrdersParams({ limit: 50, offset: 0, marketplace: 'all', status: 'all' }),
      () => session === 'seller-a',
    )
    session = null

    expect(await pending).toEqual({ outcome: 'stale' })
  })
})

describe('sellerFbsStatusLabel — WMS-616 D3', () => {
  it('maps each known group to its Russian stage label', () => {
    expect(sellerFbsStatusLabel('new')).toBe('Новый')
    expect(sellerFbsStatusLabel('in_work')).toBe('В работе')
    expect(sellerFbsStatusLabel('handed')).toBe('Передан площадке')
    expect(sellerFbsStatusLabel('accepted')).toBe('Принят площадкой')
    expect(sellerFbsStatusLabel('external_processing')).toBe('Обрабатывается площадкой')
    expect(sellerFbsStatusLabel('done')).toBe('Завершён')
    expect(sellerFbsStatusLabel('cancelled')).toBe('Отменён')
    expect(sellerFbsStatusLabel('defect')).toBe('Дефект')
  })
})

describe('sellerFbsItemsLabel — WMS-616 R4/D5', () => {
  it('shows "1 шт." for a WB order regardless of items_quantity (WB is always one unit per order)', () => {
    expect(sellerFbsItemsLabel(row({ marketplace: 'wb', items_quantity: null }))).toBe('1 шт.')
    expect(sellerFbsItemsLabel(row({ marketplace: 'wb', items_quantity: 5 }))).toBe('1 шт.')
  })

  it('shows the summed quantity for an Ozon order (3 of the same SKU → "3 шт.")', () => {
    expect(sellerFbsItemsLabel(row({ marketplace: 'ozon', items_quantity: 3 }))).toBe('3 шт.')
  })

  it('shows "—" for Ozon with a broken/null composition instead of inventing a unit (R4)', () => {
    expect(sellerFbsItemsLabel(row({ marketplace: 'ozon', items_quantity: null }))).toBe('—')
    expect(sellerFbsItemsLabel(row({ marketplace: 'ozon', items_quantity: 0 }))).toBe('—')
  })
})

describe('sellerFbsAgeLabel — WMS-616 R7', () => {
  it('shows "< 1 ч" for less than an hour', () => {
    expect(
      sellerFbsAgeLabel({
        receivedAtIso: '2026-10-01T12:00:00.000Z',
        serverNowIso: '2026-10-01T12:30:00.000Z',
      }),
    ).toBe('< 1 ч')
  })

  it('shows integer hours for anything one hour or longer', () => {
    expect(
      sellerFbsAgeLabel({
        receivedAtIso: '2026-10-01T09:15:00.000Z',
        serverNowIso: '2026-10-01T12:30:00.000Z',
      }),
    ).toBe('3 ч')
  })

  it('shows "—" for a future date (clock skew/bad data) instead of a negative or today-fake number', () => {
    expect(
      sellerFbsAgeLabel({
        receivedAtIso: '2026-10-02T12:00:00.000Z',
        serverNowIso: '2026-10-01T12:30:00.000Z',
      }),
    ).toBe('—')
  })

  it('shows "—" for an unparseable date without inventing an age', () => {
    expect(
      sellerFbsAgeLabel({ receivedAtIso: 'not-a-date', serverNowIso: '2026-10-01T12:30:00.000Z' }),
    ).toBe('—')
    expect(
      sellerFbsAgeLabel({ receivedAtIso: '2026-10-01T09:00:00.000Z', serverNowIso: 'nope' }),
    ).toBe('—')
  })
})

describe('sellerFbsReceivedAtLabel', () => {
  it('returns "—" for an unparseable date — never shows a fake today instead', () => {
    expect(sellerFbsReceivedAtLabel('nope')).toBe('—')
  })

  it('returns a stable Russian locale datetime string for a valid ISO (format detail is the browser, not us)', () => {
    const label = sellerFbsReceivedAtLabel('2026-10-01T09:15:00.000Z')
    expect(label).not.toBe('—')
    expect(label.length).toBeGreaterThan(0)
  })
})

describe('sellerFbsMarketplaceShort', () => {
  it('reads WB short for wb', () => {
    expect(sellerFbsMarketplaceShort('wb')).toBe('WB')
  })

  it('reads Ozon short for ozon', () => {
    expect(sellerFbsMarketplaceShort('ozon')).toBe('Ozon')
  })
})
