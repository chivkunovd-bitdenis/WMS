import { describe, expect, it } from 'vitest'

import { mergePreviewGroups } from './MarkingImportDialog'

describe('mergePreviewGroups', () => {
  it('preserves title and productIds when the same gtin appears again', () => {
    const prev = [
      {
        gtin: '4600000000001',
        codes_count: 2,
        suggested_title: 'Old suggestion',
        title: 'Custom pool name',
        productIds: new Set(['prod-a', 'prod-b']),
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
    })
    expect([...merged[0].productIds]).toEqual(['prod-a', 'prod-b'])
    expect(merged[1]).toMatchObject({
      gtin: '4600000000002',
      codes_count: 1,
      title: 'Second pool',
    })
    expect([...merged[1].productIds]).toEqual([])
  })
})
