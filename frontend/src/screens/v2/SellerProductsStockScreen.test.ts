import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadSellerCatalogPage, type SellerCatalogItem } from './SellerProductsStockScreen'

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
