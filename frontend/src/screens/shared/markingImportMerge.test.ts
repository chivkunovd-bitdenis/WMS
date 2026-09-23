import { describe, expect, it, vi } from 'vitest'

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
  createAssignmentAttempt,
  keepAssignmentRequestId,
  markAssignmentResponseApplied,
  mergeAssignmentResponse,
  runAssignmentAttempt,
  runAutomaticImportAttempt,
  type AutoImportResponse,
  type ImportCatalogRow,
} from './MarkingImportDialog'

describe('filterProductsBySearch', () => {
  const products: ImportCatalogRow[] = [
    {
      id: '1',
      name: 'Alpha shirt',
      sku_code: 'SKU-ALPHA',
      seller_id: 's1',
      requires_honest_sign: true,
      wb_nm_id: null,
      wb_vendor_code: null,
      wb_subject_name: null,
      wb_primary_image_url: null,
      wb_barcodes: [],
      wb_primary_barcode: null,
      wb_size: null,
    },
    {
      id: '2',
      name: 'Beta pants',
      sku_code: 'SKU-BETA',
      seller_id: 's1',
      requires_honest_sign: true,
      wb_nm_id: null,
      wb_vendor_code: null,
      wb_subject_name: null,
      wb_primary_image_url: null,
      wb_barcodes: [],
      wb_primary_barcode: null,
      wb_size: null,
    },
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

describe('automatic import recovery', () => {
  it('calls auto API and enters the result stage for an invalid-only preview', async () => {
    const response = {
      import_id: 'import-id',
      document_number: 'МК-1',
      groups: [],
      unmatched: [{
        key: '0', marking_code: '', article: null, size: null,
        reason: 'DataMatrix повреждён', eligible_for_assignment: false,
        has_label_artifact: true,
      }],
    }
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify(response),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))

    const outcome = await runAutomaticImportAttempt({
      files: [new File(['damaged'], 'damaged.pdf', { type: 'application/pdf' })],
      previewComplete: true,
      selectedProductCount: 0,
      sellerId: 'seller-id',
      token: 'token',
      requestId: 'request-id',
      fetchImpl,
    })

    expect(fetchImpl).toHaveBeenCalledOnce()
    expect(String(fetchImpl.mock.calls[0]?.[0])).toContain('/operations/marking-codes/import/auto')
    expect(outcome).toEqual({ stage: 'auto-result', data: response })
  })

  it('recovers an immutable lost-response attempt once before a new assignment', async () => {
    const attempt = createAssignmentAttempt('original-request-id', 'product-a', ['0', '1'])
    const response = {
      import_id: 'original-request-id',
      document_number: 'МК-2',
      product: {
        product_id: 'product-a', sku: 'SKU-A', product_name: 'Product A',
        size: 'M', barcode: '4600000000001', loaded_count: 2,
      },
      assigned_keys: ['0', '1'],
    }
    const sentBodies: Array<{ requestId: FormDataEntryValue | null; productId: FormDataEntryValue | null; rowKeys: FormDataEntryValue | null }> = []
    const fetchImpl = vi.fn<typeof fetch>().mockImplementation(async (_input, init) => {
      const form = init?.body as FormData
      sentBodies.push({
        requestId: form.get('request_id'),
        productId: form.get('product_id'),
        rowKeys: form.get('row_keys_json'),
      })
      if (sentBodies.length === 1) throw new TypeError('response lost')
      return new Response(JSON.stringify(response), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      })
    })
    const request = {
      attempt,
      files: [new File(['pdf'], 'labels.pdf', { type: 'application/pdf' })],
      sellerId: 'seller-id',
      token: 'token',
      fetchImpl,
    }

    expect(await runAssignmentAttempt(request)).toEqual({
      status: 'unknown', message: 'response lost',
    })
    const recovered = await runAssignmentAttempt(request)
    expect(recovered).toEqual({ status: 'success', data: response })
    expect(sentBodies).toEqual([
      { requestId: 'original-request-id', productId: 'product-a', rowKeys: '["0","1"]' },
      { requestId: 'original-request-id', productId: 'product-a', rowKeys: '["0","1"]' },
    ])

    let result: AutoImportResponse = {
      import_id: 'auto-id', document_number: 'МК-1',
      groups: [{ ...response.product, loaded_count: 1 }],
      unmatched: [
        { key: '0', marking_code: 'code-0', article: 'A', size: 'M', reason: 'Нет товара', eligible_for_assignment: true, has_label_artifact: true },
        { key: '1', marking_code: 'code-1', article: 'A', size: 'M', reason: 'Нет товара', eligible_for_assignment: true, has_label_artifact: true },
        { key: '2', marking_code: 'code-2', article: 'B', size: 'L', reason: 'Нет товара', eligible_for_assignment: true, has_label_artifact: true },
      ],
    }
    const applied = new Set<string>()
    if (markAssignmentResponseApplied(applied, response.import_id)) {
      result = mergeAssignmentResponse(result, response)
    }
    if (markAssignmentResponseApplied(applied, response.import_id)) {
      result = mergeAssignmentResponse(result, response)
    }
    expect(result.groups[0]?.loaded_count).toBe(3)
    expect(result.unmatched.map((row) => row.key)).toEqual(['2'])

    const create = vi.fn(() => 'next-request-id')
    expect(keepAssignmentRequestId(null, create)).toBe('next-request-id')
    expect(create).toHaveBeenCalledOnce()
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
