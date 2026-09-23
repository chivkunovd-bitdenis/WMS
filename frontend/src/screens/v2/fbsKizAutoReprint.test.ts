import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  FbsKizAutoPrintQueue,
  FbsPrintOutcomeUnknownError,
  fbsKizAutoReprintStorageKey,
  loadFbsKizAutoReprintEnabled,
  saveFbsKizAutoReprintEnabled,
  startClaimedAutomaticPrint,
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
      removeItem: (key: string) => { session.delete(key) },
    },
  })
})

describe('WMS-506 · automatic KIZ duplicate after FBS scan', () => {
  it('keeps the preference separate for FF and operator, defaulting to off', () => {
    expect(loadFbsKizAutoReprintEnabled(token())).toBe(false)
    saveFbsKizAutoReprintEnabled(token(), true)
    expect(loadFbsKizAutoReprintEnabled(token())).toBe(true)
    expect(loadFbsKizAutoReprintEnabled(token('ff-a', 'operator-b'))).toBe(false)
    expect(loadFbsKizAutoReprintEnabled(token('ff-b'))).toBe(false)
    expect(fbsKizAutoReprintStorageKey(token()))
      .not.toBe(fbsKizAutoReprintStorageKey(token('ff-a', 'operator-b')))
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

  it('allows an explicit retry of the same target only when launch failed before print', async () => {
    const queue = new FbsKizAutoPrintQueue()
    const print = vi.fn()
      .mockRejectedValueOnce(new Error('print launch failed'))
      .mockResolvedValueOnce(undefined)
    await expect(queue.enqueue(scan('retry-target'), print)).rejects.toThrow('print launch failed')
    await expect(queue.enqueue(scan('retry-target'), print)).resolves.toBe(true)
    await expect(queue.enqueue(scan('retry-target'), print)).resolves.toBe(false)
    expect(print).toHaveBeenCalledTimes(2)
  })

  it('serializes product, bound-KIZ and direct-KIZ jobs in accepted order', async () => {
    const queue = new FbsKizAutoPrintQueue()
    const trace: string[] = []
    let releaseFirst!: () => void
    const firstGate = new Promise<void>((resolve) => { releaseFirst = resolve })
    const first = queue.enqueue(scan('product-qr'), async () => {
      trace.push('product:start')
      await firstGate
      trace.push('product:end')
    })
    const second = queue.enqueue(scan('bound-kiz'), async () => { trace.push('bound') })
    const third = queue.enqueue(scan('direct-kiz'), async () => { trace.push('direct') })

    await Promise.resolve()
    expect(trace).toEqual(['product:start'])
    releaseFirst()
    await Promise.all([first, second, third])
    expect(trace).toEqual(['product:start', 'product:end', 'bound', 'direct'])
  })

  it('retains a target claim when the physical print outcome is unknown', async () => {
    const queue = new FbsKizAutoPrintQueue()
    const unknown = Object.assign(new Error('acknowledgement lost'), { printOutcomeUnknown: true })
    const print = vi.fn(async () => { throw unknown })
    await expect(queue.enqueue(scan('unknown-outcome'), print)).rejects.toThrow('acknowledgement lost')
    await expect(queue.enqueue(scan('unknown-outcome'), print)).resolves.toBe(false)
    expect(print).toHaveBeenCalledOnce()
  })
})

describe('WMS-514 · durable automatic print target', () => {
  it('does not invoke the browser again after the server recorded a launch', async () => {
    const print = vi.fn(async () => undefined)
    const result = await startClaimedAutomaticPrint('retry', print, {
      claim: async () => ({ claimed: false, started: true }),
      markStarted: async () => ({ claimed: false, started: true }),
      releaseClaim: async () => undefined,
    })
    expect(result).toEqual({ started: true, printedNow: false })
    expect(print).not.toHaveBeenCalled()
  })

  it('releases a proven pre-print failure so the missing target can be retried', async () => {
    const releaseClaim = vi.fn(async () => undefined)
    await expect(startClaimedAutomaticPrint(
      'pre-print-failure',
      async () => { throw new Error('asset unavailable') },
      {
        claim: async () => ({ claimed: true, started: false }),
        markStarted: async () => ({ claimed: false, started: true }),
        releaseClaim,
      },
    )).rejects.toThrow('asset unavailable')
    expect(releaseClaim).toHaveBeenCalledWith('pre-print-failure')
  })

  it('stops a second browser when an earlier claim has an unknown outcome', async () => {
    const print = vi.fn(async () => undefined)
    const error = await startClaimedAutomaticPrint('new-browser', print, {
      claim: async () => ({ claimed: false, started: false }),
      markStarted: async () => ({ claimed: false, started: true }),
      releaseClaim: async () => undefined,
    }).catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(FbsPrintOutcomeUnknownError)
    expect(print).not.toHaveBeenCalled()
  })

  it('keeps the server claim when acknowledgement is lost after print invocation', async () => {
    const releaseClaim = vi.fn(async () => undefined)
    const error = await startClaimedAutomaticPrint(
      'post-print-unknown',
      async () => undefined,
      {
        claim: async () => ({ claimed: true, started: false }),
        markStarted: async () => { throw new Error('network lost') },
        releaseClaim,
      },
    ).catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(FbsPrintOutcomeUnknownError)
    expect(releaseClaim).not.toHaveBeenCalled()
  })
})
