import { describe, expect, it, vi } from 'vitest'
import { createPackingScanController, type PackingScanDeps } from './fbsSequentialPacking'
import type { FbsScanAutoPrintResult } from './fbsApi'

function fixture(requiresKiz = true) {
  const result = (id: string): FbsScanAutoPrintResult => ({
    scan_id: `scan-${id}`, order_id: id, wb_order_id: Number(id), requires_honest_sign: requiresKiz,
    binding_target: null, reprint_recovery: null, qr_asset: null, replayed: false,
    codes: [], printed_codes: [], shortage: 0, order_errors: [],
  })
  const deps: PackingScanDeps = {
    select: vi.fn().mockResolvedValueOnce(result('1')).mockResolvedValueOnce(result('2')),
    preload: vi.fn().mockResolvedValue('png'), bind: vi.fn().mockResolvedValue(undefined),
    print: vi.fn().mockResolvedValue(undefined), pack: vi.fn().mockResolvedValue(undefined),
    claim: vi.fn().mockReturnValue('request'), saved: () => false, remember: vi.fn(), complete: vi.fn(), changed: vi.fn(),
  }
  return { deps, scanner: createPackingScanController(deps) }
}

describe('WMS-604 sequential packing', () => {
  it('preloads after barcode, waits for KIZ, then prints/packs that order and advances the next identical barcode', async () => {
    const { deps, scanner } = fixture()
    await scanner.scan('barcode')
    expect(deps.preload).toHaveBeenCalledTimes(1)
    expect(deps.print).not.toHaveBeenCalled()
    expect(scanner.view()).toMatchObject({ orderId: '1', needsKiz: true })
    await scanner.scan('kiz-1')
    expect(deps.bind).toHaveBeenCalledWith(expect.objectContaining({ order_id: '1' }), 'kiz-1')
    expect(deps.print).toHaveBeenCalledWith(expect.objectContaining({ order_id: '1' }), 'png')
    expect(deps.pack).toHaveBeenCalledWith(expect.objectContaining({ order_id: '1' }))
    expect(scanner.hasPending()).toBe(false)
    await scanner.scan('barcode')
    expect(scanner.view()).toMatchObject({ orderId: '2', needsKiz: true })
    expect(deps.print).toHaveBeenCalledTimes(1)
  })
  it('prints unmarked products immediately and persists their packing', async () => {
    const { deps, scanner } = fixture(false)
    await scanner.scan('barcode')
    expect(deps.bind).not.toHaveBeenCalled()
    expect(deps.print).toHaveBeenCalledTimes(1)
    expect(deps.pack).toHaveBeenCalledTimes(1)
    expect(scanner.hasPending()).toBe(false)
  })
  it('keeps the same order after invalid KIZ without printing', async () => {
    const { deps, scanner } = fixture()
    vi.mocked(deps.bind).mockRejectedValueOnce(new Error('bad KIZ'))
    await scanner.scan('barcode')
    await expect(scanner.scan('bad')).rejects.toThrow('bad KIZ')
    expect(scanner.view()).toMatchObject({ orderId: '1', needsKiz: true })
    expect(deps.print).not.toHaveBeenCalled()
    await scanner.scan('good')
    expect(deps.select).toHaveBeenCalledTimes(1)
    expect(deps.print).toHaveBeenCalledTimes(1)
  })
  it('keeps the saved KIZ and same print identity after printer failure', async () => {
    const { deps, scanner } = fixture()
    vi.mocked(deps.print).mockRejectedValueOnce(new Error('printer offline'))
    await scanner.scan('barcode')
    await expect(scanner.scan('kiz')).rejects.toThrow('printer offline')
    expect(scanner.view()).toMatchObject({ orderId: '1', needsKiz: false })
    expect(deps.pack).not.toHaveBeenCalled()
    await scanner.scan('barcode')
    expect(deps.bind).toHaveBeenCalledTimes(1)
    expect(deps.select).toHaveBeenCalledTimes(1)
    expect(vi.mocked(deps.print).mock.calls.map(([result]) => result.scan_id)).toEqual(['scan-1', 'scan-1'])
  })
  it('reconciles a lost KIZ response on the same product barcode before printing', async () => {
    const { deps, scanner } = fixture()
    vi.mocked(deps.bind).mockRejectedValueOnce(new Error('response lost'))
    await scanner.scan('barcode')
    await expect(scanner.scan('kiz')).rejects.toThrow('response lost')
    const original = vi.mocked(deps.preload).mock.calls[0][0]
    vi.mocked(deps.select).mockReset().mockResolvedValue({ ...original, reprint_recovery: { status: 'available' } })
    await scanner.scan('barcode')
    expect(deps.bind).toHaveBeenCalledTimes(1)
    expect(deps.print).toHaveBeenCalledWith(expect.objectContaining({ order_id: '1' }), 'png')
  })
  it('does not use a different product scan to finish the previous failed print', async () => {
    const { deps, scanner } = fixture()
    vi.mocked(deps.print).mockRejectedValueOnce(new Error('printer offline'))
    await scanner.scan('barcode')
    await expect(scanner.scan('kiz')).rejects.toThrow('printer offline')
    await expect(scanner.scan('different-barcode')).rejects.toThrow('Повторите его штрихкод barcode')
    expect(deps.print).toHaveBeenCalledTimes(1)
    expect(deps.pack).not.toHaveBeenCalled()
    expect(deps.select).toHaveBeenCalledTimes(1)
    expect(scanner.view()).toMatchObject({ orderId: '1', needsKiz: false })
    await scanner.scan('barcode')
    expect(deps.print).toHaveBeenCalledTimes(2)
  })
  it('replays a confirmed binding without asking for another KIZ', async () => {
    const { deps, scanner } = fixture()
    const first = await deps.select('barcode', 'request')
    vi.mocked(deps.select).mockReset().mockResolvedValue({ ...first, reprint_recovery: { status: 'available' } })
    await scanner.scan('barcode')
    expect(deps.bind).not.toHaveBeenCalled()
    expect(deps.print).toHaveBeenCalledTimes(1)
  })
})
