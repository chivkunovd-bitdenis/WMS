import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  intakeStorageKey, readIntake, saveInboundLabelAttempt, saveIntakeTotals, type InboundLabelAttempt,
} from './inboundDraftPersistence'

// WMS-743: the record that guards a label print attempt must stay small and must never
// stop the print. Sizes below come from a measurement in real Chrome (10 218 characters
// for one internalBox barcode image, 4 241 583 characters for the HTML of 400 labels).
const token = `header.${btoa(JSON.stringify({ tenant_id: 'tenant', sub: 'operator' }))}.signature`
const BOXES = 400
const IMAGE = `data:image/png;base64,${'A'.repeat(10_196)}`
const LABELS_HTML = `<!doctype html><html><body>${Array.from({ length: BOXES }, (_, index) =>
  `<section class="label" data-barcode="INB-${index}"><img class="barcode" src="${IMAGE}"></section>`).join('')}</body></html>`
const path = (index: number) =>
  `/operations/inbound-intake-requests/document/boxes/box-${index}/mark-label-printed`
const paths = Array.from({ length: BOXES }, (_, index) => path(index))
const printedBefore = Object.fromEntries(paths.map((value) => [value, null]))
const attempt = (state: InboundLabelAttempt['state'], extra: Record<string, unknown> = {}) =>
  ({ id: 'attempt-1', printedBefore, paths, state, ...extra }) as InboundLabelAttempt

/** A Storage with the same character quota as the browser one (5 000 000 code units). */
function quotaStorage(limit = 5_000_000) {
  const map = new Map<string, string>()
  const used = () => [...map].reduce((sum, [key, value]) => sum + key.length + value.length, 0)
  return {
    map,
    get length() { return map.size },
    key: (index: number) => [...map.keys()][index] ?? null,
    getItem: (key: string) => map.get(key) ?? null,
    setItem(key: string, value: string) {
      const previous = map.has(key) ? key.length + map.get(key)!.length : 0
      if (used() - previous + key.length + value.length > limit) {
        throw new DOMException('The quota has been exceeded.', 'QuotaExceededError')
      }
      map.set(key, value)
    },
    removeItem: (key: string) => { map.delete(key) },
    clear: () => map.clear(),
  }
}
let disk: ReturnType<typeof quotaStorage>
const stored = (document = 'document') => disk.map.get(intakeStorageKey(token, document)) ?? ''
/** Compared as text so that a failure prints a short message, not 400 paths. */
const sameAttempt = (actual: InboundLabelAttempt | undefined, expected: Record<string, unknown>) =>
  JSON.stringify(actual && { id: actual.id, printedBefore: actual.printedBefore, paths: actual.paths, state: actual.state })
    === JSON.stringify(expected)
beforeEach(() => {
  vi.restoreAllMocks()
  disk = quotaStorage()
  vi.stubGlobal('localStorage', disk)
})

describe('WMS-743 label attempt record in localStorage', () => {
  it('WMS-743 C1: the label attempt record never stores label HTML or images, even for a legacy attempt carrying html', () => {
    expect(LABELS_HTML.length).toBeGreaterThan(4_000_000)
    saveInboundLabelAttempt(token, 'document', attempt('unknown', { html: LABELS_HTML }))
    const record = stored()
    expect(record).not.toContain('data:image')
    expect(record).not.toContain('<html')
    expect(record.length).toBeLessThan(300_000)
    expect(Object.keys(readIntake(token, 'document').labelAttempt!).sort())
      .toEqual(['id', 'paths', 'printedBefore', 'state'])
  })

  it('WMS-743 C2: a completed attempt keeps only its identity, not the marks of 400 boxes', () => {
    saveInboundLabelAttempt(token, 'document', attempt('unknown'))
    saveInboundLabelAttempt(token, 'document', attempt('transferred'))
    saveInboundLabelAttempt(token, 'document', attempt('complete'))
    const record = readIntake(token, 'document').labelAttempt!
    expect(record.id).toBe('attempt-1')
    expect(record.state).toBe('complete')
    expect(record.paths).toHaveLength(0)
    expect(Object.keys(record.printedBefore)).toHaveLength(0)
    expect(stored().length).toBeLessThan(2_000)
  })

  it('WMS-743 C3: a storage quota error never reaches the caller', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => { throw new DOMException('The quota has been exceeded.', 'QuotaExceededError') },
    })
    expect(() => saveInboundLabelAttempt(token, 'document', attempt('unknown'))).not.toThrow()
    expect(() => saveInboundLabelAttempt(token, 'document', attempt('transferred'))).not.toThrow()
    expect(() => saveInboundLabelAttempt(token, 'document', attempt('complete'))).not.toThrow()
  })

  it('WMS-743 C4: the restoration data of an unfinished attempt survives the round trip', () => {
    saveInboundLabelAttempt(token, 'document', attempt('unknown'))
    expect(sameAttempt(readIntake(token, 'document').labelAttempt, {
      id: 'attempt-1', printedBefore, paths, state: 'unknown',
    })).toBe(true)
    const rest = paths.slice(250)
    saveInboundLabelAttempt(token, 'document', { ...attempt('transferred'), paths: rest })
    expect(sameAttempt(readIntake(token, 'document').labelAttempt, {
      id: 'attempt-1', printedBefore, paths: rest, state: 'transferred',
    })).toBe(true)
  })

  it('WMS-743 C5: on a quota error stale label HTML of other documents is removed and the write is retried', () => {
    for (const document of ['old-1', 'old-2', 'old-3', 'old-4']) {
      disk.setItem(intakeStorageKey(token, document), JSON.stringify({
        labelAttempt: { id: `legacy-${document}`, printedBefore: {}, html: 'x'.repeat(1_240_000), paths: [], state: 'complete' },
      }))
    }
    saveIntakeTotals(token, 'old-4', { line: '2' })
    const room = 5_000_000 - [...disk.map].reduce((sum, [key, value]) => sum + key.length + value.length, 0)
    expect(room, 'storage is nearly full before the save').toBeLessThan(100_000)

    saveInboundLabelAttempt(token, 'document', attempt('unknown'))

    expect(sameAttempt(readIntake(token, 'document').labelAttempt, {
      id: 'attempt-1', printedBefore, paths, state: 'unknown',
    })).toBe(true)
    for (const document of ['old-1', 'old-2', 'old-3', 'old-4']) {
      const record = JSON.parse(stored(document)) as { labelAttempt: Record<string, unknown>; totals?: unknown }
      expect(record.labelAttempt.html, document).toBeUndefined()
      expect(record.labelAttempt.id, `${document} keeps its attempt identity`).toBe(`legacy-${document}`)
    }
    expect(JSON.parse(stored('old-4')).totals).toEqual({ line: '2' })
  })

  it('WMS-743 C5: records of other applications are never touched while freeing space', () => {
    disk.setItem('unrelated', 'x'.repeat(4_960_000))
    expect(() => saveInboundLabelAttempt(token, 'document', attempt('unknown'))).not.toThrow()
    expect(disk.map.get('unrelated')).toBe('x'.repeat(4_960_000))
  })
})
