// @vitest-environment jsdom
import { webcrypto } from 'node:crypto'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

// WMS-625 on the production packing path (WMS-631): the order QR goes to WMS Print
// through the durable transport. An older WMS Print (only POST /print) gets
// exactly the production request; a WMS Print with a job journal keeps and
// recovers the job by the same key.

const server = vi.hoisted(() => ({
  started: new Set<string>(),
  claims: [] as string[],
  marks: [] as string[],
}))
vi.mock('./fbsApi', async (original) => ({
  ...(await original<typeof import('./fbsApi')>()),
  claimFbsScanAutoPrintTarget: vi.fn(async (_t: string, _a: unknown, _s: string, scanId: string) => {
    server.claims.push(scanId)
    return { claimed: !server.started.has(scanId), started: server.started.has(scanId) }
  }),
  markFbsScanAutoPrintTargetStarted: vi.fn(async (_t: string, _a: unknown, _s: string, scanId: string) => {
    server.marks.push(scanId)
    server.started.add(scanId)
    return { claimed: false, started: true }
  }),
}))

import { makePackingScanDeps } from './fbsSequentialPacking'
import type { FbsScanAutoPrintResult, FbsWorkspace } from './fbsApi'
import { directQrHash, forgetDirectQrProtocol, qrAttemptStore, type DurableQrAttempt } from '../../utils/durableDirectQr'

const PNG = 'data:image/png;base64,AQID'
const workspace = { supply: { id: 'supply-1', packaging_task_id: 'task-1' }, orders: [], boxes: [] } as unknown as FbsWorkspace
const result = {
  scan_id: 'scan-1', order_id: 'order-1', wb_order_id: 777, requires_honest_sign: false,
  binding_target: null, reprint_recovery: null, qr_asset: null, replayed: false, codes: [],
  printed_codes: [], shortage: 0, order_errors: [],
} as FbsScanAutoPrintResult
const context = { tenantId: 'unknown-tenant', userId: 'unknown-user', supplyId: 'supply-1', orderId: 'order-1', scanId: 'scan-1',
  barcode: 'order:order-1', marketplace: 'wildberries', wbOrderId: 777 }
/** The body production sends to WMS Print for an order QR, plus the order context older programs ignore. */
const productionBody = { imageDataUrl: PNG, idempotencyKey: 'scan-1', widthMm: 58, heightMm: 40, context }

type Program = 'old' | 'modern' | 'off'
let program: Program
let loseNextPost: boolean
let nativeCalls: Array<{ method: string; path: string; body: unknown }>
let jobs: Map<string, Record<string, unknown>>
let rows: Map<string, DurableQrAttempt>
let storeSpies: Array<{ mockRestore: () => void }> = []
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

async function native(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(String(input))
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = typeof init?.body === 'string' ? JSON.parse(init.body) : null
  nativeCalls.push({ method, path: url.pathname, body })
  if (url.hostname !== '127.0.0.1') throw new Error(`unexpected request ${url}`)
  if (program === 'off') throw new TypeError('Failed to fetch')
  if (program === 'old') {
    // v2026.09.30.4/.5: answers only POST /print, keeps the receipt by key.
    if (method === 'POST' && url.pathname === '/print') {
      const receipt = (jobs.get(body.idempotencyKey)?.receipt as string | undefined) ?? `queue-${jobs.size + 1}`
      jobs.set(body.idempotencyKey, { receipt })
      if (loseNextPost) { loseNextPost = false; throw new TypeError('response lost') }
      return json({ receipt })
    }
    return json({}, 404)
  }
  if (url.pathname === '/health') return json({ app: 'WMS Print Direct', protocolVersion: 2 })
  if (method === 'POST' && url.pathname === '/print') {
    const job = jobs.get(body.idempotencyKey) ?? { ...body, protocolVersion: undefined, hash: await directQrHash(body), status: 'accepted', receipt: `queue-${jobs.size + 1}` }
    delete job.protocolVersion
    delete job.imageDataUrl
    jobs.set(body.idempotencyKey, job)
    if (loseNextPost) { loseNextPost = false; throw new TypeError('response lost') }
    return json(job, 202)
  }
  const key = decodeURIComponent(url.pathname.split('/jobs/')[1]?.split('/')[0] ?? '')
  return jobs.has(key) ? json(jobs.get(key)) : json({}, 404)
}

beforeAll(() => {
  Object.defineProperty(globalThis, 'crypto', { value: webcrypto, configurable: true })
})
beforeEach(() => {
  program = 'old'
  loseNextPost = false
  nativeCalls = []
  jobs = new Map()
  rows = new Map()
  server.started.clear()
  server.claims.length = 0
  server.marks.length = 0
  window.localStorage.clear()
  forgetDirectQrProtocol()
  vi.stubGlobal('fetch', vi.fn(native))
  // jsdom has no IndexedDB: the browser record lives in memory, with the same contract.
  storeSpies = [
    vi.spyOn(qrAttemptStore, 'get').mockImplementation(async (key) => structuredClone(rows.get(key))),
    vi.spyOn(qrAttemptStore, 'put').mockImplementation(async (attempt) => { rows.set(attempt.input.idempotencyKey, structuredClone(attempt)) }),
  ]
})
afterEach(() => {
  vi.unstubAllGlobals()
  for (const spy of storeSpies) spy.mockRestore()
})

const deps = () => makePackingScanDeps('token', () => ({}), () => workspace, () => undefined, () => undefined)
const posts = () => nativeCalls.filter((call) => call.method === 'POST' && call.path === '/print')

describe('WMS-625 · older WMS Print v2026.09.30.4/.5 (only POST /print)', () => {
  it('prints the order QR with exactly the production request and marks it started', async () => {
    await deps().print(result, PNG, '58x40', 'scan-1')
    expect(posts()).toHaveLength(1)
    expect(posts()[0].body).toEqual(productionBody)
    expect(server.marks).toEqual(['scan-1'])
  })

  it('without an answer the order is not marked, and the repeated scan posts the same key: one label', async () => {
    loseNextPost = true
    await expect(deps().print(result, PNG, '58x40', 'scan-1')).rejects.toThrow('Нет ответа WMS Print. Запустите программу.')
    expect(server.marks).toEqual([])
    await deps().print(result, PNG, '58x40', 'scan-1')
    expect(posts().map((call) => call.body)).toEqual([productionBody, productionBody])
    expect(jobs.size).toBe(1)
    expect(server.marks).toEqual(['scan-1'])
  })

  it('works without browser storage, as before', async () => {
    vi.mocked(qrAttemptStore.get).mockRejectedValue(new Error('no IndexedDB'))
    vi.mocked(qrAttemptStore.put).mockRejectedValue(new Error('no IndexedDB'))
    await deps().print(result, PNG, '58x40', 'scan-1')
    expect(posts()[0].body).toEqual(productionBody)
  })

  it('an already started order asks the older program nothing', async () => {
    server.started.add('scan-1')
    await deps().print(result, PNG, '58x40', 'scan-1')
    expect(nativeCalls.filter((call) => call.path !== '/health')).toEqual([])
  })

  it('a program that is not running gives the production message', async () => {
    program = 'off'
    await expect(deps().print(result, PNG, '58x40', 'scan-1')).rejects.toThrow('Нет ответа WMS Print. Запустите программу.')
    expect(server.marks).toEqual([])
  })
})

describe('WMS-625 · WMS Print with the job journal (protocol 2)', () => {
  it('saves the exact label with its order before the request and sends it with the order context', async () => {
    program = 'modern'
    await deps().print(result, PNG, '58x40', 'scan-1')
    expect(posts()).toHaveLength(1)
    expect(posts()[0].body).toEqual({ ...productionBody, protocolVersion: 2 })
    expect(rows.get('scan-1')?.input.imageDataUrl).toBe(PNG)
    expect(rows.get('scan-1')?.result?.status).toBe('accepted')
    expect(server.marks).toEqual(['scan-1'])
  })

  it('a lost answer and a reload: the repeated scan finds the same job, no second POST', async () => {
    program = 'modern'
    loseNextPost = true
    await expect(deps().print(result, PNG, '58x40', 'scan-1')).rejects.toThrow('Нет ответа WMS Print')
    expect(server.marks).toEqual([])
    // A reload builds new dependencies; the browser record and the program journal remain.
    await deps().print(result, 'data:image/png;base64,BBBB', '70x120', 'scan-1')
    expect(posts()).toHaveLength(1)
    expect(server.marks).toEqual(['scan-1'])
    expect(rows.get('scan-1')?.input).toMatchObject({ imageDataUrl: PNG, widthMm: 58, heightMm: 40 })
  })

  it('a stopped queue keeps the order unpacked and names it; the retry checks the same job', async () => {
    program = 'modern'
    await deps().print(result, PNG, '58x40', 'scan-1')
    server.started.clear()
    server.marks.length = 0
    jobs.get('scan-1')!.status = 'stopped'
    await expect(deps().print(result, PNG, '58x40', 'scan-1')).rejects.toThrow('очередь остановлена')
    expect(server.marks).toEqual([])
    jobs.get('scan-1')!.status = 'completed'
    await deps().print(result, PNG, '58x40', 'scan-1')
    expect(posts()).toHaveLength(1)
    expect(server.marks).toEqual(['scan-1'])
  })

  it('an order the server marked started is checked in the journal: a canceled job is reported', async () => {
    program = 'modern'
    await deps().print(result, PNG, '58x40', 'scan-1')
    jobs.get('scan-1')!.status = 'canceled'
    await expect(deps().print(result, PNG, '58x40', 'scan-1')).rejects.toThrow('задание отменено')
    expect(posts()).toHaveLength(1)
  })
})
