import { expect, it, vi } from 'vitest'
import { createPackingScanController, type PackingScanDeps } from './fbsSequentialPacking'
import { FbsApiError, type FbsScanAutoPrintResult } from './fbsApi'
import type { FbsScanPrintPreferences } from './fbsScanAutoPrint'

function fixture() {
  const result = (id: string): FbsScanAutoPrintResult => ({
    scan_id: `scan-${id}`, order_id: id, wb_order_id: Number(id), requires_honest_sign: false,
    binding_target: null, reprint_recovery: null, qr_asset: null, replayed: false,
    codes: [], printed_codes: [], shortage: 0, order_errors: [],
  })
  let live: FbsScanPrintPreferences = { printQr: true, printChz: false, reprintChz: false }
  const deps: PackingScanDeps = {
    preferences: () => live,
    select: vi.fn().mockResolvedValueOnce(result('1')).mockResolvedValueOnce(result('2')),
    lookupSticker: vi.fn().mockRejectedValue(new FbsApiError('sticker_not_found', 'not found', null, false, 404)),
    directReprint: vi.fn().mockRejectedValue(new FbsApiError('not_a_kiz', 'not a kiz', null, false, 422)),
    release: vi.fn().mockResolvedValue(undefined), undo: vi.fn().mockResolvedValue(null),
    preload: vi.fn().mockResolvedValue('png'), bind: vi.fn().mockResolvedValue(undefined),
    print: vi.fn().mockResolvedValue(undefined), printChz: vi.fn().mockResolvedValue(undefined),
    printCopy: vi.fn().mockResolvedValue(undefined), pack: vi.fn().mockResolvedValue(undefined),
    claim: vi.fn().mockImplementation(() => ({ key: 'request', preferences: { ...live }, labelSizeId: '58x40', explicit: false })),
    saved: () => false, remember: vi.fn(), complete: vi.fn(), changed: vi.fn(),
  }
  return { deps, scanner: createPackingScanController(deps), setPreferences: (p: FbsScanPrintPreferences) => { live = p } }
}

it('C6 scan retry after unchecking QR completes once without stale printing and accepts another order', async () => {
  const { deps, scanner, setPreferences } = fixture()
  vi.mocked(deps.print).mockRejectedValueOnce(new Error('WMS Print unavailable'))
  await expect(scanner.scan('barcode')).rejects.toThrow('WMS Print unavailable')
  expect(deps.pack).not.toHaveBeenCalled()
  setPreferences({ printQr: false, printChz: false, reprintChz: false })
  await scanner.scan('barcode')
  expect(deps.print).toHaveBeenCalledTimes(1)
  expect(deps.select).toHaveBeenCalledTimes(1)
  expect(deps.pack).toHaveBeenCalledTimes(1)
  expect(scanner.hasPending()).toBe(false)
  vi.mocked(deps.lookupSticker).mockResolvedValueOnce({ order_id: '2', wb_order_id: 2, requires_honest_sign: false,
    product: { name: 'Other product', barcode: 'other-product-barcode' }, can_bind: true, block_reason: null, current_kiz: null, needs_confirmation: false } as any)
  await scanner.scan('other-order-sticker')
  expect(deps.select).toHaveBeenCalledTimes(1)
  expect(vi.mocked(deps.pack).mock.calls.map(([r]) => r.order_id)).toEqual(['1', '2'])
  expect(deps.bind).not.toHaveBeenCalled()
})

it('C6 checked QR retry retains operation identity and packs only once', async () => {
  const { deps, scanner } = fixture()
  vi.mocked(deps.print).mockRejectedValueOnce(new Error('WMS Print unavailable'))
  await expect(scanner.scan('barcode')).rejects.toThrow('WMS Print unavailable')
  await scanner.scan('barcode')
  expect(deps.select).toHaveBeenCalledTimes(1)
  expect(vi.mocked(deps.print).mock.calls.map(([r]) => r.scan_id)).toEqual(['scan-1', 'scan-1'])
  expect(vi.mocked(deps.print).mock.calls.map(([, , , key]) => key)).toEqual(['scan-1', 'scan-1'])
  expect(deps.pack).toHaveBeenCalledTimes(1)
  expect(scanner.hasPending()).toBe(false)
})
