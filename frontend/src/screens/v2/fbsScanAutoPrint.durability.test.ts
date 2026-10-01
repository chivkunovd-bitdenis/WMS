// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { claimFbsPendingProductScan, fbsPendingProductScanStorageKey, peekFbsPendingProductScan } from './fbsScanAutoPrint'
const supply = 'supply:sequential-packing'
const prefs = { printQr: true, printChz: false, reprintChz: false }
afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })
describe('mass packing saved selection pointer', () => {
  it('fails before returning new selection key on storage write failure', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    expect(() => claimFbsPendingProductScan('token', supply, 'barcode', prefs, () => 'key')).toThrow('Не удалось сохранить')
  })
  it('preserves corrupt content and refuses to reinterpret it as no pending scan', () => {
    const key = fbsPendingProductScanStorageKey('token', supply)
    localStorage.setItem(key, '[{"bad":1}]')
    expect(() => claimFbsPendingProductScan('token', supply, 'barcode', prefs, () => 'new')).toThrow('Не удалось прочитать')
    expect(localStorage.getItem(key)).toBe('[{"bad":1}]')
  })
  it('restores original key after a controller is recreated', () => {
    claimFbsPendingProductScan('token', supply, 'barcode', prefs, () => 'original')
    expect(claimFbsPendingProductScan('token', supply, 'barcode', prefs, () => 'new').idempotencyKey).toBe('original')
    expect(peekFbsPendingProductScan('token', supply, 'barcode')?.idempotencyKey).toBe('original')
  })
})
