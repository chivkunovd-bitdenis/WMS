import { describe, expect, it } from 'vitest'

import {
  classifyWms514MockScan,
  createWms514MockupScanPrinting,
  simulateWms514ProductScan,
  WMS514_BOUND_KIZ,
  WMS514_DIRECT_KIZ,
  WMS514_ORDER_QR,
  WMS514_PRODUCT_BARCODE,
  type Wms514MockupModes,
} from './wms514Logic'

describe('WMS-514 clickable mockup scan logic', () => {
  it('demonstrates exactly the six allowed product-scan modes', () => {
    const cases: Array<{
      modes: Wms514MockupModes
      outputs: string[]
      waits: boolean
      handled: boolean
    }> = [
      { modes: { printQr: false, printChz: false, reprintChz: false }, outputs: [], waits: false, handled: false },
      { modes: { printQr: true, printChz: false, reprintChz: false }, outputs: ['order_qr'], waits: false, handled: true },
      { modes: { printQr: false, printChz: true, reprintChz: false }, outputs: ['new_chz'], waits: false, handled: true },
      { modes: { printQr: true, printChz: true, reprintChz: false }, outputs: ['order_qr', 'new_chz'], waits: false, handled: true },
      { modes: { printQr: false, printChz: false, reprintChz: true }, outputs: [], waits: true, handled: true },
      { modes: { printQr: true, printChz: false, reprintChz: true }, outputs: ['order_qr'], waits: true, handled: true },
    ]

    for (const item of cases) {
      const result = simulateWms514ProductScan(item.modes, 0)
      expect(result.handled).toBe(item.handled)
      expect(result.outputs).toEqual(item.outputs)
      expect(result.waitsForFullKiz).toBe(item.waits)
      expect(result.outputs).not.toContain('product_barcode')
    }
  })

  it('classifies only the exact deterministic QR, product and full KIZ codes', () => {
    expect(classifyWms514MockScan(WMS514_ORDER_QR)).toBe('order_qr')
    expect(classifyWms514MockScan(WMS514_PRODUCT_BARCODE)).toBe('product')
    expect(classifyWms514MockScan(WMS514_DIRECT_KIZ)).toBe('full_kiz')
    expect(classifyWms514MockScan(WMS514_BOUND_KIZ)).toBe('full_kiz')
    expect(classifyWms514MockScan('4680123456788')).toBe('unknown')
    expect(classifyWms514MockScan('not-WB-and-not-a-kiz')).toBe('unknown')
  })

  it('directly reprints one exact full KIZ without allocating a new code', async () => {
    const mockup = createWms514MockupScanPrinting()
    const result = await mockup.handleIdleScan(WMS514_DIRECT_KIZ, {
      printQr: false,
      printChz: false,
      reprintChz: true,
    })
    expect(result).toMatchObject({ handled: true, outputs: ['exact_chz_reprint'] })
    expect(result.notice).toContain('Новый код не выделялся')
  })

  it('does not guess a product barcode or arbitrary text as a KIZ', async () => {
    const mockup = createWms514MockupScanPrinting()
    const product = await mockup.handleIdleScan(WMS514_PRODUCT_BARCODE, {
      printQr: false,
      printChz: false,
      reprintChz: true,
    })
    expect(product.outputs).toEqual([])
    expect(product.notice).toContain('ожидается отдельный скан полного ЧЗ')

    const unknown = await mockup.handleIdleScan('not-WB-and-not-a-kiz', {
      printQr: false,
      printChz: false,
      reprintChz: true,
    })
    expect(unknown.error).toContain('Код не распознан')
  })

  it('reprints after QR to KIZ only for the exact committed mock KIZ', async () => {
    const mockup = createWms514MockupScanPrinting()
    await expect(mockup.reprintBoundKiz(WMS514_BOUND_KIZ)).resolves.toBe(true)
    await expect(mockup.reprintBoundKiz(WMS514_PRODUCT_BARCODE)).resolves.toBe(false)
    await expect(mockup.reprintBoundKiz('almost-a-kiz')).resolves.toBe(false)
  })
})
