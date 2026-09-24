import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  claimFbsPendingProductScan,
  completeFbsPendingProductScan,
  fbsPendingProductScanComplete,
  fbsScanPrintPreferencesStorageKey,
  loadFbsScanPrintPreferences,
  mergeFbsBufferedHardwareScan,
  peekFbsPendingProductScan,
  productScanPrintPlan,
  saveFbsScanPrintPreferences,
  updateFbsPendingProductScan,
  type FbsScanPrintPreferences,
} from './fbsScanAutoPrint'

const token = (tenant = 'ff-a', user = 'operator-a') =>
  `header.${btoa(JSON.stringify({ tenant_id: tenant, sub: user }))}.signature`

let local = new Map<string, string>()

beforeEach(() => {
  local = new Map()
  vi.stubGlobal('window', {
    localStorage: {
      getItem: (key: string) => local.get(key) ?? null,
      setItem: (key: string, value: string) => { local.set(key, value) },
      removeItem: (key: string) => { local.delete(key) },
    },
  })
})

describe('WMS-514 · FBS product-scan print preferences', () => {
  it('maps all six allowed checkbox modes to product-scan outputs', () => {
    const cases: Array<{
      preferences: FbsScanPrintPreferences
      expected: { printQr: boolean; printChz: boolean; reprintChz: boolean }
    }> = [
      { preferences: { printQr: false, printChz: false, reprintChz: false }, expected: { printQr: false, printChz: false, reprintChz: false } },
      { preferences: { printQr: true, printChz: false, reprintChz: false }, expected: { printQr: true, printChz: false, reprintChz: false } },
      { preferences: { printQr: false, printChz: true, reprintChz: false }, expected: { printQr: false, printChz: true, reprintChz: false } },
      { preferences: { printQr: true, printChz: true, reprintChz: false }, expected: { printQr: true, printChz: true, reprintChz: false } },
      { preferences: { printQr: false, printChz: false, reprintChz: true }, expected: { printQr: false, printChz: false, reprintChz: true } },
      { preferences: { printQr: true, printChz: false, reprintChz: true }, expected: { printQr: true, printChz: false, reprintChz: true } },
    ]

    for (const item of cases) {
      expect(productScanPrintPlan(item.preferences)).toEqual(item.expected)
    }
  })

  it('defaults off and persists separately by tenant and operator', () => {
    expect(loadFbsScanPrintPreferences(token())).toEqual({
      printQr: false,
      printChz: false,
      reprintChz: false,
    })
    saveFbsScanPrintPreferences(token(), {
      printQr: true,
      printChz: true,
      reprintChz: false,
    })
    expect(loadFbsScanPrintPreferences(token())).toEqual({
      printQr: true,
      printChz: true,
      reprintChz: false,
    })
    expect(loadFbsScanPrintPreferences(token('ff-a', 'operator-b')).printQr).toBe(false)
    expect(loadFbsScanPrintPreferences(token('ff-b')).printQr).toBe(false)
    expect(fbsScanPrintPreferencesStorageKey(token()))
      .not.toBe(fbsScanPrintPreferencesStorageKey(token('ff-a', 'operator-b')))
  })

  it('fails closed if persisted CHZ modes are both enabled', () => {
    local.set(fbsScanPrintPreferencesStorageKey(token()), JSON.stringify({
      printQr: true,
      printChz: true,
      reprintChz: true,
    }))
    expect(loadFbsScanPrintPreferences(token())).toEqual({
      printQr: true,
      printChz: true,
      reprintChz: false,
    })
  })

  it('recovers one partial attempt after remount with its original request and snapshot', () => {
    const original = { printQr: true, printChz: true, reprintChz: false }
    const first = claimFbsPendingProductScan(token(), 'supply-a', '4600123', original, () => 'request-a')
    first.scanId = 'scan-a'
    first.orderId = 'order-a'
    first.qrStarted = true
    updateFbsPendingProductScan(token(), 'supply-a', first)

    // A remounted workspace and changed toggles must resume only the missing
    // CHZ with the old server key, not submit that key with a new payload.
    const recovered = claimFbsPendingProductScan(
      token(),
      'supply-a',
      '4600123',
      { printQr: false, printChz: false, reprintChz: true },
      () => 'must-not-be-used',
    )
    expect(recovered).toEqual({
      ...first,
      preferences: original,
      qrStarted: true,
      chzStarted: false,
    })
    expect(peekFbsPendingProductScan(token('ff-a', 'operator-b'), 'supply-a', '4600123')).toBeNull()
    expect(peekFbsPendingProductScan(token(), 'supply-b', '4600123')).toBeNull()
  })

  it('keeps an incomplete attempt across days until explicit completion or cancellation', () => {
    const original = { printQr: true, printChz: false, reprintChz: true }
    const first = claimFbsPendingProductScan(token(), 'supply-a', '4600123', original, () => 'request-a')
    first.createdAt = Date.now() - (7 * 24 * 60 * 60 * 1000)
    first.scanId = 'scan-a'
    first.orderId = 'order-a'
    first.qrStarted = true
    first.chzStarted = false
    updateFbsPendingProductScan(token(), 'supply-a', first)

    const recovered = claimFbsPendingProductScan(
      token(),
      'supply-a',
      '4600123',
      { printQr: false, printChz: true, reprintChz: false },
      () => 'must-not-be-used',
    )
    expect(recovered).toEqual(first)
    expect(recovered.idempotencyKey).toBe('request-a')
    expect(recovered.preferences).toEqual(original)
  })

  it('completes reprint attempts only after every captured target started', () => {
    const qrAndReprint = claimFbsPendingProductScan(
      token(),
      'supply-a',
      '4600123',
      { printQr: true, printChz: false, reprintChz: true },
      () => 'request-a',
    )
    qrAndReprint.chzStarted = true
    expect(fbsPendingProductScanComplete(qrAndReprint)).toBe(false)
    qrAndReprint.qrStarted = true
    expect(fbsPendingProductScanComplete(qrAndReprint)).toBe(true)

    const reprintOnly = {
      ...qrAndReprint,
      preferences: { printQr: false, printChz: false, reprintChz: true },
      qrStarted: false,
    }
    expect(fbsPendingProductScanComplete(reprintOnly)).toBe(true)
  })

  it('joins a busy scanner prefix with the suffix accepted after idle', () => {
    expect(mergeFbsBufferedHardwareScan('FAST-', 'B')).toBe('FAST-B')
    expect(mergeFbsBufferedHardwareScan('0104600', '00000121ABC')).toBe('010460000000121ABC')
  })

  it('uses a new request and current snapshot only after the prior attempt completes', () => {
    const first = claimFbsPendingProductScan(
      token(),
      'supply-a',
      '4600123',
      { printQr: true, printChz: false, reprintChz: false },
      () => 'request-a',
    )
    completeFbsPendingProductScan(token(), 'supply-a', first.barcode)
    const next = claimFbsPendingProductScan(
      token(),
      'supply-a',
      '4600123',
      { printQr: false, printChz: true, reprintChz: false },
      () => 'request-b',
    )
    expect(next.idempotencyKey).toBe('request-b')
    expect(next.preferences).toEqual({ printQr: false, printChz: true, reprintChz: false })
  })
})
