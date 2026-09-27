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
})

// WMS-548, ревью Astra №1, F4 (и доработка по её приёмке): «Синхронизировать
// по API» обязана обновить каждую подключённую площадку саму по себе — отказ
// или отсутствие ключа одной площадки не должны отменять синхронизацию другой.
// Неподключённая площадка (нет ключа) пропускается молча — это не ошибка;
// отказ самого запроса синхронизации уже подключённой площадки обязан быть
// виден человеческим текстом, а не кодом и не проглочен.
describe('syncSellerCatalogMarketplaces', () => {
  function urlOf(input: RequestInfo | URL): string {
    return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  }

  // Владелец 27.09.2026 отменил предварительную проверку подключения WB как
  // выход за рамки задачи: WB здесь вызывается напрямую, как в etalon, без
  // GET /integrations/wildberries/self/tokens. Дефолт wbSync — успех, чтобы
  // тесты, посвящённые только Ozon, не писали лишний булерплейт.
  function fetchMock(
    handlers: Partial<{
      wbSync: () => Response | Promise<Response>
      ozonAccount: () => Response
      ozonSync: () => Response | Promise<Response>
    }>,
  ) {
    return vi.fn(async (input: RequestInfo | URL) => {
      const url = urlOf(input)
      if (url.includes('/integrations/wildberries/self/sync-products')) {
        return (handlers.wbSync ?? (() => jsonResponse(200, { updated: 0 })))()
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

  it('calls WB sync-products directly, without a connection pre-check, matching etalon', async () => {
    const fetchImpl = fetchMock({
      wbSync: () => jsonResponse(200, { updated: 3 }),
      ozonAccount: () => jsonResponse(200, { connected: true }),
      ozonSync: () => jsonResponse(200, { updated: 3 }),
    })
    vi.stubGlobal('fetch', fetchImpl)

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: null, ozonFailure: null })
    const calledUrls = fetchImpl.mock.calls.map((c) => urlOf(c[0] as RequestInfo | URL))
    expect(calledUrls.some((u) => u.includes('/integrations/wildberries/self/tokens'))).toBe(false)
    expect(calledUrls.some((u) => u.includes('/integrations/wildberries/self/sync-products'))).toBe(true)
  })

  it('shows the raw server error text for a rejected WB sync, exactly as etalon does (no translation)', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbSync: () => jsonResponse(422, { detail: 'invalid_wb_token' }),
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: 'invalid_wb_token', ozonFailure: null })
  })

  it('shows the raw server error text for an unrecognised WB error code too (no generic fallback phrase)', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbSync: () => jsonResponse(502, { detail: 'upstream_error' }),
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: 'upstream_error', ozonFailure: null })
  })

  it('reports a network failure of the WB sync call itself instead of swallowing it', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbSync: () => {
          throw new TypeError('Failed to fetch')
        },
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: 'Failed to fetch', ozonFailure: null })
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

    expect(outcome).toEqual({ wbFailure: null, ozonFailure: 'Failed to fetch' })
  })

  // R12/F4 (ревью Astra №1): единственное, что из старой WB-логики сохранено
  // после отката владельцем — отказ WB не должен отменять попытку синхронизировать
  // Ozon, и наоборот.
  it('reports both failures at once when both platforms fail to sync, without one blocking the other', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbSync: () => jsonResponse(422, { detail: 'invalid_wb_token' }),
        ozonAccount: () => jsonResponse(200, { connected: true }),
        ozonSync: () => jsonResponse(500, { detail: 'ozon_unavailable' }),
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({
      wbFailure: 'invalid_wb_token',
      ozonFailure: 'Не удалось синхронизировать Ozon.',
    })
  })

  it('does not call Ozon sync-products when Ozon is not connected, and reports no Ozon failure', async () => {
    const fetchImpl = fetchMock({
      wbSync: () => jsonResponse(200, { updated: 4 }),
      ozonAccount: () => jsonResponse(200, { connected: false }),
    })
    vi.stubGlobal('fetch', fetchImpl)

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: null, ozonFailure: null })
    const calledUrls = fetchImpl.mock.calls.map((c) => urlOf(c[0] as RequestInfo | URL))
    expect(calledUrls.some((u) => u.includes('/integrations/ozon/self/sync-products'))).toBe(false)
  })

  // F9 (ревью Astra №2), Ozon-сторона — владелец её не отменял: отказ самой
  // проверки подключения обязан оставить понятную ошибку Ozon, не трогая WB.
  it('shows a clear error when the Ozon connection check itself fails over the network, without blocking WB', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbSync: () => jsonResponse(200, { updated: 1 }),
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
          wbSync: () => jsonResponse(200, { updated: 1 }),
          ozonAccount: () => jsonResponse(status, { detail: 'boom' }),
        }),
      )

      const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

      // 'boom' — код, похожий на машинный (readApiErrorMessage его не знает),
      // поэтому экран не показывает его голым, а даёт человеческий текст.
      // Важно здесь другое: сообщение вообще есть, и это сообщение Ozon.
      expect(outcome.wbFailure).toBeNull()
      expect(outcome.ozonFailure).toBe('Не удалось проверить подключение Ozon.')
    },
  )

  it('shows a clear error when GET /ozon/self/account returns unparsable JSON', async () => {
    vi.stubGlobal(
      'fetch',
      fetchMock({
        wbSync: () => jsonResponse(200, { updated: 1 }),
        ozonAccount: () =>
          new Response('not json', { status: 200, headers: { 'Content-Type': 'application/json' } }),
      }),
    )

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome.wbFailure).toBeNull()
    expect(outcome.ozonFailure).not.toBeNull()
  })

  it('still silently skips a confirmed-not-connected Ozon without any error', async () => {
    const fetchImpl = fetchMock({
      wbSync: () => jsonResponse(200, { updated: 1 }),
      ozonAccount: () => jsonResponse(200, { connected: false }),
    })
    vi.stubGlobal('fetch', fetchImpl)

    const outcome = await syncSellerCatalogMarketplaces({ Authorization: 'Bearer t' })

    expect(outcome).toEqual({ wbFailure: null, ozonFailure: null })
    const calledUrls = fetchImpl.mock.calls.map((c) => urlOf(c[0] as RequestInfo | URL))
    expect(calledUrls.some((u) => u.includes('/integrations/ozon/self/sync-products'))).toBe(false)
  })
})
