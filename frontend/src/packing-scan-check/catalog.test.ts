import { describe, expect, it } from 'vitest'
import { TEST_LABELS, findTestLabel } from './catalog'

describe('standalone printer check', () => {
  it('maps exactly ten distinct test barcodes to distinct synthetic QR payloads', () => {
    expect(TEST_LABELS).toHaveLength(10)
    expect(new Set(TEST_LABELS.map((row) => row.barcode)).size).toBe(10)
    expect(new Set(TEST_LABELS.map((row) => row.qr)).size).toBe(10)
    for (const row of TEST_LABELS) {
      expect(findTestLabel(`${row.barcode}\r\n`)).toEqual(row)
      expect(row.qr).toMatch(/^WMS-PRINT-TEST-\d{2}$/)
    }
    expect(findTestLabel('unknown')).toBeUndefined()
  })
})
