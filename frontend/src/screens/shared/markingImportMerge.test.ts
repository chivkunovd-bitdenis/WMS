import { describe, expect, it } from 'vitest'

import {
  applyPoolContextToGroup,
  filterProductsBySearch,
  findFirstGtinWithMissingTitle,
  gtinMatches,
  gtinsWithMissingTitle,
  isImportGroupTitleMissing,
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

describe('import group title validation helpers', () => {
  const groups = [
    { gtin: '4600000000001', title: 'Pool A' },
    { gtin: '4600000000002', title: '   ' },
    { gtin: '4600000000003', title: '' },
  ]

  it('detects whitespace-only titles as missing', () => {
    expect(isImportGroupTitleMissing('')).toBe(true)
    expect(isImportGroupTitleMissing('   ')).toBe(true)
    expect(isImportGroupTitleMissing('Pool')).toBe(false)
  })

  it('collects all gtins with missing titles in file order', () => {
    expect(gtinsWithMissingTitle(groups)).toEqual(['4600000000002', '4600000000003'])
  })

  it('returns the first gtin with missing title for scroll target', () => {
    expect(findFirstGtinWithMissingTitle(groups)).toBe('4600000000002')
    expect(findFirstGtinWithMissingTitle([{ gtin: '1', title: 'Ok' }])).toBeNull()
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

  it('prefills title and productIds from pool context for matching gtin', () => {
    const incoming = [
      {
        gtin: '4601234567890',
        codes_count: 3,
        suggested_title: 'Suggested from file',
      },
      {
        gtin: '4609999999999',
        codes_count: 1,
        suggested_title: 'Other pool',
      },
    ]
    const poolContext = {
      gtin: '4601234567890',
      title: 'Existing Pool Title',
      productIds: ['prod-1', 'prod-2'],
    }

    const merged = mergePreviewGroups([], incoming, poolContext)

    expect(merged[0]).toMatchObject({
      gtin: '4601234567890',
      title: 'Existing Pool Title',
    })
    expect([...merged[0].productIds]).toEqual(['prod-1', 'prod-2'])
    expect(merged[1]).toMatchObject({
      gtin: '4609999999999',
      title: 'Other pool',
    })
    expect([...merged[1].productIds]).toEqual([])
  })

  it('does not re-apply pool context on re-preview for existing groups', () => {
    const poolContext = {
      gtin: '4601234567890',
      title: 'Pool from dashboard',
      productIds: ['prod-1', 'prod-2'],
    }
    const prev = [
      {
        gtin: '4601234567890',
        codes_count: 2,
        suggested_title: 'Suggested',
        title: 'User edited title',
        productIds: new Set(['prod-user-only']),
        productSearch: 'alpha',
      },
    ]
    const incoming = [
      {
        gtin: '4601234567890',
        codes_count: 5,
        suggested_title: 'New suggestion',
      },
    ]

    const merged = mergePreviewGroups(prev, incoming, poolContext)

    expect(merged).toHaveLength(1)
    expect(merged[0]).toMatchObject({
      gtin: '4601234567890',
      codes_count: 5,
      title: 'User edited title',
      productSearch: 'alpha',
    })
    expect([...merged[0].productIds]).toEqual(['prod-user-only'])
  })

  it('preserves user edits when re-preview uses 14-digit gtin variant', () => {
    const poolContext = {
      gtin: '4601234567890',
      title: 'Pool from dashboard',
      productIds: ['prod-1'],
    }
    const prev = [
      {
        gtin: '04601234567890',
        codes_count: 1,
        suggested_title: 'File',
        title: 'Kept title',
        productIds: new Set(['prod-x']),
        productSearch: '',
      },
    ]
    const incoming = [
      {
        gtin: '4601234567890',
        codes_count: 3,
        suggested_title: 'Updated suggestion',
      },
    ]

    const merged = mergePreviewGroups(prev, incoming, poolContext)

    expect(merged[0].title).toBe('Kept title')
    expect([...merged[0].productIds]).toEqual(['prod-x'])
    expect(merged[0].codes_count).toBe(3)
  })
})

describe('gtinMatches', () => {
  it('matches 13- and 14-digit GTIN variants', () => {
    expect(gtinMatches('4601234567890', '04601234567890')).toBe(true)
    expect(gtinMatches('04601234567890', '4601234567890')).toBe(true)
    expect(gtinMatches('4601234567890', '4609999999999')).toBe(false)
  })
})

describe('applyPoolContextToGroup', () => {
  const baseGroup = {
    gtin: '4601234567890',
    codes_count: 2,
    suggested_title: 'File suggestion',
    title: 'File suggestion',
    productIds: new Set<string>(),
    productSearch: '',
  }

  it('overrides title and merges product ids when gtin matches', () => {
    const result = applyPoolContextToGroup(baseGroup, {
      gtin: '4601234567890',
      title: 'Pool from dashboard',
      productIds: ['p1'],
    })

    expect(result.title).toBe('Pool from dashboard')
    expect([...result.productIds]).toEqual(['p1'])
  })

  it('leaves group unchanged when gtin differs', () => {
    const result = applyPoolContextToGroup(baseGroup, {
      gtin: '9999999999999',
      title: 'Other',
      productIds: ['p1'],
    })

    expect(result).toEqual(baseGroup)
  })

  it('applies context when file gtin is 14-digit variant of pool gtin', () => {
    const group14 = { ...baseGroup, gtin: '04601234567890' }
    const result = applyPoolContextToGroup(group14, {
      gtin: '4601234567890',
      title: 'Pool from dashboard',
      productIds: ['p1'],
    })

    expect(result.title).toBe('Pool from dashboard')
    expect([...result.productIds]).toEqual(['p1'])
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
