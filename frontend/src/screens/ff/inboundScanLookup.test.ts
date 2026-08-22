import { describe, expect, it } from 'vitest'
import type { WbProductCatalogRow } from '../../types/wbProductCatalog'
import { buildInboundScanProductMap, findInboundScanProductId } from './inboundScanLookup'

describe('inbound scan product lookup', () => {
  it('resolves SKU, primary and alternate WB barcodes once on the client', () => {
    const catalog = new Map<string, WbProductCatalogRow>([
      [
        'p1',
        {
          id: 'p1',
          name: 'Product',
          sku_code: 'sku-1',
          wb_nm_id: 1,
          wb_vendor_code: null,
          wb_subject_name: null,
          wb_primary_image_url: null,
          wb_barcodes: ['460000000001', 'ALT-code'],
          wb_primary_barcode: '460000000001',
          wb_size: null,
          wb_color: null,
        },
      ],
    ])
    const lookup = buildInboundScanProductMap(
      [{ product_id: 'p1', sku_code: 'sku-1', wb_barcode: null }],
      catalog,
    )

    expect(findInboundScanProductId('sku-1', lookup)).toBe('p1')
    expect(findInboundScanProductId('SKU-1', lookup)).toBe('p1')
    expect(findInboundScanProductId('460000000001', lookup)).toBe('p1')
    expect(findInboundScanProductId('alt-CODE', lookup)).toBe('p1')
    expect(findInboundScanProductId('missing', lookup)).toBeUndefined()
  })
})
