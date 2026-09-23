import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fbsScanPrintPreferencesStorageKey,
  loadFbsScanPrintPreferences,
  productScanPrintPlan,
  saveFbsScanPrintPreferences,
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
    },
  })
})

describe('WMS-514 · FBS product-scan print preferences', () => {
  it('maps all six allowed checkbox modes to product-scan outputs', () => {
    const cases: Array<{
      preferences: FbsScanPrintPreferences
      expected: { printQr: boolean; printChz: boolean }
    }> = [
      { preferences: { printQr: false, printChz: false, reprintChz: false }, expected: { printQr: false, printChz: false } },
      { preferences: { printQr: true, printChz: false, reprintChz: false }, expected: { printQr: true, printChz: false } },
      { preferences: { printQr: false, printChz: true, reprintChz: false }, expected: { printQr: false, printChz: true } },
      { preferences: { printQr: true, printChz: true, reprintChz: false }, expected: { printQr: true, printChz: true } },
      { preferences: { printQr: false, printChz: false, reprintChz: true }, expected: { printQr: false, printChz: false } },
      { preferences: { printQr: true, printChz: false, reprintChz: true }, expected: { printQr: true, printChz: false } },
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
})
