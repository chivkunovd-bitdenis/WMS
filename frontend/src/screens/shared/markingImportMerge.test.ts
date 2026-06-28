import { describe, expect, it } from 'vitest'

import {
  filterProductsBySearch,
  mergePreviewGroups,
  paginateProductSearchResults,
  PRODUCT_SEARCH_INITIAL_LIMIT,
  removeImportFileAt,
} from './MarkingImportDialog'

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

describe('removeImportFileAt', () => {
  const fileA = new File(['a'], 'a.csv', { type: 'text/csv' })
  const fileB = new File(['b'], 'b.csv', { type: 'text/csv' })
  const fileC = new File(['c'], 'c.csv', { type: 'text/csv' })

  it('removes the file at the given index', () => {
    expect(removeImportFileAt([fileA, fileB, fileC], 1)).toEqual([fileA, fileC])
  })

  it('returns the same list for out-of-range index', () => {
    const files = [fileA, fileB]
    expect(removeImportFileAt(files, -1)).toEqual(files)
    expect(removeImportFileAt(files, 2)).toEqual(files)
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

describe('paginateProductSearchResults', () => {
  const items = Array.from({ length: 12 }, (_, index) => `item-${index + 1}`)

  it('returns the first page when the list exceeds the limit', () => {
    const result = paginateProductSearchResults(items, false)

    expect(result.visible).toHaveLength(PRODUCT_SEARCH_INITIAL_LIMIT)
    expect(result.total).toBe(12)
    expect(result.truncated).toBe(true)
    expect(result.limit).toBe(PRODUCT_SEARCH_INITIAL_LIMIT)
    expect(result.visible[0]).toBe('item-1')
    expect(result.visible.at(-1)).toBe(`item-${PRODUCT_SEARCH_INITIAL_LIMIT}`)
  })

  it('returns all items after show more is requested', () => {
    const result = paginateProductSearchResults(items, true)

    expect(result.visible).toEqual(items)
    expect(result.truncated).toBe(false)
  })

  it('does not truncate short lists', () => {
    const shortList = items.slice(0, 5)
    const result = paginateProductSearchResults(shortList, false)

    expect(result.visible).toEqual(shortList)
    expect(result.truncated).toBe(false)
  })
})
