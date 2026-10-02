import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const printer = vi.hoisted(() => ({
  /** Keys WMS Print accepted (and would have sent to paper) — its idempotency store. */
  accepted: new Set<string>(),
  printed: [] as string[],
  calls: [] as string[],
  failOnce: null as string | null,
}))

vi.mock('../../utils/printPreparedQr', () => ({
  dispatchPreparedQrInKiosk: vi.fn(async ({ idempotencyKey }: { idempotencyKey: string }) => {
    printer.calls.push(idempotencyKey)
    if (printer.failOnce === idempotencyKey) {
      printer.failOnce = null
      throw new Error('Нет ответа WMS Print')
    }
    // Same key again: WMS Print returns the stored receipt and prints nothing.
    if (printer.accepted.has(idempotencyKey)) return
    printer.accepted.add(idempotencyKey)
    printer.printed.push(idempotencyKey)
  }),
}))
vi.mock('../../utils/czLabelPng', () => ({
  renderCzLabelPng: vi.fn(async () => 'data:image/png;base64,AAAA'),
}))
vi.mock('./fbsApi', async (original) => ({
  ...(await original<typeof import('./fbsApi')>()),
  claimFbsScanAutoPrintTarget: vi.fn(async () => ({ claimed: true, started: false })),
  markFbsScanAutoPrintTargetStarted: vi.fn(async () => ({ claimed: false, started: true })),
  claimFbsScanAutoPrintReprint: vi.fn(async () => ({ claimed: true, started: false, kiz: 'cis-bound' })),
  releaseFbsScanAutoPrintTargetClaim: vi.fn(async () => undefined),
}))

import {
  createPackingScanController, makePackingScanDeps, packingLabelCopyKeys, type PackingScanDeps,
} from './fbsSequentialPacking'
import { FbsApiError, type FbsScanAutoPrintResult, type FbsWorkspace } from './fbsApi'
import type { FbsScanPrintPreferences } from './fbsScanAutoPrint'

const workspace = { supply: { id: 'supply-1', packaging_task_id: 'task-1' }, orders: [], boxes: [] } as unknown as FbsWorkspace
const poolResult = {
  scan_id: 'scan-1', order_id: 'order-1', wb_order_id: 1, requires_honest_sign: true,
  binding_target: null, reprint_recovery: null, qr_asset: null, replayed: false, codes: [],
  printed_codes: [{ id: 'code-1', cis_code: 'cis-1', has_label_artifact: false, order_product_id: null }],
  shortage: 0, order_errors: [],
} as FbsScanAutoPrintResult

beforeEach(() => {
  printer.accepted.clear()
  printer.printed.length = 0
  printer.calls.length = 0
  printer.failOnce = null
})
afterEach(() => vi.clearAllMocks())

describe('WMS-633 · copies of the KIZ label printed by one scan', () => {
  it('keeps the key of the first copy and gives every further copy its own key', () => {
    expect(packingLabelCopyKeys('scan-1:chz', 1)).toEqual(['scan-1:chz'])
    expect(packingLabelCopyKeys('scan-1:chz', 3)).toEqual(['scan-1:chz', 'scan-1:chz:c2', 'scan-1:chz:c3'])
    expect(packingLabelCopyKeys('scan-1:copy', 0)).toEqual(['scan-1:copy'])
    expect(packingLabelCopyKeys('scan-1:copy', 25)).toHaveLength(10)
  })

  it('N=1 sends one pool KIZ job under the unchanged key', async () => {
    const deps = makePackingScanDeps('token', () => ({}), () => workspace, () => undefined, () => undefined)
    await deps.printChz(poolResult, '58x40', 1)
    expect(printer.calls).toEqual(['scan-1:chz'])
  })

  it('N=3 sends three pool KIZ jobs, each with its own key', async () => {
    const deps = makePackingScanDeps('token', () => ({}), () => workspace, () => undefined, () => undefined)
    await deps.printChz(poolResult, '58x40', 3)
    expect(printer.printed).toEqual(['scan-1:chz', 'scan-1:chz:c2', 'scan-1:chz:c3'])
  })

  it('N=3 exact reprint sends three jobs; a retry after a failed copy prints only the missing ones', async () => {
    const deps = makePackingScanDeps('token', () => ({}), () => workspace, () => undefined, () => undefined)
    printer.failOnce = 'scan-1:copy:c2'
    await expect(deps.printCopy(poolResult, '58x40', 3)).rejects.toThrow('Нет ответа WMS Print')
    expect(printer.printed).toEqual(['scan-1:copy'])
    await deps.printCopy(poolResult, '58x40', 3)
    // Every copy reached paper exactly once.
    expect(printer.printed).toEqual(['scan-1:copy', 'scan-1:copy:c2', 'scan-1:copy:c3'])
  })

  it('a pool KIZ retry after a failed copy also completes only the missing copies', async () => {
    const deps = makePackingScanDeps('token', () => ({}), () => workspace, () => undefined, () => undefined)
    printer.failOnce = 'scan-1:chz:c3'
    await expect(deps.printChz(poolResult, '58x40', 3)).rejects.toThrow()
    await deps.printChz(poolResult, '58x40', 3)
    expect(printer.printed).toEqual(['scan-1:chz', 'scan-1:chz:c2', 'scan-1:chz:c3'])
  })
})

describe('WMS-633 · the scan passes the copy count frozen with its checkboxes', () => {
  const lookup = { order_id: 'order-1', wb_order_id: 1, product: { name: 'Товар', image_url: null, barcode: null, seller_article: null },
    current_kiz: null, needs_confirmation: false, can_bind: true, block_reason: null, requires_honest_sign: true }
  const deps = (preferences: () => FbsScanPrintPreferences, result: FbsScanAutoPrintResult): PackingScanDeps => {
    const snapshot = preferences()
    return {
      preferences,
      select: vi.fn().mockResolvedValue(result),
      lookupSticker: vi.fn().mockRejectedValue(new FbsApiError('sticker_not_found', 'sticker_not_found', null, false, 404)),
      directReprint: vi.fn(), release: vi.fn(), undo: vi.fn(),
      preload: vi.fn().mockResolvedValue('png'), bind: vi.fn().mockResolvedValue(undefined),
      print: vi.fn().mockResolvedValue(undefined), printChz: vi.fn().mockResolvedValue(undefined),
      printCopy: vi.fn().mockResolvedValue(undefined), pack: vi.fn().mockResolvedValue(undefined),
      // The attempt keeps the snapshot of the moment of the scan.
      claim: vi.fn().mockReturnValue({ key: 'k', preferences: { ...snapshot }, labelSizeId: '58x40', explicit: false }),
      saved: () => false, remember: vi.fn(), complete: vi.fn(), changed: vi.fn(),
    }
  }

  it('pool KIZ: QR first, then the KIZ with N=3', async () => {
    const order: string[] = []
    const one = deps(() => ({ printQr: true, printChz: true, reprintChz: false, printChzCopies: 3 }), poolResult)
    vi.mocked(one.print).mockImplementation(async () => { order.push('qr') })
    vi.mocked(one.printChz).mockImplementation(async (_r, _s, copies) => { order.push(`chz×${copies}`) })
    await createPackingScanController(one).scan('barcode')
    expect(order).toEqual(['qr', 'chz×3'])
    expect(one.print).toHaveBeenCalledTimes(1)
  })

  it('old saved preferences without a count print one copy', async () => {
    const one = deps(() => ({ printQr: false, printChz: true, reprintChz: false }), poolResult)
    await createPackingScanController(one).scan('barcode')
    expect(one.printChz).toHaveBeenCalledWith(poolResult, '58x40', 1)
  })

  it('exact reprint keeps the count of its scan even if the field changes before the KIZ scan', async () => {
    let current: FbsScanPrintPreferences = { printQr: false, printChz: false, reprintChz: true, reprintChzCopies: 2 }
    const result = { ...poolResult, requires_honest_sign: false, printed_codes: [], binding_target: lookup,
      reprint_recovery: { status: 'not_attempted' } } as unknown as FbsScanAutoPrintResult
    const one = deps(() => current, result)
    const scanner = createPackingScanController(one)
    await scanner.scan('barcode')
    current = { ...current, reprintChzCopies: 5 }
    await scanner.scan('kiz')
    expect(one.printCopy).toHaveBeenCalledWith(result, '58x40', 2)
  })
})
