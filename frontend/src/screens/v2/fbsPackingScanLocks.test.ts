// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { createPackingScanLocks } from './fbsPackingScanLocks'
import { makePackingScanDeps } from './fbsSequentialPacking'
import { readPendingAttempts } from './fbsScanAutoPrint'
import type { FbsScanAutoPrintResult, FbsWorkspace } from './fbsApi'

/** Models independently owned document lifetimes over a shared Web Locks manager. */
function browserLocks() {
  const held = new Map<string, string>()
  const tails = new Map<string, Promise<unknown>>()
  const document = (tab: string) => ({
    request: (name: string, options: unknown, callback?: (lock: Lock | null) => Promise<unknown>) => {
      const action = (typeof options === 'function' ? options : callback) as (lock: Lock | null) => Promise<unknown>
      if (typeof options === 'object' && (options as { ifAvailable?: boolean }).ifAvailable) {
        if (held.has(name)) return Promise.resolve(action(null))
        held.set(name, tab)
        return Promise.resolve(action({ name, mode: 'exclusive' })).finally(() => { if (held.get(name) === tab) held.delete(name) })
      }
      const next = (tails.get(name) ?? Promise.resolve()).then(async () => {
        held.set(name, tab)
        try { return await action({ name, mode: 'exclusive' }) }
        finally { held.delete(name) }
      })
      tails.set(name, next.catch(() => undefined))
      return next
    },
  }) as unknown as LockManager
  const close = (tab: string) => { for (const [name, owner] of held) if (owner === tab) held.delete(name) }
  return { document, close }
}
function session() {
  const rows = new Map<string, string>()
  return { get length() { return rows.size }, key: (index: number) => Array.from(rows.keys())[index] ?? null,
    clear: () => rows.clear(), removeItem: (key: string) => { rows.delete(key) },
    getItem: (key: string) => rows.get(key) ?? null, setItem: (key: string, value: string) => { rows.set(key, value) } } as Storage
}
const workspace = { supply: { id: 'supply', packaging_task_id: 'task' }, orders: [], boxes: [] } as unknown as FbsWorkspace
beforeEach(() => window.localStorage.clear())

describe('WMS-625 independent tab scans and closed tab recovery', () => {
  it('cloned active tab gets another owner; reload after closure recovers original owner', async () => {
    const browser = browserLocks(), savedSession = session()
    const a = createPackingScanLocks(browser.document('A'), savedSession, () => 'owner-A')
    expect(await a.owner()).toBe('owner-A')
    const b = createPackingScanLocks(browser.document('B'), savedSession, () => 'owner-B')
    expect(await b.owner()).toBe('owner-B')
    expect(await b.active('owner-A')).toBe(true)
    browser.close('A')
    const resumedSession = session(); resumedSession.setItem('wms:fbs:packing-owner', 'owner-A')
    const resumed = createPackingScanLocks(browser.document('C'), resumedSession, () => 'must-not-use')
    expect(await resumed.owner()).toBe('owner-A')
  })
  it('two active owners scanning identical items keep separate keys; completing one preserves sibling; closed owner recovers exact key and order', async () => {
    const browser = browserLocks()
    const a = createPackingScanLocks(browser.document('A'), session(), () => 'owner-A')
    const b = createPackingScanLocks(browser.document('B'), session(), () => 'owner-B')
    const make = (locks: typeof a) => makePackingScanDeps('token', () => ({}), () => workspace,
      () => undefined, () => undefined, () => true, () => null, () => undefined, () => undefined, () => locks)
    const da = make(a), db = make(b)
    let ka = '', kb = ''
    await Promise.all([
      da.exclusive!(async () => { ka = await da.claim('same'); await da.remember('same', { scan_id: 'scan-A', order_id: 'order-A' } as FbsScanAutoPrintResult) }),
      db.exclusive!(async () => { kb = await db.claim('same'); await db.remember('same', { scan_id: 'scan-B', order_id: 'order-B' } as FbsScanAutoPrintResult) }),
    ])
    expect(ka).not.toBe(kb)
    expect(readPendingAttempts('token', 'supply:sequential-packing')).toHaveLength(2)
    await db.exclusive!(async () => { await db.complete('same') })
    expect(readPendingAttempts('token', 'supply:sequential-packing')).toMatchObject([{ idempotencyKey: ka, scanId: 'scan-A', orderId: 'order-A' }])
    browser.close('A')
    const c = createPackingScanLocks(browser.document('C'), session(), () => 'owner-C'), dc = make(c)
    await dc.exclusive!(async () => {
      expect(await dc.claim('same')).toBe(ka)
      await dc.remember('same', { scan_id: 'scan-A', order_id: 'order-A' } as FbsScanAutoPrintResult)
    })
    expect(readPendingAttempts('token', 'supply:sequential-packing')[0]).toMatchObject({ ownerId: 'owner-C', idempotencyKey: ka, orderId: 'order-A' })
  })
  it('whole flow lock prevents another selection while initial selection/print/pack is active', async () => {
    const browser = browserLocks(), a = createPackingScanLocks(browser.document('A'), session(), () => 'A'), b = createPackingScanLocks(browser.document('B'), session(), () => 'B')
    let release!: () => void
    const waiting = new Promise<void>((resolve) => { release = resolve })
    const steps: string[] = []
    const first = a.run('tenant:user:supply', async () => { steps.push('select-A'); await waiting; steps.push('pack-A') })
    await new Promise((resolve) => setTimeout(resolve, 0))
    const second = b.run('tenant:user:supply', async () => { steps.push('select-B') })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(steps).toEqual(['select-A'])
    release(); await Promise.all([first, second])
    expect(steps).toEqual(['select-A', 'pack-A', 'select-B'])
  })
})
