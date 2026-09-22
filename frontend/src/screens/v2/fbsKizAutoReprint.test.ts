import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  FbsKizAutoPrintQueue,
  fbsKizAutoReprintStorageKey,
  loadFbsKizAutoReprintEnabled,
  saveFbsKizAutoReprintEnabled,
  type FbsKizAutoPrintSnapshot,
} from './fbsKizAutoReprint'

const token = (tenant = 'ff-a', user = 'operator-a') =>
  `header.${btoa(JSON.stringify({ tenant_id: tenant, sub: user }))}.signature`

const scan = (attemptId: string, enabled = true): FbsKizAutoPrintSnapshot => ({
  attemptId,
  orderId: 'order-1',
  kiz: `010460000000000121SERIAL\x1d91ABCD\x1d92${'A'.repeat(44)}`,
  enabled,
})

let local = new Map<string, string>()
let session = new Map<string, string>()

beforeEach(() => {
  local = new Map()
  session = new Map()
  vi.stubGlobal('window', {
    localStorage: {
      getItem: (key: string) => local.get(key) ?? null,
      setItem: (key: string, value: string) => { local.set(key, value) },
    },
    sessionStorage: {
      getItem: (key: string) => session.get(key) ?? null,
      setItem: (key: string, value: string) => { session.set(key, value) },
    },
  })
})

describe('WMS-506 · automatic KIZ duplicate after FBS scan', () => {
  it('keeps the preference separate for FF and operator, defaulting to off', () => {
    expect(loadFbsKizAutoReprintEnabled(token(), 'ff-warehouse-1')).toBe(false)
    saveFbsKizAutoReprintEnabled(token(), 'ff-warehouse-1', true)
    expect(loadFbsKizAutoReprintEnabled(token(), 'ff-warehouse-1')).toBe(true)
    expect(loadFbsKizAutoReprintEnabled(token(), 'ff-warehouse-2')).toBe(false)
    expect(loadFbsKizAutoReprintEnabled(token('ff-a', 'operator-b'), 'ff-warehouse-1')).toBe(false)
    expect(loadFbsKizAutoReprintEnabled(token('ff-b'), 'ff-warehouse-1')).toBe(false)
    expect(fbsKizAutoReprintStorageKey(token(), 'ff-warehouse-1'))
      .not.toBe(fbsKizAutoReprintStorageKey(token('ff-a', 'operator-b'), 'ff-warehouse-1'))
  })

  it('does nothing while the checkbox snapshot is off', async () => {
    const print = vi.fn(async () => undefined)
    await expect(new FbsKizAutoPrintQueue().enqueue(scan('off', false), print)).resolves.toBe(false)
    expect(print).not.toHaveBeenCalled()
  })

  it('prints exactly the saved full KIZ once and keeps one explicit copy option at the call site', async () => {
    const print = vi.fn(async () => undefined)
    const queue = new FbsKizAutoPrintQueue()
    await expect(queue.enqueue(scan('success'), print)).resolves.toBe(true)
    expect(print).toHaveBeenCalledTimes(1)
    expect(print).toHaveBeenCalledWith(scan('success').kiz)
  })

  it('does not print a replay of the same successful commit after a refresh', async () => {
    const print = vi.fn(async () => undefined)
    await expect(new FbsKizAutoPrintQueue().enqueue(scan('replayed-commit'), print)).resolves.toBe(true)
    await expect(new FbsKizAutoPrintQueue().enqueue(scan('replayed-commit'), print)).resolves.toBe(false)
    expect(print).toHaveBeenCalledTimes(1)
  })

  it('continues with the next saved scan if launching the first print fails', async () => {
    const queue = new FbsKizAutoPrintQueue()
    const print = vi.fn()
      .mockRejectedValueOnce(new Error('print launch failed'))
      .mockResolvedValueOnce(undefined)
    await expect(queue.enqueue(scan('failed-print'), print)).rejects.toThrow('print launch failed')
    await expect(queue.enqueue(scan('next-scan'), print)).resolves.toBe(true)
    expect(print).toHaveBeenNthCalledWith(1, scan('failed-print').kiz)
    expect(print).toHaveBeenNthCalledWith(2, scan('next-scan').kiz)
  })
})
