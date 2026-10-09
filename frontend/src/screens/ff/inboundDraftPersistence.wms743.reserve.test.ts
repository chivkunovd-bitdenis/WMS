import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { InboundLabelAttempt } from './inboundDraftPersistence'

type Persistence = typeof import('./inboundDraftPersistence')

// WMS-743, review of PR 432: when localStorage refuses the record of a label print attempt, the
// attempt must still be remembered, otherwise the next press prints a SECOND tape instead of
// asking the operator (unknown outcome) or repairing the marks (tape already transferred).
// The reserve is the page memory plus sessionStorage; "reload" below drops the page memory by
// loading the module again while both storages keep their content.
const token = `header.${btoa(JSON.stringify({ tenant_id: 'tenant', sub: 'operator' }))}.signature`
const otherUser = `header.${btoa(JSON.stringify({ tenant_id: 'tenant', sub: 'someone-else' }))}.signature`
const paths = Array.from({ length: 5 }, (_, index) =>
  `/operations/inbound-intake-requests/document/boxes/box-${index}/mark-label-printed`)
const printedBefore = Object.fromEntries(paths.map((value) => [value, '2026-10-01T12:00:00Z']))
const attempt = (state: InboundLabelAttempt['state'], rest = paths): InboundLabelAttempt =>
  ({ id: 'attempt-1', printedBefore, paths: rest, state })

function memoryStorage(refusesWrites: () => boolean = () => false) {
  const map = new Map<string, string>()
  return {
    map,
    get length() { return map.size },
    key: (index: number) => [...map.keys()][index] ?? null,
    getItem: (key: string) => map.get(key) ?? null,
    setItem(key: string, value: string) {
      if (refusesWrites()) throw new DOMException('The quota has been exceeded.', 'QuotaExceededError')
      map.set(key, value)
    },
    removeItem: (key: string) => { map.delete(key) },
    clear: () => map.clear(),
  }
}
let localRefuses = true
let sessionRefuses = false
let local: ReturnType<typeof memoryStorage>
let session: ReturnType<typeof memoryStorage>
let persistence: Persistence
beforeEach(async () => {
  vi.restoreAllMocks()
  // Every test starts as a freshly opened tab: the page memory of the module is empty.
  vi.resetModules()
  persistence = await import('./inboundDraftPersistence')
  localRefuses = true
  sessionRefuses = false
  local = memoryStorage(() => localRefuses)
  session = memoryStorage(() => sessionRefuses)
  vi.stubGlobal('localStorage', local)
  vi.stubGlobal('sessionStorage', session)
})
/** A reload of the tab: the module (page memory) starts empty, localStorage and sessionStorage stay. */
async function reload() {
  vi.resetModules()
  return await import('./inboundDraftPersistence')
}
const read = (module: Persistence, who = token, document = 'document') =>
  module.readIntake(who, document).labelAttempt
/** A complete attempt and no attempt both mean: the next press is a new print. */
const unfinished = (value: InboundLabelAttempt | undefined) => value !== undefined && value.state !== 'complete'

describe('WMS-743 reserve of a label print attempt when localStorage refuses the record', () => {
  it('WMS-743 C12: an unknown outcome is read back by the same page although localStorage refused it', () => {
    persistence.saveInboundLabelAttempt(token, 'document', attempt('unknown'))
    expect(local.map.size, 'the record really was refused').toBe(0)
    const back = read(persistence)
    expect(back?.state).toBe('unknown')
    expect(back?.id).toBe('attempt-1')
    expect(back?.paths).toEqual(paths)
    expect(back?.printedBefore).toEqual(printedBefore)
  })

  it('WMS-743 C12: the unfinished attempt is still there after a reload of the page', async () => {
    persistence.saveInboundLabelAttempt(token, 'document', attempt('unknown'))
    persistence.saveInboundLabelAttempt(token, 'document', attempt('transferred', paths.slice(2)))
    const afterReload = await reload()
    const back = read(afterReload)
    expect(back?.state).toBe('transferred')
    expect(back?.paths).toEqual(paths.slice(2))
    expect(back?.printedBefore).toEqual(printedBefore)
  })

  it('WMS-743 C12: the reserve belongs to one user and one document', async () => {
    persistence.saveInboundLabelAttempt(token, 'document', attempt('unknown'))
    const afterReload = await reload()
    expect(read(afterReload, token, 'another-document')).toBeUndefined()
    expect(read(afterReload, otherUser, 'document')).toBeUndefined()
    expect(read(afterReload)?.state).toBe('unknown')
  })

  it('WMS-743 C12: without sessionStorage too, the open page still remembers the attempt and nothing throws', () => {
    sessionRefuses = true
    expect(() => persistence.saveInboundLabelAttempt(token, 'document', attempt('unknown'))).not.toThrow()
    expect(read(persistence)?.state).toBe('unknown')
    vi.stubGlobal('sessionStorage', undefined)
    expect(() => persistence.saveInboundLabelAttempt(token, 'document', attempt('transferred'))).not.toThrow()
    expect(read(persistence)?.state).toBe('transferred')
  })

  it('WMS-743 C13: finishing the attempt updates and clears the reserve, so the old state never returns', async () => {
    persistence.saveInboundLabelAttempt(token, 'document', attempt('unknown'))
    persistence.saveInboundLabelAttempt(token, 'document', attempt('transferred'))
    expect(read(persistence)?.state).toBe('transferred')
    persistence.saveInboundLabelAttempt(token, 'document', attempt('complete', []))
    expect(unfinished(read(persistence)), 'in the open page').toBe(false)
    const afterReload = await reload()
    expect(unfinished(read(afterReload)), 'after a reload').toBe(false)
    expect([...session.map.keys()].some((key) => key.startsWith('wms440:')), 'nothing stale is left to resurrect').toBe(false)
  })

  it('WMS-743 C13: once localStorage accepts the record again, the reserve is cleared', async () => {
    persistence.saveInboundLabelAttempt(token, 'document', attempt('unknown'))
    expect([...session.map.keys()].some((key) => key.startsWith('wms440:'))).toBe(true)
    localRefuses = false
    persistence.saveInboundLabelAttempt(token, 'document', attempt('complete', []))
    expect([...session.map.keys()].some((key) => key.startsWith('wms440:')), 'reserve cleared').toBe(false)
    const afterReload = await reload()
    expect(read(afterReload)?.state).toBe('complete')
    expect(local.map.size).toBe(1)
  })

  it('WMS-743 C13: a newer reserve wins over an older record left in localStorage', async () => {
    localRefuses = false
    persistence.saveInboundLabelAttempt(token, 'document', attempt('unknown'))
    expect(read(persistence)?.state).toBe('unknown')
    localRefuses = true
    persistence.saveInboundLabelAttempt(token, 'document', attempt('transferred', paths.slice(1)))
    const afterReload = await reload()
    expect(read(afterReload)?.state).toBe('transferred')
    expect(read(afterReload)?.paths).toEqual(paths.slice(1))
    afterReload.saveInboundLabelAttempt(token, 'document', attempt('complete', []))
    expect(read(afterReload)?.state, 'a completed attempt must not fall back to the stale unknown record').toBe('complete')
  })
})
