import { describe, expect, it } from 'vitest'
import { resolveProductBarcodeOptions, resolveProductBarcodeSelection, resolveProductPrimaryBarcode } from './wbProductCatalog'

describe('product marketplace barcodes', () => {
  it('keeps the existing primary WB barcode before the other WB codes', () => {
    const meta = { wb_primary_barcode: ' 460-primary ', wb_barcodes: ['460-secondary', '460-primary'] }
    expect(resolveProductPrimaryBarcode(meta)).toBe('460-primary')
    expect(resolveProductBarcodeOptions(meta)).toEqual([
      { marketplace: 'wb', barcode: '460-primary' },
      { marketplace: 'wb', barcode: '460-secondary' },
    ])
  })

  it('prints a real Ozon-only binding code', () => {
    const meta = { marketplace_bindings: [{ marketplace: 'ozon' as const, external_sku: '123', external_barcodes: [' OZN-real-code '] }] }
    expect(resolveProductPrimaryBarcode(meta)).toBe('OZN-real-code')
    expect(resolveProductBarcodeOptions(meta)).toEqual([{ marketplace: 'ozon', barcode: 'OZN-real-code' }])
  })

  it('keeps marketplace identity and all distinct codes for a combined card', () => {
    const options = resolveProductBarcodeOptions({
      wb_primary_barcode: 'same',
      marketplace_bindings: [
        { marketplace: 'wb', external_barcodes: ['same'] },
        { marketplace: 'ozon', external_barcodes: ['same', 'ozon-second', 'ozon-second', ' '] },
      ],
    })
    expect(options).toEqual([
      { marketplace: 'wb', barcode: 'same' },
      { marketplace: 'ozon', barcode: 'same' },
      { marketplace: 'ozon', barcode: 'ozon-second' },
    ])
  })

  it('never synthesizes a barcode from an Ozon SKU or offer id', () => {
    const meta = { marketplace_bindings: [{ marketplace: 'ozon' as const, external_sku: '123', external_offer_id: 'offer', external_barcodes: ['', '  '] }] }
    expect(resolveProductBarcodeOptions(meta)).toEqual([])
    expect(resolveProductPrimaryBarcode(meta)).toBe('')
  })
})


describe('selected product barcode', () => {
  it('selects the exact Ozon code and preserves marketplace identity for identical codes', () => {
    const options = resolveProductBarcodeOptions({ wb_primary_barcode: 'shared', marketplace_bindings: [
      { marketplace: 'ozon', external_barcodes: ['shared', 'ozon-second'] },
    ] })
    expect(resolveProductBarcodeSelection(options, 'ozon:shared')).toEqual({ marketplace: 'ozon', barcode: 'shared' })
    expect(resolveProductBarcodeSelection(options, 'ozon:ozon-second')?.barcode).toBe('ozon-second')
    expect(resolveProductBarcodeSelection(options, 'wb:shared')?.marketplace).toBe('wb')
  })

  it('drops a previous product selection when the current product does not contain it', () => {
    const options = [{ marketplace: 'ozon' as const, barcode: 'current-code' }]
    expect(resolveProductBarcodeSelection(options, 'ozon:previous-code')?.barcode).toBe('current-code')
    expect(resolveProductBarcodeSelection([], 'ozon:previous-code')).toBeUndefined()
  })
})
