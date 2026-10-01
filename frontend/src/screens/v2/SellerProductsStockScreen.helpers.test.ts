import { describe, expect, it } from 'vitest'
import {
  cardMarketplaceId,
  chunk,
  itemMarketplaces,
  itemPrimaryBarcode,
  itemSizeLabel,
  marketplaceFilterParam,
  outcomeEntryLabel,
  outcomeEntryMarketplace,
  type AddToFulfillmentOutcomeEntry,
  type SellerCatalogCardItem,
  type SellerCatalogProductItem,
} from './SellerProductsStockScreen'

// WMS-548 D5: чистая логика экрана «Товары» селлера — разбиение выборки на
// порции по 500 (R9, R15) и сопоставление ответа POST /seller-catalog/add-to-fulfillment
// (контракт подтверждён в backend/app/api/seller_catalog.py и решении А12,
// docs/requirements/WMS-548.md: id и marketplace у added/skipped всегда есть,
// id строкой; причину пропуска экран не расшифровывает — только артикул).

function product(overrides: Partial<SellerCatalogProductItem> = {}): SellerCatalogProductItem {
  return {
    key: 'product:p-1',
    on_fulfillment: true,
    marketplace: 'wildberries',
    id: 'p-1',
    sku_code: 'SKU-1',
    name: 'Товар',
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
    ...overrides,
  }
}

function wbCard(overrides: Partial<SellerCatalogCardItem> = {}): SellerCatalogCardItem {
  return {
    key: 'wb:555',
    on_fulfillment: false,
    marketplace: 'wildberries',
    nm_id: 555,
    vendor_code: 'art-555',
    name: 'Карточка WB',
    photo_url: null,
    barcodes: [],
    sizes: [],
    category: null,
    ...overrides,
  }
}

function ozonCard(overrides: Partial<SellerCatalogCardItem> = {}): SellerCatalogCardItem {
  return {
    key: 'ozon:777',
    on_fulfillment: false,
    marketplace: 'ozon',
    ozon_product_id: '777',
    vendor_code: 'offer-777',
    name: 'Карточка Ozon',
    photo_url: null,
    barcodes: [],
    sizes: [],
    category: null,
    ...overrides,
  }
}

function outcomeEntry(overrides: Partial<AddToFulfillmentOutcomeEntry> = {}): AddToFulfillmentOutcomeEntry {
  return { marketplace: 'wildberries', id: '555', vendor_code: 'art-555', ...overrides }
}

describe('chunk', () => {
  it('keeps a short list in a single batch', () => {
    expect(chunk([1, 2, 3], 500)).toEqual([[1, 2, 3]])
  })

  it('splits an exact multiple into equal batches without an empty tail', () => {
    const items = Array.from({ length: 1000 }, (_, i) => i)
    const batches = chunk(items, 500)
    expect(batches).toHaveLength(2)
    expect(batches[0]).toHaveLength(500)
    expect(batches[1]).toHaveLength(500)
  })

  it('puts the remainder in its own last batch (R15: 15 000 карточек порциями)', () => {
    const items = Array.from({ length: 1200 }, (_, i) => i)
    const batches = chunk(items, 500)
    expect(batches.map((b) => b.length)).toEqual([500, 500, 200])
  })

  it('returns no batches for an empty list', () => {
    expect(chunk([], 500)).toEqual([])
  })
})

describe('cardMarketplaceId', () => {
  it('reads nm_id for a WB card as a string (add-to-fulfillment compares id as string)', () => {
    expect(cardMarketplaceId(wbCard({ nm_id: 42 }))).toBe('42')
  })

  it('reads ozon_product_id for an Ozon card as-is (already a string)', () => {
    expect(cardMarketplaceId(ozonCard({ ozon_product_id: '99' }))).toBe('99')
  })

  it('is null when the platform id is missing', () => {
    expect(cardMarketplaceId(wbCard({ nm_id: null }))).toBeNull()
  })
})

describe('itemMarketplaces', () => {
  // R7: строка товара на ФФ — «как сейчас», один в один с etalon. Etalon
  // показывал чип только когда у товара есть Ozon-привязка (ozon_sku/
  // ozon_offer_id) и никогда не показывал чип для WB — этот экран строки
  // на ФФ не меняет, включая объединённую (R13) карточку.
  it('shows only Ozon on a product created purely from Ozon import (no WB nmID)', () => {
    expect(
      itemMarketplaces(product({ wb_nm_id: null, ozon_sku: 'oz-1', ozon_offer_id: null })),
    ).toEqual(['ozon'])
  })

  it('shows only the Ozon chip for a merged card (WMS-548 R13) — WB stays without a chip, as in etalon', () => {
    expect(itemMarketplaces(product({ wb_nm_id: 10, ozon_sku: 'oz-1' }))).toEqual(['ozon'])
  })

  it('shows no chip at all for a WB-only product (etalon convention unchanged)', () => {
    expect(itemMarketplaces(product({ wb_nm_id: 10, ozon_sku: null, ozon_offer_id: null }))).toEqual([])
  })

  // R7: карточка не на ФФ — новая строка, значок площадки обязателен для неё.
  it('marks a not-on-fulfillment WB card as wb', () => {
    expect(itemMarketplaces(wbCard())).toEqual(['wb'])
  })

  it('marks a not-on-fulfillment Ozon card as ozon', () => {
    expect(itemMarketplaces(ozonCard())).toEqual(['ozon'])
  })
})

describe('itemPrimaryBarcode', () => {
  it('prefers the primary WB barcode on a product row', () => {
    expect(
      itemPrimaryBarcode(product({ wb_primary_barcode: '111', wb_barcodes: ['111', '222'] })),
    ).toBe('111')
  })

  it('falls back to the first barcode when there is no explicit primary', () => {
    expect(itemPrimaryBarcode(product({ wb_primary_barcode: null, wb_barcodes: ['222'] }))).toBe('222')
  })

  it('reads the first barcode of a not-on-fulfillment card (all sizes bundled, R2)', () => {
    expect(itemPrimaryBarcode(wbCard({ barcodes: ['333', '444'] }))).toBe('333')
  })

  it('is null when a card has no barcode at all', () => {
    expect(itemPrimaryBarcode(wbCard({ barcodes: [] }))).toBeNull()
  })
})

describe('itemSizeLabel', () => {
  it('shows the single size of a product row', () => {
    expect(itemSizeLabel(product({ wb_size: '42' }))).toBe('42')
  })

  it('shows a dash when a product has no size', () => {
    expect(itemSizeLabel(product({ wb_size: null }))).toBe('—')
  })

  it('joins every size of a not-on-fulfillment card into one line', () => {
    expect(itemSizeLabel(wbCard({ sizes: ['38', '40', '42'] }))).toBe('38, 40, 42')
  })

  it('shows a dash for a card with no sizes', () => {
    expect(itemSizeLabel(wbCard({ sizes: [] }))).toBe('—')
  })
})

describe('outcomeEntryMarketplace', () => {
  it('reads wildberries', () => {
    expect(outcomeEntryMarketplace(outcomeEntry({ marketplace: 'wildberries' }))).toBe('wildberries')
  })

  it('reads ozon', () => {
    expect(outcomeEntryMarketplace(outcomeEntry({ marketplace: 'ozon' }))).toBe('ozon')
  })
})

describe('marketplaceFilterParam — WMS-614 R1/R3', () => {
  it('returns null for "all" so the request stays identical to the no-filter baseline', () => {
    expect(marketplaceFilterParam('all')).toBeNull()
  })

  it('passes "wildberries" through unchanged so /page and /keys get the same marketplace key', () => {
    expect(marketplaceFilterParam('wildberries')).toBe('wildberries')
  })

  it('passes "ozon" through unchanged so /page and /keys get the same marketplace key', () => {
    expect(marketplaceFilterParam('ozon')).toBe('ozon')
  })
})

describe('outcomeEntryLabel — А12: только артикул, без расшифровки причины', () => {
  it('shows the vendor code of the matching selected WB card regardless of the reason code', () => {
    const cards = [wbCard({ nm_id: 555, vendor_code: 'art-555' })]
    expect(
      outcomeEntryLabel(outcomeEntry({ id: '555', reason: 'vendor_code_conflict' }), cards),
    ).toBe('art-555')
  })

  it('matches an Ozon card by marketplace and string id', () => {
    const cards = [ozonCard({ ozon_product_id: '999', vendor_code: 'offer-999' })]
    expect(
      outcomeEntryLabel(outcomeEntry({ marketplace: 'ozon', id: '999', reason: 'ozon_not_supported_yet' }), cards),
    ).toBe('offer-999')
  })

  it('falls back to the response vendor_code when no selected card matches', () => {
    expect(outcomeEntryLabel(outcomeEntry({ id: '42', vendor_code: 'art-42' }), [])).toBe('art-42')
  })

  it('falls back to the id when neither a matching card nor a vendor_code is available (R14: not_found must not leak data)', () => {
    expect(outcomeEntryLabel(outcomeEntry({ id: '7', vendor_code: null, reason: 'not_found' }), [])).toBe('7')
  })
})
