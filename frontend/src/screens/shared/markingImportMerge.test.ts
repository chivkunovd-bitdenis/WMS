import { describe, expect, it } from 'vitest'

import { filterProductsBySearch, mergePreviewGroups } from './MarkingImportDialog'

describe('filterProductsBySearch', () => {
  const products = [
    { id: '1', name: 'Alpha shirt', sku_code: 'SKU-ALPHA', seller_id: 's1' },
    { id: '2', name: 'Beta pants', sku_code: 'SKU-BETA', seller_id: 's1' },
  ]

  it('filters by sku or name independently per query string', () => {
    expect(filterProductsBySearch(products, 'alpha')).toEqual([products[0]])
    expect(filterProductsBySearch(products, 'SKU-BETA')).toEqual([products[1]])
    expect(filterProductsBySearch(products, '')).toEqual(products)
  })
})

describe('mergePreviewGroups', () => {
  it('preserves title, productIds, and productSearch when the same gtin appears again', () => {
    const prev = [
      {
        gtin: '4600000000001',
        codes_count: 2,
        suggested_title: 'Old suggestion',
        title: 'Custom pool name',
        productIds: new Set(['prod-a', 'prod-b']),
        productSearch: 'alpha',
      },
    ]
    const incoming = [
      {
        gtin: '4600000000001',
        codes_count: 5,
        suggested_title: 'New suggestion',
      },
      {
        gtin: '4600000000002',
        codes_count: 1,
        suggested_title: 'Second pool',
      },
    ]

    const merged = mergePreviewGroups(prev, incoming)

    expect(merged).toHaveLength(2)
    expect(merged[0]).toMatchObject({
      gtin: '4600000000001',
      codes_count: 5,
      title: 'Custom pool name',
      productSearch: 'alpha',
    })
    expect([...merged[0].productIds]).toEqual(['prod-a', 'prod-b'])
    expect(merged[1]).toMatchObject({
      gtin: '4600000000002',
      codes_count: 1,
      title: 'Second pool',
      productSearch: '',
    })
    expect([...merged[1].productIds]).toEqual([])
  })
})
