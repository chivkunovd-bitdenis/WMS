import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { dispatchDurableQr, directQrHash, type DurableQrAttempt, type DurableQrInput, type QrAttemptStore } from './durableDirectQr'

// WMS-625, cross-review of the port 03.10.2026 (Astra, review-astra-1.md): each finding
// F1–F5 reproduced with the real transport (dispatchDurableQr → printDirectQr's POST and
// queue), the network replaced by models of the two WMS Print journals. These assert the
// required behaviour; before the fix every one of them failed.

const input: DurableQrInput = {
  idempotencyKey: 'review-scan', imageDataUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGP8//8/AwMDEwMYAAAkBgMBXaJOiAAAAABJRU5ErkJggg==', widthMm: 58, heightMm: 40,
  context: { tenantId: 'tenant', userId: 'user', supplyId: 'supply', orderId: 'order', scanId: 'review-scan', barcode: '4601', marketplace: 'wildberries', wbOrderId: 123 },
}
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status })

function memory(failing?: 'read' | 'write') {
  const rows = new Map<string, DurableQrAttempt>()
  const store: QrAttemptStore = {
    get: async (key) => { if (failing === 'read') throw new Error('IndexedDB unavailable'); return structuredClone(rows.get(key)) },
    put: async (attempt) => { if (failing === 'write') throw new Error('IndexedDB unavailable'); rows.set(attempt.input.idempotencyKey, structuredClone(attempt)) },
  }
  return { rows, store }
}

/**
 * v2026.09.30.4 keeps `direct-jobs.json` (key → hash, receipt); the new program keeps
 * jobs-v2, imports the old file at start and (WMS-625 fix) mirrors every job it hands to
 * the queue into the old file before lp, so the older program knows that key.
 */
function wmsPrint() {
  const state = {
    version: 'old' as 'old' | 'modern',
    oldJournal: new Map<string, string | null>(),
    modernJournal: new Map<string, Record<string, unknown>>(),
    queueJobs: 0, loseNext: false, refuse: null as string | null, requests: [] as string[],
  }
  const release4Hash = directQrHash(input, '|58.0x40.0')
  const fetcher = vi.fn<typeof fetch>(async (url, init) => {
    const path = String(url).replace('http://127.0.0.1:17843', '')
    const method = init?.method ?? 'GET'
    state.requests.push(`${method} ${path}`)
    if (method === 'POST' && path === '/print') {
      const body = JSON.parse(String(init?.body)) as DurableQrInput
      let reply: Response
      if (state.version === 'old') {
        if (state.refuse) reply = json({ error: state.refuse }, 409)
        else if (state.oldJournal.has(body.idempotencyKey)) {
          const receipt = state.oldJournal.get(body.idempotencyKey)
          reply = receipt ? json({ receipt }) : json({ error: 'Задание уже передавалось. Проверьте очередь принтера; повтор автоматически не отправлен.' }, 409)
        } else {
          state.queueJobs++
          state.oldJournal.set(body.idempotencyKey, `old-${state.queueJobs}`)
          reply = json({ receipt: `old-${state.queueJobs}` })
        }
      } else {
        let kept = state.modernJournal.get(body.idempotencyKey)
        if (!kept && state.oldJournal.has(body.idempotencyKey)) {
          const receipt = state.oldJournal.get(body.idempotencyKey)
          kept = { idempotencyKey: body.idempotencyKey, hash: await release4Hash, legacy: true, status: receipt ? 'accepted' : 'unknown', ...(receipt ? { receipt } : {}) }
        }
        if (!kept) {
          state.queueJobs++
          kept = { idempotencyKey: body.idempotencyKey, hash: await directQrHash(body), widthMm: body.widthMm, heightMm: body.heightMm, context: body.context, status: 'accepted', receipt: `queue-${state.queueJobs}` }
          state.modernJournal.set(body.idempotencyKey, kept)
          state.oldJournal.set(body.idempotencyKey, kept.receipt as string)
        }
        reply = json(kept, 202)
      }
      if (state.loseNext) { state.loseNext = false; throw new TypeError('response lost') }
      return reply
    }
    if (state.version === 'old' || path === '/health') return json(state.version === 'old' ? {} : { app: 'WMS Print Direct', protocolVersion: 2 }, state.version === 'old' ? 404 : 200)
    const key = decodeURIComponent(path.split('/jobs/')[1]?.split('/')[0] ?? '')
    return state.modernJournal.has(key) ? json(state.modernJournal.get(key)) : json({}, 404)
  })
  vi.stubGlobal('fetch', fetcher)
  return state
}

beforeEach(() => vi.unstubAllGlobals())
afterEach(() => vi.unstubAllGlobals())

describe('WMS-625 review F1–F5: required behaviour', () => {
  it.each(['read', 'write'] as const)('F2: program with a journal and IndexedDB %s failure — the first label is printed', async (failing) => {
    const program = wmsPrint()
    program.version = 'modern'
    await dispatchDurableQr(input, memory(failing).store)
    expect(program.requests).toEqual(['POST /print'])
    expect(program.queueJobs).toBe(1)
  })
  it('F3: older program (no remembered version any more), lost answer — the retry gets the kept receipt', async () => {
    const program = wmsPrint()
    const { store } = memory()
    program.loseNext = true
    await expect(dispatchDurableQr(input, store)).rejects.toThrow('Нет ответа WMS Print')
    await dispatchDurableQr(input, store)
    expect(program.requests).toEqual(['POST /print', 'POST /print'])
    expect(program.queueJobs).toBe(1)
  })
  it('F3: older program refused before the queue — after choosing a printer the retry prints once', async () => {
    const program = wmsPrint()
    const { store } = memory()
    program.refuse = 'В системе не выбран принтер по умолчанию'
    await expect(dispatchDurableQr(input, store)).rejects.toThrow('не выбран принтер')
    program.refuse = null
    await dispatchDurableQr(input, store)
    expect(program.queueJobs).toBe(1)
  })
  it('F1: the new program accepted, the answer was lost, rolled back to the older one — one queue job', async () => {
    const program = wmsPrint()
    const { store } = memory()
    program.version = 'modern'
    program.loseNext = true
    await expect(dispatchDurableQr(input, store)).rejects.toThrow('Нет ответа WMS Print')
    program.version = 'old'
    await dispatchDurableQr(input, store)
    expect(program.queueJobs).toBe(1)
  })
  it('F1: the same with a broken browser storage — still one queue job', async () => {
    const program = wmsPrint()
    const { store } = memory('read')
    program.version = 'modern'
    program.loseNext = true
    await expect(dispatchDurableQr(input, store)).rejects.toThrow('Нет ответа WMS Print')
    program.version = 'old'
    await dispatchDurableQr(input, store)
    expect(program.queueJobs).toBe(1)
  })
  it('F4: the older program accepted, the answer was lost, then updated — the imported receipt completes the order', async () => {
    const program = wmsPrint()
    const { store } = memory()
    program.loseNext = true
    await expect(dispatchDurableQr(input, store)).rejects.toThrow('Нет ответа WMS Print')
    program.version = 'modern'
    await dispatchDurableQr(input, store)
    const before = program.requests.length
    await dispatchDurableQr(input, store)
    expect(program.requests).toHaveLength(before)
    expect(program.queueJobs).toBe(1)
  })
  it('F5: no /health anywhere; the older program gets the POST at once; «started» asks nothing', async () => {
    const program = wmsPrint()
    const { store } = memory()
    await dispatchDurableQr(input, store)
    await dispatchDurableQr({ ...input, idempotencyKey: 'started-elsewhere' }, store, undefined, true)
    expect(program.requests).toEqual(['POST /print'])
  })
})
