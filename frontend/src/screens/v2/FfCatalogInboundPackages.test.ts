import { describe, expect, it } from 'vitest'

import {
  filterInboundPackages,
  lineMatchesFilters,
  type InboundPackage,
  type InboundPackageLine,
} from './FfCatalogInboundPackageFilters'

const firstSellerLine: InboundPackageLine = {
  product_id: 'product-first',
  remaining_qty: 1,
  name: 'Кеды белые',
  sku_code: 'sku-first',
  wb_vendor_code: 'article-first',
  wb_barcode: '460001',
  wb_size: '40',
  seller_name: 'Первый селлер',
}

const secondSellerLine: InboundPackageLine = {
  product_id: 'product-second',
  remaining_qty: 1,
  name: 'Ботинки чёрные',
  sku_code: 'sku-second',
  wb_vendor_code: 'article-second',
  wb_barcode: '460002',
  wb_size: '41',
  seller_name: 'Второй селлер',
}

function packageWithLines(id: string, lines: InboundPackageLine[]): InboundPackage {
  return {
    id,
    kind: 'box',
    number: 1,
    internal_barcode: `INB-${id}`,
    request_id: 'request-1',
    request_display_number: '000001',
    warehouse_name: 'Склад',
    intake_status: 'receiving',
    composition_tracked: true,
    fully_distributed: false,
    remaining_qty: 1,
    lines,
    source_document: {
      kind: 'inbound_intake',
      id: 'request-1',
      number: '000001',
      date: '2026-08-24T10:00:00Z',
    },
  }
}

describe('catalog inbound package filters', () => {
  it('requires seller and text search to match the same package line', () => {
    const packages = [
      packageWithLines('mixed', [firstSellerLine, secondSellerLine]),
      packageWithLines('second-only', [secondSellerLine]),
    ]

    expect(filterInboundPackages(packages, 'Первый селлер', 'кеды')).toHaveLength(1)
    expect(filterInboundPackages(packages, 'Первый селлер', 'ботинки')).toHaveLength(0)
    expect(lineMatchesFilters(firstSellerLine, 'Первый селлер', '460001')).toBe(true)
    expect(lineMatchesFilters(firstSellerLine, 'Первый селлер', 'ARTICLE-FIRST')).toBe(true)
    expect(lineMatchesFilters(firstSellerLine, 'Первый селлер', 'SKU-FIRST')).toBe(true)
  })

  it('always hides packages without product lines', () => {
    const packages = [packageWithLines('empty', []), packageWithLines('filled', [firstSellerLine])]

    expect(filterInboundPackages(packages, '', '')).toEqual([packages[1]])
  })
})
