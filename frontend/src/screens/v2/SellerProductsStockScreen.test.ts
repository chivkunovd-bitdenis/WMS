import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  loadSellerCatalogPage,
  syncSellerCatalogMarketplaces,
  type SellerCatalogItem,
} from './SellerProductsStockScreen'

function productItem(id: string, name: string): SellerCatalogItem {
  return {
    key: `product:${id}`,
    on_fulfillment: true,
    marketplace: 'wildberries',
    id,
    sku_code: id,
    name,
    wb_vendor_code: null,
    wb_nm_id: null,
    ozon_sku: null,
    ozon_offer_id: null,
    wb_subject_name: null,
    wb_primary_image_url: null,
    wb_barcodes: [],
    wb_primary_barcode: null,
    wb_size: null,
    packaging_instructions: null,
    requires_honest_sign: false,
    has_packaging_instructions: false,
  }
}

function cardItem(nmId: number, name: string): SellerCatalogItem {
  return {
    key: `wb:${nmId}`,
    on_fulfillment: false,
    marketplace: 'wildberries',
    nm_id: nmId,
    vendor_code: `art-${nmId}`,
    name,
    photo_url: null,
    barcodes: [],
    sizes: [],
    category: null,
  }
}

function pageResponse(items: SellerCatalogItem[]) {
  return { items, total: items.length, scope_total: items.length, categories: [] }
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function pageParams(): URLSearchParams {
  return new URLSearchParams({ limit: '10', offset: '0', on_fulfillment: 'all' })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

// WMS-488: страница каталога грузится по токену вкладки. Пока ответ шёл,
// сессию могли сменить — тогда пришедшие строки описывают прежнего селлера.
describe('seller catalog page response', () => {
  it('shows the rows of the session that asked for them', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, pageResponse([productItem('p-1', 'Палантин')]))),
    )

    const result = await loadSellerCatalogPage(
      { Authorization: 'Bearer token-goryachkina' },
      pageParams(),
      () => true,
    )

    expect(result).toEqual({ outcome: 'loaded', page: pageResponse([productItem('p-1', 'Палантин')]) })
  })

  it('discards rows that arrive after the tab switched to another seller', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, pageResponse([productItem('p-1', 'Палантин')]))),
    )
    let sessionToken = 'token-goryachkina'

    const pending = loadSellerCatalogPage(
      { Authorization: 'Bearer token-goryachkina' },
      pageParams(),
      () => sessionToken === 'token-goryachkina',
    )
    sessionToken = 'token-chulkov'

    expect(await pending).toEqual({ outcome: 'stale' })
  })

  it('stays silent about a late failure of a session that already logged out', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(403, { detail: 'forbidden' })),
    )
    let sessionToken: string | null = 'token-goryachkina'

    const pending = loadSellerCatalogPage(
      { Authorization: 'Bearer token-goryachkina' },
      pageParams(),
      () => sessionToken === 'token-goryachkina',
    )
    sessionToken = null

    expect(await pending).toEqual({ outcome: 'stale' })
  })

  it('reports a server error of the current session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(500, { detail: 'boom' })),
    )

    const result = await loadSellerCatalogPage({ Authorization: 'Bearer token-goryachkina' }, pageParams(), () => true)

    expect(result).toEqual({ outcome: 'failed', message: 'boom' })
  })

  it('carries both a product on fulfillment and a card that is not yet on it', async () => {
    const items = [productItem('p-1', 'Палантин на ФФ'), cardItem(555, 'Карточка без ФФ')]
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, pageResponse(items))))

    const result = await loadSellerCatalogPage({ Authorization: 'Bearer t' }, pageParams(), () => true)

    expect(result).toEqual({ outcome: 'loaded', page: pageResponse(items) })
  })

  // WMS-614 R3: экран обязан дотащить marketplace в тот же запрос страницы,
  // который делает сервер; без неё сервер отдаст все площадки и экран покажет
  // чужой срез.
  it('forwards the marketplace query param to /seller-catalog/page exactly as the caller composed it', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, pageResponse([])))
    vi.stubGlobal('fetch', fetchImpl)

    const params = pageParams()
    params.set('marketplace', 'ozon')
    await loadSellerCatalogPage({ Authorization: 'Bearer t' }, params, () => true)

    const calls = fetchImpl.mock.calls as unknown as Array<[RequestInfo | URL, unknown]>
    expect(calls.length).toBeGreaterThan(0)
    const url = String(calls[0]![0])
    expect(url).toContain('marketplace=ozon')
  })
})

// WMS-615 QA 2 (01.10): «Синхронизировать по API» обязана уважать то, какая
// площадка на самом деле подключена. У Ozon-only селлера WB-ручка возвращала
// 409 `missing_content_token`, экран показывал этот код поверх успешного Ozon.
// Теперь обе площадки предваряются одинаковой проверкой подключения, при
// отсутствии ключа — пропускаем молча (не ошибка), при отказе самой проверки —
// честно показываем ошибку этой площадки, не блокируя соседнюю.
describe('syncSellerCatalogMarketplaces', () => {
  function urlOf(input: RequestInfo | URL): string {
    return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  }

  function fetchMock(
    handlers: Partial<{
      wbTokens: () => Response | Promise<Response>
      wbSync: () => Response | Promise<Response>
      ozonAccount: () => Response | Promise<Response>
      ozonSync: () => Response | Promise<Response>
    }>,
  ) {
    return vi.fn(async (input: RequestInfo | URL) => {
      const url = urlOf(input)
      if (url.includes('/integrations/wildberries/self/tokens')) {
        return (handlers.wbTokens ?? (() => jsonResponse(200, { has_content_token: false })))()
      }
      if (url.includes('/integrations/wildberries/self/sync-products')) {
        if (!handlers.wbSync) throw new Error(`unexpected WB sync request: ${url}`)
        return handlers.wbSync()
      }
      if (url.includes('/integrations/ozon/self/account')) {
        return (handlers.ozonAccount ?? (() => jsonResponse(200, { connected: false })))()
      }
      if (url.includes('/integrations/ozon/self/sync-products')) {
        if (!handlers.ozonSync) throw new Error(`unexpected Ozon sync request: ${url}`)
        return handlers.ozonSync()
      }
      throw new Error(`unexpected request: ${url}`)
    })
  }

  it('does not call WB sync-products on an Ozon-only seller (no WB key) and does not fake a WB failure', async () => {
    const fetchImpl = fetchMock({
      wbTokens: () => jsonResponse(200, { has_content_token: false }),
      ozonAccount: () => jsonResponse(200, { connected: true }),
      ozonSync: () => jsonResponse(202, { id: 'job-ozon', marketplace: 'ozon', state: 'queued' }),
    })
    vi.stubGlobal('fetch', fetchImpl)

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: null, ozonFailure: null })
    const calledUrls = fetchImpl.mock.calls.map((c) => urlOf(c[0] as RequestInfo | URL))
    expect(calledUrls.some((u) => u.includes('/integrations/wildberries/self/sync-products'))).toBe(false)
  })

  it('calls WB sync-products when the token endpoint confirms the key is present', async () => {
    const fetchImpl = fetchMock({
      wbTokens: () => jsonResponse(200, { has_content_token: true }),
      wbSync: () => jsonResponse(202, { id: 'job-wb', marketplace: 'wildberries', state: 'queued' }),
      ozonAccount: () => jsonResponse(200, { connected: true }),
      ozonSync: () => jsonResponse(202, { id: 'job-ozon', marketplace: 'ozon', state: 'queued' }),
    })
    vi.stubGlobal('fetch', fetchImpl)

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: null, ozonFailure: null })
    const calledUrls = fetchImpl.mock.calls.map((c) => urlOf(c[0] as RequestInfo | URL))
    expect(calledUrls.some((u) => u.includes('/integrations/wildberries/self/sync-products'))).toBe(true)
    expect(calledUrls.some((u) => u.includes('/integrations/ozon/self/sync-products'))).toBe(true)
  })

  it('reports a WB sync failure with a human message instead of a raw server code', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbTokens: () => jsonResponse(200, { has_content_token: true }),
        wbSync: () => jsonResponse(422, { detail: 'invalid_wb_token' }),
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome.wbFailure).toBe('Ключ WB не подходит — проверка не прошла.')
    expect(outcome.ozonFailure).toBeNull()
  })

  it('falls back to a generic WB phrase for unrecognised machine-looking codes, not the raw code', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbTokens: () => jsonResponse(200, { has_content_token: true }),
        wbSync: () => jsonResponse(502, { detail: 'upstream_error' }),
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome.wbFailure).toBe('Не удалось синхронизировать Wildberries.')
  })

  it('reports a network failure of the WB sync call itself instead of swallowing it', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbTokens: () => jsonResponse(200, { has_content_token: true }),
        wbSync: () => {
          throw new TypeError('Failed to fetch')
        },
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome.wbFailure).toBe('Failed to fetch')
    expect(outcome.ozonFailure).toBeNull()
  })

  it('shows a clear WB check error when GET /integrations/wildberries/self/tokens fails, without blocking Ozon', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbTokens: () => jsonResponse(500, { detail: 'boom' }),
        ozonAccount: () => jsonResponse(200, { connected: true }),
        ozonSync: () => jsonResponse(202, { id: 'job-ozon', marketplace: 'ozon', state: 'queued' }),
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome.wbFailure).toBe('Не удалось проверить подключение Wildberries.')
    expect(outcome.ozonFailure).toBeNull()
  })

  it('reports a network failure of the Ozon sync call itself instead of swallowing it', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        ozonAccount: () => jsonResponse(200, { connected: true }),
        ozonSync: () => {
          throw new TypeError('Failed to fetch')
        },
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome.ozonFailure).toBe('Failed to fetch')
    expect(outcome.wbFailure).toBeNull()
  })

  it('reports both failures at once when both platforms fail to sync, without one blocking the other', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbTokens: () => jsonResponse(200, { has_content_token: true }),
        wbSync: () => jsonResponse(422, { detail: 'invalid_wb_token' }),
        ozonAccount: () => jsonResponse(200, { connected: true }),
        ozonSync: () => jsonResponse(500, { detail: 'ozon_unavailable' }),
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({
      wbFailure: 'Ключ WB не подходит — проверка не прошла.',
      ozonFailure: 'Не удалось синхронизировать Ozon.',
    })
  })

  it('does not call Ozon sync-products when Ozon is not connected, and reports no Ozon failure', async () => {
    const fetchImpl = fetchMock({
      wbTokens: () => jsonResponse(200, { has_content_token: true }),
      wbSync: () => jsonResponse(202, { id: 'job-wb', marketplace: 'wildberries', state: 'queued' }),
      ozonAccount: () => jsonResponse(200, { connected: false }),
    })
    vi.stubGlobal('fetch', fetchImpl)

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: null, ozonFailure: null })
    const calledUrls = fetchImpl.mock.calls.map((c) => urlOf(c[0] as RequestInfo | URL))
    expect(calledUrls.some((u) => u.includes('/integrations/ozon/self/sync-products'))).toBe(false)
  })

  it('shows a clear error when the Ozon connection check itself fails over the network, without blocking WB', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbTokens: () => jsonResponse(200, { has_content_token: true }),
        wbSync: () => jsonResponse(202, { id: 'job-wb', marketplace: 'wildberries', state: 'queued' }),
        ozonAccount: () => {
          throw new TypeError('Failed to fetch')
        },
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: null, ozonFailure: 'Failed to fetch' })
  })

  it.each([403, 500, 503])(
    'shows a clear error when GET /ozon/self/account answers %i, instead of silently skipping Ozon',
    async (status) => {
      vi.stubGlobal(
        'fetch',
        fetchMock({
          wbTokens: () => jsonResponse(200, { has_content_token: true }),
          wbSync: () => jsonResponse(202, { id: 'job-wb', marketplace: 'wildberries', state: 'queued' }),
          ozonAccount: () => jsonResponse(status, { detail: 'boom' }),
        }),
      )

      const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

      expect(outcome.wbFailure).toBeNull()
      expect(outcome.ozonFailure).toBe('Не удалось проверить подключение Ozon.')
    },
  )

  it('shows a clear error when GET /ozon/self/account returns unparsable JSON', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbTokens: () => jsonResponse(200, { has_content_token: true }),
        wbSync: () => jsonResponse(202, { id: 'job-wb', marketplace: 'wildberries', state: 'queued' }),
        ozonAccount: () =>
          new Response('not json', { status: 200, headers: { 'Content-Type': 'application/json' } }),
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome.wbFailure).toBeNull()
    expect(outcome.ozonFailure).not.toBeNull()
  })

  it('silently skips both platforms when neither has a connected key — no fake success/failure', async () => {
    const fetchImpl = fetchMock({
      wbTokens: () => jsonResponse(200, { has_content_token: false }),
      ozonAccount: () => jsonResponse(200, { connected: false }),
    })
    vi.stubGlobal('fetch', fetchImpl)

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: null, ozonFailure: null })
    const calledUrls = fetchImpl.mock.calls.map((c) => urlOf(c[0] as RequestInfo | URL))
    expect(calledUrls.some((u) => u.includes('/integrations/wildberries/self/sync-products'))).toBe(false)
    expect(calledUrls.some((u) => u.includes('/integrations/ozon/self/sync-products'))).toBe(false)
  })
})
