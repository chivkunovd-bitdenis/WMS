import { describe, expect, it, vi } from 'vitest'
import { createPackingScanController, routePackingScan, type PackingScanController, type PackingScanDeps } from './fbsSequentialPacking'
import { FbsApiError, type FbsScanAutoPrintResult } from './fbsApi'

function fixture(requiresKiz = true) {
  const result = (id: string): FbsScanAutoPrintResult => ({
    scan_id: `scan-${id}`, order_id: id, wb_order_id: Number(id), requires_honest_sign: requiresKiz,
    binding_target: null, reprint_recovery: null, qr_asset: null, replayed: false,
    codes: [], printed_codes: [], shortage: 0, order_errors: [],
  })
  const qrOnly = { printQr: true, printChz: false, reprintChz: false }
  const deps: PackingScanDeps = {
    preferences: () => qrOnly,
    select: vi.fn().mockResolvedValueOnce(result('1')).mockResolvedValueOnce(result('2')),
    lookupSticker: vi.fn().mockRejectedValue(new FbsApiError('sticker_not_found', 'sticker_not_found', null, false, 404)),
    directReprint: vi.fn().mockRejectedValue(new FbsApiError('not_a_kiz', 'not_a_kiz', null, false, 422)),
    release: vi.fn().mockResolvedValue(undefined),
    preload: vi.fn().mockResolvedValue('png'), bind: vi.fn().mockResolvedValue(undefined),
    print: vi.fn().mockResolvedValue(undefined), printChz: vi.fn().mockResolvedValue(undefined),
    printCopy: vi.fn().mockResolvedValue(undefined), pack: vi.fn().mockResolvedValue(undefined),
    claim: vi.fn().mockReturnValue({ key: 'request', preferences: qrOnly }), saved: () => false,
    remember: vi.fn(), complete: vi.fn(), changed: vi.fn(),
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
    expect(deps.pack).toHaveBeenCalledWith(expect.objectContaining({ order_id: '1' }), false, 'barcode')
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
    const first = await deps.select('barcode', 'request', { printQr: true, printChz: false, reprintChz: false })
    vi.mocked(deps.select).mockReset().mockResolvedValue({ ...first, reprint_recovery: { status: 'available' } })
    await scanner.scan('barcode')
    expect(deps.bind).not.toHaveBeenCalled()
    expect(deps.print).toHaveBeenCalledTimes(1)
  })
})


describe('WMS-604 scan routing recovery', () => {
  it.each(['scan_product_not_found', 'scan_product_exhausted'])('WMS-630: resumes routing to the other supply after the selected row gate completes with %s', async (code) => {
    let selected = true
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => { release = resolve })
    const first: PackingScanController = {
      hasSelectedRow: () => selected, hasPending: () => selected,
      hasSavedAttempt: () => false, view: () => null,
      scan: vi.fn(async () => {
        await gate
        selected = false
        throw new FbsApiError(code, code, null, false, 404)
      }),
    }
    const second = fixture()
    const routed = routePackingScan([first, second.scanner], 'next-product')
    expect(second.deps.select).not.toHaveBeenCalled()
    release()
    await routed
    expect(first.scan).toHaveBeenCalledTimes(1)
    expect(second.deps.select).toHaveBeenCalledWith('next-product', 'request')
    expect(second.scanner.hasPending()).toBe(true)
  })

  it.each(['pending', 'saved'])('WMS-630: keeps %s priority among remaining supplies after a completed row', async (priority) => {
    let selected = true
    const first: PackingScanController = {
      hasSelectedRow: () => selected, hasPending: () => false,
      hasSavedAttempt: () => false, view: () => null,
      scan: vi.fn(async () => {
        selected = false
        throw new FbsApiError('scan_product_not_found', 'not found', null, false, 404)
      }),
    }
    const ordinary = fixture()
    const preferred: PackingScanController = {
      hasPending: () => priority === 'pending', hasSavedAttempt: () => priority === 'saved',
      view: () => null, scan: vi.fn(async () => undefined),
    }
    await routePackingScan([first, ordinary.scanner, preferred], 'next-product')
    expect(first.scan).toHaveBeenCalledTimes(1)
    expect(ordinary.deps.select).not.toHaveBeenCalled()
    expect(preferred.scan).toHaveBeenCalledWith('next-product')
  })

  it('WMS-630: does not route a still-selected row failure to another supply', async () => {
    const failure = new FbsApiError('scan_product_not_found', 'bad KIZ', null, false, 404)
    const first: PackingScanController = {
      hasSelectedRow: () => true, hasPending: () => true,
      hasSavedAttempt: () => false, view: () => null,
      scan: vi.fn(async () => { throw failure }),
    }
    const second = fixture()
    await expect(routePackingScan([first, second.scanner], 'kiz')).rejects.toBe(failure)
    expect(second.deps.select).not.toHaveBeenCalled()
  })

  it.each(['scan_product_not_found', 'scan_product_exhausted'])('continues to supply B on the same retry after saved supply A returns %s', async (code) => {
    const first = fixture()
    const second = fixture()
    let saved = false
    first.deps.saved = () => saved
    // Recreate after overriding saved, as the controller captures its function.
    first.scanner = createPackingScanController(first.deps)
    vi.mocked(first.deps.claim).mockImplementation(() => { saved = true; return { key: 'same-request', preferences: { printQr: true, printChz: false, reprintChz: false } } })
    vi.mocked(first.deps.select).mockReset()
      .mockRejectedValueOnce(new Error('network lost'))
      .mockRejectedValueOnce(new FbsApiError(code, code, null, false, 404))
    await expect(routePackingScan([first.scanner, second.scanner], 'barcode')).rejects.toThrow('network lost')
    expect(second.deps.select).not.toHaveBeenCalled()
    await routePackingScan([first.scanner, second.scanner], 'barcode')
    expect(first.deps.select).toHaveBeenCalledTimes(2)
    expect(second.deps.select).toHaveBeenCalledTimes(1)
    expect(second.scanner.view()?.orderId).toBe('1')
  })
  it('keeps a selected order authoritative instead of routing its failure to another supply', async () => {
    const first = fixture()
    const second = fixture()
    await first.scanner.scan('barcode')
    vi.mocked(first.deps.bind).mockRejectedValueOnce(new FbsApiError('scan_product_not_found', 'binding failed', null, false, 404))
    await expect(routePackingScan([first.scanner, second.scanner], 'kiz')).rejects.toThrow('binding failed')
    expect(second.deps.select).not.toHaveBeenCalled()
    expect(first.scanner.view()?.orderId).toBe('1')
  })
})

describe('WMS-631 one mechanism with the supply checkboxes', () => {
  const lookup = { order_id: '7', wb_order_id: 7, product: { name: 'Товар', image_url: null, barcode: null, seller_article: null },
    current_kiz: null, needs_confirmation: false, can_bind: true, block_reason: null, requires_honest_sign: true }
  const off = { printQr: false, printChz: false, reprintChz: false }
  it('M8: all off — sticker, then KIZ binds and packs without any print or scan-auto-print', async () => {
    const { deps } = fixture()
    deps.preferences = () => off
    deps.claim = vi.fn().mockReturnValue({ key: 'k', preferences: off })
    deps.lookupSticker = vi.fn().mockResolvedValue(lookup)
    const scanner = createPackingScanController(deps)
    await scanner.scan('sticker')
    expect(deps.select).not.toHaveBeenCalled()
    expect(scanner.view()).toMatchObject({ orderId: '7', needsKiz: true })
    await scanner.scan('kiz')
    expect(deps.bind).toHaveBeenCalledWith(expect.objectContaining({ scan_id: 'local:k' }), 'kiz')
    expect(deps.print).not.toHaveBeenCalled()
    expect(deps.pack).toHaveBeenCalledWith(expect.objectContaining({ order_id: '7' }), true, 'sticker')
  })
  it('M10: all off — a product barcode gives the sticker error and selects nothing', async () => {
    const { deps } = fixture()
    deps.preferences = () => off
    const scanner = createPackingScanController(deps)
    await expect(routePackingScan([scanner], 'barcode')).rejects.toMatchObject({ code: 'sticker_not_found' })
    expect(deps.select).not.toHaveBeenCalled()
    expect(scanner.hasPending()).toBe(false)
  })
  it('M4: QR + pool KIZ prints QR then the KIZ label and packs without a KIZ scan', async () => {
    const { deps } = fixture()
    const qrChz = { printQr: true, printChz: true, reprintChz: false }
    deps.preferences = () => qrChz
    deps.claim = vi.fn().mockReturnValue({ key: 'k', preferences: qrChz })
    vi.mocked(deps.select).mockReset().mockResolvedValue({ scan_id: 's', order_id: '1', wb_order_id: 1, requires_honest_sign: true,
      binding_target: null, reprint_recovery: null, qr_asset: null, replayed: false, codes: [],
      printed_codes: [{ id: 'c', cis_code: 'cis', has_label_artifact: false, order_product_id: null }], shortage: 0, order_errors: [] } as FbsScanAutoPrintResult)
    const order: string[] = []
    vi.mocked(deps.print).mockImplementation(async () => { order.push('qr') })
    vi.mocked(deps.printChz).mockImplementation(async () => { order.push('chz') })
    const scanner = createPackingScanController(deps)
    await scanner.scan('barcode')
    expect(order).toEqual(['qr', 'chz'])
    expect(deps.bind).not.toHaveBeenCalled()
    expect(deps.pack).toHaveBeenCalledTimes(1)
  })
  it('M14: reprint only — KIZ scan binds and prints its exact copy', async () => {
    const { deps } = fixture()
    const copy = { printQr: false, printChz: false, reprintChz: true }
    deps.preferences = () => copy
    deps.claim = vi.fn().mockReturnValue({ key: 'k', preferences: copy })
    vi.mocked(deps.select).mockReset().mockResolvedValue({ scan_id: 's', order_id: '1', wb_order_id: 1, requires_honest_sign: false,
      binding_target: lookup, reprint_recovery: { status: 'not_attempted' }, qr_asset: null, replayed: false, codes: [],
      printed_codes: [], shortage: 0, order_errors: [] } as unknown as FbsScanAutoPrintResult)
    const scanner = createPackingScanController(deps)
    await scanner.scan('barcode')
    expect(scanner.view()).toMatchObject({ needsKiz: true })
    await scanner.scan('kiz')
    expect(deps.print).not.toHaveBeenCalled()
    expect(deps.printCopy).toHaveBeenCalledTimes(1)
    expect(deps.pack).toHaveBeenCalledTimes(1)
  })
  it('R20: Escape releases a selection that waits for its KIZ', async () => {
    const { deps, scanner } = fixture()
    await scanner.scan('barcode')
    expect(scanner.canCancel?.()).toBe(true)
    await expect(scanner.cancel?.()).resolves.toBe(true)
    expect(deps.release).toHaveBeenCalledWith(expect.objectContaining({ scan_id: 'scan-1' }))
    expect(scanner.hasPending()).toBe(false)
    expect(deps.print).not.toHaveBeenCalled()
  })
})
