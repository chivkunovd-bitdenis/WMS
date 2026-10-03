import { describe, expect, it, vi } from 'vitest'
import {
  dispatchDurableQr, prepareDurableQr, restoreDurableQr, directQrHash,
  type DurableQrAttempt, type DurableQrInput, type DurableQrTransport, type NativeQrJob, type QrAttemptStore,
} from './durableDirectQr'
import type { DirectQrAnswer } from './printDirectQr'
import { createPackingScanController, type PackingScanDeps } from '../screens/v2/fbsSequentialPacking'
import { FbsApiError, type FbsScanAutoPrintResult } from '../screens/v2/fbsApi'

const input: DurableQrInput = {
  idempotencyKey: 'scan-one', imageDataUrl: 'data:image/png;base64,AQID', widthMm: 58, heightMm: 40,
  context: { tenantId: 'tenant', userId: 'user', supplyId: 'supply', orderId: 'order', scanId: 'scan-one', barcode: '4601', marketplace: 'wildberries', wbOrderId: 123 },
}
const hash = await directQrHash(input)
/** The hash v2026.09.30.4 (Swift) keeps for this label: whole Doubles with .0. */
const release4Hash = await directQrHash(input, '|58.0x40.0')
const rawResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const job = (body: Record<string, unknown>): Record<string, unknown> => ({
  idempotencyKey: input.idempotencyKey, widthMm: input.widthMm, heightMm: input.heightMm, context: input.context, hash, ...body,
})
const response = (body: Record<string, unknown>, status = 200) => rawResponse(job(body), status)
/** The body every first label sends: the production fields, the order and protocolVersion 2. */
const sent = { ...input, protocolVersion: 2 }
const answer = (result: unknown, status = 200): DirectQrAnswer => ({ ok: status >= 200 && status < 300, status, result })

function fixture() {
  const rows = new Map<string, DurableQrAttempt>()
  const store: QrAttemptStore = {
    get: vi.fn(async (key) => structuredClone(rows.get(key))),
    put: vi.fn(async (attempt) => {
      // As the IndexedDB transaction: another label under the same key is never overwritten.
      const previous = rows.get(attempt.input.idempotencyKey)
      if (previous && JSON.stringify(previous.input) !== JSON.stringify(attempt.input)) throw new Error('transaction aborted')
      rows.set(attempt.input.idempotencyKey, structuredClone(attempt))
    }),
  }
  const order: string[] = []
  const native = vi.fn<typeof fetch>()
  const post = vi.fn<DurableQrTransport['post']>()
  const io: DurableQrTransport = {
    fetch: ((url, options) => { order.push(`${options?.method ?? 'GET'} ${String(url).replace('http://127.0.0.1:17843', '')}`); return native(url, options) }) as typeof fetch,
    post: (body) => { order.push('POST /print'); return post(body) },
    wait: vi.fn(async () => undefined), polls: 3, now: () => Date.now(),
  }
  return { store, rows, io, native, post, order }
}

describe('WMS-625 · the first label is exactly one production POST', () => {
  it('older program: one POST, its receipt completes the label, nothing else is asked (F5)', async () => {
    const { store, rows, io, post, order } = fixture()
    post.mockResolvedValueOnce(answer({ receipt: 'old-1' }))
    await dispatchDurableQr(input, store, io)
    expect(order).toEqual(['POST /print'])
    expect(post).toHaveBeenCalledWith(sent)
    expect(rows.get(input.idempotencyKey)?.legacyAcceptedAt).toBeGreaterThan(0)
  })
  it('the POST starts before any other request and does not wait for /health (F5)', async () => {
    const { store, io, post, native } = fixture()
    let release!: (value: DirectQrAnswer) => void
    post.mockReturnValueOnce(new Promise((resolve) => { release = resolve }))
    const printing = dispatchDurableQr(input, store, io)
    await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(1))
    expect(native).not.toHaveBeenCalled()
    release(answer({ receipt: 'old-1' }))
    await printing
    expect(native).not.toHaveBeenCalled()
  })
  it('program with a journal: one POST, its accepted job completes the label', async () => {
    const { store, rows, io, post, order } = fixture()
    post.mockResolvedValueOnce(answer(job({ status: 'accepted', receipt: 'queue-1' }), 202))
    await dispatchDurableQr(input, store, io)
    expect(order).toEqual(['POST /print'])
    expect(rows.get(input.idempotencyKey)).toMatchObject({ nativeProtocol: 2, acceptedReceipt: 'queue-1' })
  })
  it('waits for real queue acceptance after async 202 and retains accepted history', async () => {
    const { store, rows, io, native, post } = fixture()
    post.mockResolvedValueOnce(answer(job({ status: 'saved' }), 202))
    native.mockResolvedValueOnce(response({ status: 'submitting' })).mockResolvedValueOnce(response({ status: 'accepted', receipt: 'printer-2' }))
    await dispatchDurableQr(input, store, io)
    expect(io.wait).toHaveBeenCalledTimes(2)
    expect(rows.get(input.idempotencyKey)?.result?.receipt).toBe('printer-2')
  })
  it.each(['read', 'write'])('IndexedDB %s failure never stops the label, old program (F2)', async (kind) => {
    const { store, io, post } = fixture()
    if (kind === 'read') vi.mocked(store.get).mockRejectedValue(new Error('IndexedDB unavailable'))
    else vi.mocked(store.put).mockRejectedValue(new Error('IndexedDB unavailable'))
    post.mockResolvedValueOnce(answer({ receipt: 'old-1' }))
    await dispatchDurableQr(input, store, io)
    expect(post).toHaveBeenCalledWith(sent)
  })
  it.each(['read', 'write'])('IndexedDB %s failure never stops the label, program with a journal (F2)', async (kind) => {
    const { store, io, post } = fixture()
    if (kind === 'read') vi.mocked(store.get).mockRejectedValue(new Error('IndexedDB unavailable'))
    else vi.mocked(store.put).mockRejectedValue(new Error('IndexedDB unavailable'))
    post.mockResolvedValueOnce(answer(job({ status: 'accepted', receipt: 'queue-1' }), 202))
    await dispatchDurableQr(input, store, io)
    expect(post).toHaveBeenCalledTimes(1)
  })
  it('the exact label is saved in the browser before the POST when storage works', async () => {
    const { store, rows, io, post } = fixture()
    post.mockImplementationOnce(async () => {
      expect(rows.get(input.idempotencyKey)).toMatchObject({ input, dispatchStartedAt: expect.any(Number) })
      return answer({ receipt: 'old-1' })
    })
    await dispatchDurableQr(input, store, io)
  })
  it('production errors reach the operator unchanged', async () => {
    const { store, io, post } = fixture()
    post.mockResolvedValueOnce(answer({ error: 'В системе не выбран принтер по умолчанию' }, 409))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow(/^В системе не выбран принтер по умолчанию$/)
    post.mockRejectedValueOnce(new Error('Нет ответа WMS Print. Запустите программу.'))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('Нет ответа WMS Print. Запустите программу.')
    post.mockResolvedValueOnce(answer({}))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('Принтер не подтвердил приём этикетки')
  })
})

describe('WMS-625 · a retry of the key is the same job in every program version', () => {
  /** Two journals, as in the programs: v2026.09.30.4 by key, the new one by key, mirrored into the old file. */
  function programs() {
    const oldJournal = new Map<string, string | null>()
    const modernJournal = new Map<string, Record<string, unknown>>()
    let queueJobs = 0
    let version: 'old' | 'modern' | 'off' = 'old'
    let lose = false
    let refuse: string | null = null
    const io = fixture()
    io.post.mockImplementation(async (body) => {
      const { idempotencyKey: key } = body as { idempotencyKey: string }
      if (version === 'off') throw new Error('Нет ответа WMS Print. Запустите программу.')
      let result: DirectQrAnswer
      if (version === 'old') {
        if (refuse) result = answer({ error: refuse }, 409)
        else if (oldJournal.has(key)) {
          const receipt = oldJournal.get(key)
          result = receipt ? answer({ receipt }) : answer({ error: 'Задание уже передавалось. Проверьте очередь принтера; повтор автоматически не отправлен.' }, 409)
        } else { queueJobs++; oldJournal.set(key, `old-${queueJobs}`); result = answer({ receipt: `old-${queueJobs}` }) }
      } else {
        let kept = modernJournal.get(key)
        if (!kept && oldJournal.has(key)) {
          // Imported at start: the receipt and the .4 hash, no image or size.
          kept = { idempotencyKey: key, hash: release4Hash, status: oldJournal.get(key) ? 'accepted' : 'unknown', legacy: true, ...(oldJournal.get(key) ? { receipt: oldJournal.get(key) } : {}) }
        }
        if (!kept) {
          queueJobs++
          kept = job({ idempotencyKey: key, status: 'accepted', receipt: `queue-${queueJobs}` })
          modernJournal.set(key, kept)
          oldJournal.set(key, kept.receipt as string) // the mirror into direct-jobs.json
        }
        result = answer(kept, 202)
      }
      if (lose) { lose = false; throw new Error('Нет ответа WMS Print. Запустите программу.') }
      return result
    })
    io.native.mockImplementation(async (url) => {
      const key = decodeURIComponent(String(url).split('/jobs/')[1]?.split('/')[0] ?? '')
      if (version === 'off') throw new TypeError('Failed to fetch')
      if (version === 'old' || !modernJournal.has(key)) return rawResponse({}, 404)
      return rawResponse(modernJournal.get(key))
    })
    return {
      ...io,
      get version(): 'old' | 'modern' | 'off' { return version },
      set version(value: 'old' | 'modern' | 'off') { version = value },
      loseNext: () => { lose = true },
      refuse: (message: string | null) => { refuse = message },
      queueJobs: () => queueJobs,
    }
  }

  it('older program kept the receipt, the answer was lost: the retry posts the same key and gets it (F3)', async () => {
    const world = programs()
    world.loseNext()
    await expect(dispatchDurableQr(input, world.store, world.io)).rejects.toThrow('Нет ответа WMS Print')
    await dispatchDurableQr(input, world.store, world.io)
    expect(world.post.mock.calls).toEqual([[sent], [sent]])
    expect(world.queueJobs()).toBe(1)
  })
  it('older program refused before the queue (no default printer): after the fix the retry prints once (F3)', async () => {
    const world = programs()
    world.refuse('В системе не выбран принтер по умолчанию')
    await expect(dispatchDurableQr(input, world.store, world.io)).rejects.toThrow('не выбран принтер')
    world.refuse(null)
    await dispatchDurableQr(input, world.store, world.io)
    expect(world.queueJobs()).toBe(1)
  })
  it('program with a journal replaced by the older one, the answer was lost: one queue job (F1)', async () => {
    const world = programs()
    world.version = 'modern'
    world.loseNext()
    await expect(dispatchDurableQr(input, world.store, world.io)).rejects.toThrow('Нет ответа WMS Print')
    world.version = 'old'
    await dispatchDurableQr(input, world.store, world.io)
    expect(world.queueJobs()).toBe(1)
  })
  it('older program accepted, the answer was lost, then updated: the imported receipt completes it (F4)', async () => {
    const world = programs()
    world.loseNext()
    await expect(dispatchDurableQr(input, world.store, world.io)).rejects.toThrow('Нет ответа WMS Print')
    world.version = 'modern'
    await dispatchDurableQr(input, world.store, world.io)
    expect(world.queueJobs()).toBe(1)
    expect(world.rows.get(input.idempotencyKey)?.legacyAcceptedAt).toBeGreaterThan(0)
    // Completed for good: a later retry asks nothing.
    world.post.mockClear()
    await dispatchDurableQr(input, world.store, world.io)
    expect(world.post).not.toHaveBeenCalled()
  })
  it('older program never got it (not running), then updated: printed once by the new program', async () => {
    const world = programs()
    world.version = 'off'
    await expect(dispatchDurableQr(input, world.store, world.io)).rejects.toThrow('Нет ответа WMS Print')
    world.version = 'modern'
    await dispatchDurableQr(input, world.store, world.io)
    expect(world.queueJobs()).toBe(1)
  })
  it('a journal program lost the answer: the retry gets the same job, no second queue job', async () => {
    const world = programs()
    world.version = 'modern'
    world.loseNext()
    await expect(dispatchDurableQr(input, world.store, world.io)).rejects.toThrow('Нет ответа WMS Print')
    await dispatchDurableQr(input, world.store, world.io)
    expect(world.queueJobs()).toBe(1)
  })
  it('without any browser record the retry is still the same job (F2)', async () => {
    const world = programs()
    vi.mocked(world.store.get).mockRejectedValue(new Error('IndexedDB unavailable'))
    vi.mocked(world.store.put).mockRejectedValue(new Error('IndexedDB unavailable'))
    for (const version of ['old', 'modern'] as const) {
      world.version = version
      world.loseNext()
      await expect(dispatchDurableQr({ ...input, idempotencyKey: version }, world.store, world.io)).rejects.toThrow('Нет ответа WMS Print')
      await dispatchDurableQr({ ...input, idempotencyKey: version }, world.store, world.io)
    }
    expect(world.queueJobs()).toBe(2)
  })
  it('accepted by a journal program, the server mark lost: the retry checks the job and never posts again', async () => {
    const world = programs()
    world.version = 'modern'
    await dispatchDurableQr(input, world.store, world.io)
    world.post.mockClear()
    await dispatchDurableQr(input, world.store, world.io)
    world.version = 'old'
    await dispatchDurableQr(input, world.store, world.io)
    world.version = 'off'
    await dispatchDurableQr(input, world.store, world.io)
    expect(world.post).not.toHaveBeenCalled()
    expect(world.queueJobs()).toBe(1)
  })
  it('an imported old entry without a receipt stays an error, as with the production request; nothing is sent', async () => {
    const { store, io, post } = fixture()
    post.mockResolvedValue(answer({ idempotencyKey: input.idempotencyKey, hash: release4Hash, status: 'unknown', legacy: true }, 202))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('не записала результат')
    expect(post).toHaveBeenCalledTimes(1)
  })
  it('an imported old receipt of another label is never taken for this one', async () => {
    const { store, io, post } = fixture()
    post.mockResolvedValue(answer({ idempotencyKey: input.idempotencyKey, hash: 'b'.repeat(64), status: 'accepted', receipt: 'old-9', legacy: true }, 202))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('с другой этикеткой')
  })
})

describe('WMS-625 · the server already marked the label started', () => {
  it.each(['none', 'older'])('browser record %s: nothing is asked of WMS Print, as before (F5)', async (kind) => {
    const { store, rows, io, post, native } = fixture()
    if (kind === 'older') rows.set(input.idempotencyKey, { input, createdAt: 1, dispatchStartedAt: 1 })
    await dispatchDurableQr(input, store, io, true)
    expect(post).not.toHaveBeenCalled()
    expect(native).not.toHaveBeenCalled()
  })
  it('a journal job reports its later queue failure; unknown key or no answer leaves the mark as it was', async () => {
    const { store, rows, io, native, post } = fixture()
    rows.set(input.idempotencyKey, { input, createdAt: 1, dispatchStartedAt: 1, nativeProtocol: 2, acceptedReceipt: 'queue-1' })
    native.mockResolvedValueOnce(response({ status: 'canceled', receipt: 'queue-1' }))
    await expect(dispatchDurableQr(input, store, io, true)).rejects.toThrow('задание отменено')
    native.mockResolvedValueOnce(rawResponse({}, 404))
    await dispatchDurableQr(input, store, io, true)
    native.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await dispatchDurableQr(input, store, io, true)
    expect(post).not.toHaveBeenCalled()
  })
})

describe('WMS-625 · the journal protocol', () => {
  it.each([
    { receipt: {} }, { receipt: '' }, { receipt: 123 }, { hash: 'b'.repeat(64) }, { hash: undefined },
    { widthMm: undefined }, { heightMm: undefined }, { idempotencyKey: undefined }, { status: 'nonsense' }, { context: 'order' },
  ])('rejects malformed proof without marking accepted: %j', async (override) => {
    const { store, rows, io, post } = fixture()
    post.mockResolvedValueOnce(answer(job({ status: 'accepted', receipt: 'queue-1', ...override }), 202))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow()
    expect(rows.get(input.idempotencyKey)?.acceptedReceipt).toBeUndefined()
    expect(rows.get(input.idempotencyKey)?.legacyAcceptedAt).toBeUndefined()
  })
  it.each([{ orderId: 'other' }, { userId: 'other' }, { wbOrderId: 999 }])('rejects the job of another order: %j', async (other) => {
    const { store, io, post } = fixture()
    post.mockResolvedValueOnce(answer(job({ status: 'accepted', receipt: 'queue-1', context: { ...input.context, ...other } }), 202))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('другого задания')
  })
  it.each([{ context: undefined }, { context: {} }])('accepts a job kept without the order (made by the production request): %j', async (override) => {
    const { store, io, post } = fixture()
    post.mockResolvedValueOnce(answer(job({ status: 'accepted', receipt: 'queue-1', ...override }), 202))
    await dispatchDurableQr(input, store, io)
  })
  it.each([
    [58, 40, '|58x40', '1b97a75d5f477750aa77ee2cd69a0fff0a53c8e12cd250ad0a7b180e30eb211b'],
    [58, 40, '|58.0x40.0', '140fa7a991b62fee146aa0a2739e800bbc81c650ed49bfa71f508033fd0705d2'],
    [58.5, 40, '|58.5x40.0', 'f23d8b4ed94e637ab5d72d3bc17e9197ca4c92b592a6d4376d32863a9f705f81'],
  ])('matches exact native Python/Swift numeric identity %s x %s (%s)', async (width, height, suffix, expectedHash) => {
    const current = { ...input, widthMm: Number(width), heightMm: Number(height) }
    const { store, io, post } = fixture()
    post.mockResolvedValueOnce(answer(job({ widthMm: current.widthMm, heightMm: current.heightMm, hash: String(expectedHash), status: 'accepted', receipt: 'queue-1' }), 202))
    expect(await directQrHash(current, String(suffix))).toBe(expectedHash)
    await dispatchDurableQr(current, store, io)
  })
  it.each(['canceled', 'aborted', 'stopped', 'held'])('retains %s as unresolved despite a receipt and never posts a copy', async (status) => {
    const { store, rows, io, native, post } = fixture()
    post.mockResolvedValue(answer(job({ status, receipt: 'printer-1' }), 202))
    native.mockImplementation(async () => response({ status, receipt: 'printer-1' }))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('Исходная этикетка сохранена')
    expect(rows.get(input.idempotencyKey)?.result?.status).toBe(status)
    expect(post).toHaveBeenCalledTimes(1)
  })
  it('an unknown outcome is re-read from the queue, never posted again', async () => {
    const { store, io, native, post } = fixture()
    post.mockResolvedValueOnce(answer(job({ status: 'unknown' }), 202))
    native.mockResolvedValueOnce(response({ status: 'unknown' }))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('результат передачи неизвестен')
    expect(String(native.mock.calls[0][0])).toBe('http://127.0.0.1:17843/jobs/scan-one/reconcile')
    expect(post).toHaveBeenCalledTimes(1)
  })
  it('names the order, barcode, key and the WMS Print history in an unresolved result', async () => {
    const { store, io, post } = fixture()
    post.mockResolvedValueOnce(answer(job({ status: 'stopped', receipt: 'printer-1', reason: 'paused' }), 202))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow(
      'WMS Print: очередь остановлена (paused). Заказ WB № 123, штрихкод 4601, задание scan-one. Исходная этикетка сохранена. Повторите этот штрихкод для проверки и восстановления; журнал: http://127.0.0.1:17843.')
  })
  it('retries only a proven pre-submit failure with the saved job and original key', async () => {
    const { store, io, native, post } = fixture()
    post.mockResolvedValueOnce(answer(job({ status: 'failed_before_submit' }), 202))
    native.mockResolvedValueOnce(response({ status: 'accepted', receipt: 'printer-1' }))
    await dispatchDurableQr(input, store, io)
    expect(String(native.mock.calls[0][0])).toBe('http://127.0.0.1:17843/jobs/scan-one/retry')
    expect(post).toHaveBeenCalledTimes(1)
  })
  it('completes even when the browser cannot record the receipt; a retry asks the program by key (F2)', async () => {
    const { store, rows, io, post } = fixture()
    vi.mocked(store.put).mockRejectedValue(new Error('disk full after receipt'))
    post.mockResolvedValue(answer(job({ status: 'accepted', receipt: 'printer-1' }), 202))
    await dispatchDurableQr(input, store, io)
    expect(rows.size).toBe(0)
    await dispatchDurableQr(input, store, io)
    expect(post).toHaveBeenCalledTimes(2)
  })
  it('keeps sending the first saved label of a key, never a later preload or size', async () => {
    const { store, rows, io, post } = fixture()
    await prepareDurableQr(input, store)
    post.mockResolvedValueOnce(answer({ receipt: 'old-1' }))
    await dispatchDurableQr({ ...input, imageDataUrl: 'data:image/png;base64,BBBB', widthMm: 100 }, store, io)
    expect(post).toHaveBeenCalledWith(sent)
    expect(rows.get(input.idempotencyKey)?.input).toEqual(input)
  })
  it('a saved record of another order under the key is ignored, never a reason to stop (F2)', async () => {
    const { store, rows, io, post } = fixture()
    await prepareDurableQr(input, store)
    await expect(restoreDurableQr(input.idempotencyKey, { ...input.context, userId: 'other' }, store)).rejects.toThrow('не соответствует')
    const other = { ...input, context: { ...input.context, orderId: 'other' } }
    post.mockResolvedValueOnce(answer({ receipt: 'old-1' }))
    await dispatchDurableQr(other, store, io)
    expect(post).toHaveBeenCalledWith({ ...other, protocolVersion: 2 })
    expect(rows.get(input.idempotencyKey)?.input).toEqual(input)
  })
  it('the same key resumed by another scanned code (sticker, row) is the same job', async () => {
    const { store, io, post } = fixture()
    await prepareDurableQr(input, store)
    post.mockResolvedValueOnce(answer(job({ status: 'accepted', receipt: 'printer-1' }), 202))
    await dispatchDurableQr({ ...input, context: { ...input.context, barcode: 'order:order' } }, store, io)
    expect(post).toHaveBeenCalledWith(sent)
  })
  it('successive identical goods use separate intent keys and both retained images', async () => {
    const { store, rows, io, post } = fixture()
    post.mockImplementation(async (body) => {
      const { idempotencyKey, context } = body as DurableQrInput
      return answer(job({ idempotencyKey, context, status: 'accepted', receipt: 'printer-1' }), 202)
    })
    await dispatchDurableQr(input, store, io)
    await dispatchDurableQr({ ...input, idempotencyKey: 'scan-two', context: { ...input.context, orderId: 'order-two', scanId: 'scan-two' } }, store, io)
    expect(rows.size).toBe(2)
    expect(post).toHaveBeenCalledTimes(2)
  })
})

function linkedJobs(childOverrides: Partial<NativeQrJob> = {}) {
  const child: NativeQrJob = {
    idempotencyKey: 'explicit-reprint', parentKey: input.idempotencyKey, duplicateRiskAcknowledged: true, hash,
    widthMm: input.widthMm, heightMm: input.heightMm, context: input.context,
    status: 'accepted', receipt: 'printer-child', ...childOverrides,
  }
  const parent: NativeQrJob = {
    idempotencyKey: input.idempotencyKey, hash, widthMm: input.widthMm,
    heightMm: input.heightMm, context: input.context, status: 'canceled', receipt: 'printer-parent', reprints: [child],
  }
  return { parent, child }
}
/** The production packing controller (WMS-631) with its QR printed by the durable transport. */
function recoveryController(store: QrAttemptStore, io: DurableQrTransport) {
  const result = {
    scan_id: input.idempotencyKey, order_id: input.context.orderId, wb_order_id: input.context.wbOrderId,
    requires_honest_sign: false, binding_target: null, reprint_recovery: null, qr_asset: null, replayed: false,
    codes: [], printed_codes: [], shortage: 0, order_errors: [],
  } as FbsScanAutoPrintResult
  const preferences = { printQr: true, printChz: false, reprintChz: false }
  const deps: PackingScanDeps = {
    preferences: () => preferences,
    select: vi.fn().mockResolvedValue(result),
    lookupSticker: vi.fn().mockRejectedValue(new FbsApiError('sticker_not_found', 'sticker_not_found', null, false, 404)),
    directReprint: vi.fn(), release: vi.fn(), undo: vi.fn(),
    preload: vi.fn().mockResolvedValue(input.imageDataUrl), bind: vi.fn().mockResolvedValue(undefined),
    print: vi.fn(() => dispatchDurableQr(input, store, io)),
    printChz: vi.fn().mockResolvedValue(undefined), printCopy: vi.fn().mockResolvedValue(undefined),
    pack: vi.fn().mockResolvedValue(undefined),
    claim: vi.fn().mockReturnValue({ key: 'original-selection-key', preferences, labelSizeId: '58x40', explicit: false }),
    saved: () => true, remember: vi.fn(), complete: vi.fn(), changed: vi.fn(),
  }
  return { controller: createPackingScanController(deps), pack: deps.pack, complete: deps.complete }
}

describe('WMS-625 · an explicit copy made in WMS Print recovers the original packing intent', () => {
  it('reconciles the linked copy and packs the original order', async () => {
    const { store, rows, io, native, post } = fixture()
    const { parent, child } = linkedJobs()
    post.mockResolvedValueOnce(answer(parent, 202))
    native.mockResolvedValueOnce(rawResponse(child)).mockResolvedValueOnce(rawResponse(parent))
    const { controller, pack, complete } = recoveryController(store, io)
    await controller.scan(input.context.barcode)
    expect(pack).toHaveBeenCalledWith(expect.objectContaining({ order_id: input.context.orderId }), false, input.context.barcode, expect.anything())
    expect(complete).toHaveBeenCalledWith(input.context.barcode)
    expect(controller.hasPending()).toBe(false)
    expect(native.mock.calls.map(([url]) => String(url))).toEqual([
      'http://127.0.0.1:17843/jobs/explicit-reprint/reconcile',
      'http://127.0.0.1:17843/jobs/scan-one',
    ])
    expect(post).toHaveBeenCalledTimes(1)
    expect(rows.get(input.idempotencyKey)?.result?.status).toBe('canceled')
  })
  it.each([
    { duplicateRiskAcknowledged: false }, { duplicateRiskAcknowledged: undefined }, { parentKey: 'another-original' }, { hash: 'b'.repeat(64) }, { hash: undefined },
    { widthMm: 70 }, { heightMm: 120 }, { context: { ...input.context, userId: 'other' } },
    { context: { ...input.context, wbOrderId: 999 } }, { context: undefined },
    { idempotencyKey: input.idempotencyKey }, { status: 'unknown' }, { status: 'canceled' },
    { status: 'submitting' }, { status: undefined }, { receipt: '' }, { receipt: undefined },
  ])('does not pack or silently repeat the parent when the copy proof is insufficient: %j', async (override) => {
    const { store, io, native, post } = fixture()
    const { parent, child } = linkedJobs(override)
    post.mockResolvedValue(answer(parent, 202))
    native.mockImplementation(async (url) => rawResponse(String(url).includes('/explicit-reprint/') ? child : parent))
    const { controller, pack, complete } = recoveryController(store, io)
    await expect(controller.scan(input.context.barcode)).rejects.toThrow()
    expect(pack).not.toHaveBeenCalled()
    expect(complete).not.toHaveBeenCalled()
    expect(controller.hasPending()).toBe(true)
    expect(native.mock.calls.some(([url]) => String(url).endsWith('/retry'))).toBe(false)
  })
  it('does not trust an old accepted copy after reconciliation says canceled', async () => {
    const { store, io, native, post } = fixture()
    const { parent, child } = linkedJobs()
    const canceled = { ...child, status: 'canceled' }
    post.mockResolvedValueOnce(answer(parent, 202))
    native.mockResolvedValueOnce(rawResponse(canceled)).mockResolvedValueOnce(rawResponse({ ...parent, reprints: [canceled] }))
    const { controller, pack } = recoveryController(store, io)
    await expect(controller.scan(input.context.barcode)).rejects.toThrow('отменено')
    expect(pack).not.toHaveBeenCalled()
  })
  it('does not retry a pre-submit parent while its explicit copy remains unknown', async () => {
    const { store, io, native, post } = fixture()
    const { parent, child } = linkedJobs({ status: 'unknown' })
    parent.status = 'failed_before_submit'
    post.mockResolvedValue(answer(parent, 202))
    native.mockImplementation(async (url) => rawResponse(String(url).includes('/explicit-reprint/') ? child : parent))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow()
    expect(native.mock.calls.some(([url]) => String(url).endsWith('/retry'))).toBe(false)
    expect(post).toHaveBeenCalledTimes(1)
  })
})
