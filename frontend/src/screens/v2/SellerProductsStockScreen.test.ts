import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadSellerCatalog } from './SellerProductsStockScreen'

function catalogRow(id: string, name: string) {
  return {
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

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

// WMS-488: каталог селлера грузится по токену вкладки. Пока ответ шёл, сессию
// могли сменить — тогда пришедшие строки описывают прежнего селлера.
describe('seller catalog response', () => {
  it('shows the rows of the session that asked for them', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, [catalogRow('p-1', 'Палантин')])),
    )

    const result = await loadSellerCatalog({ Authorization: 'Bearer token-goryachkina' }, () => true)

    expect(result).toEqual({ outcome: 'loaded', rows: [catalogRow('p-1', 'Палантин')] })
  })

  it('discards rows that arrive after the tab switched to another seller', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, [catalogRow('p-1', 'Палантин')])),
    )
    let sessionToken = 'token-goryachkina'

    const pending = loadSellerCatalog(
      { Authorization: 'Bearer token-goryachkina' },
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

    const pending = loadSellerCatalog(
      { Authorization: 'Bearer token-goryachkina' },
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

    const result = await loadSellerCatalog({ Authorization: 'Bearer token-goryachkina' }, () => true)

    expect(result).toEqual({ outcome: 'failed', message: 'boom' })
  })
})
