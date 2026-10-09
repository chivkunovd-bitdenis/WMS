// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { harness, makeDetail } from '../../test-contracts/inbound684586Harness'
import { intakeStorageKey } from './inboundDraftPersistence'

// WMS-743. One internalBox barcode image measured in real Chrome is 10 218 characters,
// so the HTML of 400 labels is about 4.2 million characters. The renderer is replaced only
// to give jsdom (which has no real canvas) images of that real size; the screen, the print
// utility, the iframe handoff and the attempt record are the production code.
vi.mock('../../utils/renderBarcodeDataUrl', () => ({
  renderBarcodeDataUrl: () => `data:image/png;base64,${'A'.repeat(10_196)}`,
}))

// Same credential format as the shared harness: the record key depends on tenant and user.
const token = `contract.${btoa(JSON.stringify({ tenant_id: 'contract-tenant', sub: 'contract-user' }))}.signature`
const errorText = () => document.querySelector('[data-testid="ff-inbound-doc-error"]')?.textContent ?? ''
const attemptOf = (document = 'A') => {
  const raw = localStorage.getItem(intakeStorageKey(token, document))
  return raw ? (JSON.parse(raw) as { labelAttempt?: Record<string, unknown> }).labelAttempt : undefined
}
const bigDetail = (count: number) => {
  const detail = makeDetail()
  detail.boxes = Array.from({ length: count }, (_, index) => ({
    ...detail.boxes[0]!, id: `A-box-${index + 1}`, box_number: index + 1,
    internal_barcode: `INB-${String(index + 1).padStart(12, '0')}`, label_printed_at: null as never,
  }))
  return detail
}
/** Every value the screen writes into the intake recovery records. */
function captureIntakeWrites(failWith?: DOMException) {
  const writes: string[] = []
  const original = Storage.prototype.setItem
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key: string, value: string) {
    if (key.startsWith('wms440:')) {
      if (failWith) throw failWith
      writes.push(value)
    }
    return original.call(this, key, value)
  })
  return writes
}
const quotaError = () => new DOMException('The quota has been exceeded.', 'QuotaExceededError')

let h: ReturnType<typeof harness>
beforeEach(() => { h = harness() })
afterEach(async () => { await h.dispose(); vi.useRealTimers() })

describe('WMS-743 inbound box labels and the browser storage', () => {
  it('WMS-743 C6: printing 400 box labels stores no HTML or images and leaves a small completed record', async () => {
    h.current = bigDetail(400)
    const writes = captureIntakeWrites()
    await h.render()
    await h.print(true)
    expect(errorText()).toBe('')
    expect(window.__WMS_PRINT_JOB_COUNT__).toBe(1)
    expect(h.markCalls).toHaveLength(400)
    expect(writes.length, 'the attempt is recorded before and after the handoff').toBeGreaterThan(1)
    expect(writes.some((value) => value.includes('data:image') || value.includes('<html'))).toBe(false)
    expect(Math.max(...writes.map((value) => value.length))).toBeLessThan(300_000)
    const finished = attemptOf()!
    expect(Object.keys(finished).sort()).toEqual(['id', 'paths', 'printedBefore', 'state'])
    expect(finished.state).toBe('complete')
    expect(finished.paths).toEqual([])
    expect(finished.printedBefore).toEqual({})
  }, 120_000)

  it('WMS-743 C9: leftover label HTML of earlier documents does not make a 400-label print fail', async () => {
    for (const number of [1, 2, 3]) {
      localStorage.setItem(intakeStorageKey(token, `old-${number}`), JSON.stringify({
        labelAttempt: { id: `old-${number}`, printedBefore: {}, html: 'x'.repeat(1_200_000), paths: [], state: 'complete' },
      }))
    }
    expect(() => localStorage.setItem('probe', 'x'.repeat(1_500_000)), 'the 5 000 000 character quota is in force')
      .toThrow()
    h.current = bigDetail(400)
    await h.render()
    // Without the fix the print never reaches the handoff and the shared helper gives up waiting.
    await h.print(true).catch(() => undefined)
    expect(errorText()).toBe('')
    expect(window.__WMS_PRINT_JOB_COUNT__).toBe(1)
    expect(h.markCalls).toHaveLength(400)
    expect(attemptOf()!.state).toBe('complete')
  }, 120_000)

  it('WMS-743 C7: a storage quota error does not stop printing or marking', async () => {
    captureIntakeWrites(quotaError())
    await h.render()
    // Without the fix the print never reaches the handoff and the shared helper gives up waiting.
    await h.print(true).catch(() => undefined)
    expect(errorText()).toBe('')
    expect(window.__WMS_PRINT_JOB_COUNT__).toBe(1)
    expect(h.markCalls).toHaveLength(3)
  }, 60_000)

  it('WMS-743 C8: an unfinished attempt is restored after reload without printing the tape again', async () => {
    await h.render()
    h.markMode = 'http'
    await h.print(true)
    expect(errorText()).toContain('label mark failed')
    expect(window.__WMS_PRINT_JOB_COUNT__).toBe(1)
    expect(h.markCalls).toHaveLength(1)
    const unfinished = attemptOf()!
    expect(unfinished.state).toBe('transferred')
    expect(unfinished.paths).toHaveLength(3)
    h.markMode = 'ok'
    await h.remount()
    await h.print(true)
    expect(window.__WMS_PRINT_JOB_COUNT__, 'recovery completes the marks only').toBe(1)
    expect(h.markCalls).toHaveLength(4)
    expect(errorText()).toBe('')
    const finished = attemptOf()!
    expect(finished.id).toBe(unfinished.id)
    expect(finished.state).toBe('complete')
  }, 60_000)

  it('WMS-743 C8: an unknown outcome saved by the previous version is honoured, asked once and then compacted', async () => {
    const paths = makeDetail().boxes.map((box) => `/operations/inbound-intake-requests/A/boxes/${box.id}/mark-label-printed`)
    localStorage.setItem(intakeStorageKey(token, 'A'), JSON.stringify({
      labelAttempt: {
        id: 'previous-version', printedBefore: Object.fromEntries(paths.map((path) => [path, null])),
        html: `<html>${'x'.repeat(200_000)}</html>`, paths, state: 'unknown',
      },
    }))
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    // The shared helper expects some print source to exist; this scenario must not print.
    window.__WMS_LAST_PRINT_HTML__ = '<html></html>'
    await h.render()
    await h.print(true)
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(errorText()).toContain('не отправлена повторно')
    expect(window.__WMS_PRINT_JOB_COUNT__).toBe(0)
    expect(h.markCalls).toHaveLength(0)
    const clarified = attemptOf()!
    expect(clarified.id).toBe('previous-version')
    expect(clarified.state).toBe('complete')
    expect(JSON.stringify(clarified).length, 'the old label HTML is dropped').toBeLessThan(1_000)
    // The next confirmation is an explicit reprint.
    await h.print(true)
    expect(window.__WMS_PRINT_JOB_COUNT__).toBe(1)
    expect(h.markCalls).toHaveLength(3)
  }, 60_000)
})
