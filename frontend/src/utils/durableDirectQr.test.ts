import { describe, expect, it, vi } from 'vitest'
import {
  dispatchDurableQr, prepareDurableQr, restoreDurableQr, directQrHash,
  type DurableQrAttempt, type DurableQrInput, type DurableQrTransport, type NativeQrJob, type QrAttemptStore,
} from './durableDirectQr'
import { createPackingScanController, type PackingScanDeps } from '../screens/v2/fbsSequentialPacking'
import { FbsApiError, type FbsScanAutoPrintResult } from '../screens/v2/fbsApi'

const input: DurableQrInput = {
  idempotencyKey: 'scan-one', imageDataUrl: 'data:image/png;base64,AQID', widthMm: 58, heightMm: 40,
  context: { tenantId: 'tenant', userId: 'user', supplyId: 'supply', orderId: 'order', scanId: 'scan-one', barcode: '4601', marketplace: 'wildberries', wbOrderId: 123 },
}
const hash = await directQrHash(input)
const rawResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const response = (body: unknown, status = 200) => rawResponse(body && typeof body === 'object' && 'status' in body ? { idempotencyKey: input.idempotencyKey, widthMm: input.widthMm, heightMm: input.heightMm, context: input.context, hash, ...body } : body, status)
/** What production sends to WMS Print, plus the order context older programs ignore. */
const productionBody = { imageDataUrl: input.imageDataUrl, idempotencyKey: input.idempotencyKey, widthMm: input.widthMm, heightMm: input.heightMm, context: input.context }

type Health = 'v2' | 'old' | 'none' | 'offline' | 'no-printer'
function fixture(health: Health | 1 | 2 = 'v2') {
  const mode = health === 2 ? 'v2' : health === 1 ? 'old' : health
  const rows = new Map<string, DurableQrAttempt>()
  const store: QrAttemptStore = {
    get: vi.fn(async (key) => structuredClone(rows.get(key))),
    put: vi.fn(async (attempt) => { rows.set(attempt.input.idempotencyKey, structuredClone(attempt)) }),
  }
  const native = vi.fn<typeof fetch>()
  const legacy = vi.fn<DurableQrTransport['legacy']>(async () => undefined)
  const healthAnswer = () => {
    if (mode === 'offline') return Promise.reject(new TypeError('Failed to fetch'))
    if (mode === 'none') return Promise.resolve(rawResponse({}, 404))
    if (mode === 'no-printer') return Promise.resolve(rawResponse({ app: 'WMS Print Direct', error: 'В системе не выбран принтер по умолчанию' }, 503))
    return Promise.resolve(rawResponse(mode === 'v2' ? { app: 'WMS Print Direct', protocolVersion: 2 } : { app: 'WMS Print Direct', printer: 'fixture' }))
  }
  const io: DurableQrTransport = {
    fetch: ((url, options) => String(url).endsWith('/health') ? healthAnswer() : native(url, options)) as typeof fetch,
    legacy, wait: vi.fn(async () => undefined), polls: 3, now: () => Date.now(),
  }
  return { store, rows, io, native, legacy }
}
const posts = (native: ReturnType<typeof fixture>['native']) => native.mock.calls.filter(([, opts]) => opts?.method === 'POST')

describe('WMS-625 durable direct QR protocol 2', () => {
  it('commits the exact artifacts before any native request and preserves them on unavailability', async () => {
    const { store, rows, io, native } = fixture()
    native.mockImplementation(async () => {
      expect(rows.get(input.idempotencyKey)?.input).toEqual(input)
      throw new TypeError('offline')
    })
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('Исходная этикетка сохранена')
    expect(rows.get(input.idempotencyKey)?.input).toEqual(input)
  })
  it('does not contact native if storage cannot commit', async () => {
    const { store, io, native } = fixture()
    vi.mocked(store.put).mockRejectedValue(new Error('disk full'))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('disk full')
    expect(native).not.toHaveBeenCalled()
  })
  it('queries the same native key after lost POST response and never resubmits accepted job', async () => {
    const { store, rows, io, native } = fixture()
    native.mockResolvedValueOnce(response({}, 404)).mockRejectedValueOnce(new Error('response lost'))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('Нет ответа')
    const persisted = structuredClone(rows.get(input.idempotencyKey)!)
    native.mockResolvedValueOnce(response({ idempotencyKey: input.idempotencyKey, status: 'pending', receipt: 'printer-1' }))
    await dispatchDurableQr(persisted.input, store, io)
    expect(posts(native)).toHaveLength(1)
    expect(rows.get(input.idempotencyKey)?.result?.receipt).toBe('printer-1')
  })
  it.each(['lost-response', 'accepted-receipt'])('GET404 after %s cannot issue another POST or overwrite receipt', async (kind) => {
    const { store, rows, io, native } = fixture()
    native.mockResolvedValueOnce(response({}, 404))
    if (kind === 'lost-response') native.mockRejectedValueOnce(new Error('lost'))
    else native.mockResolvedValueOnce(response({ status: 'accepted', receipt: 'original-queue' }))
    if (kind === 'lost-response') await expect(dispatchDurableQr(input, store, io)).rejects.toThrow()
    else await dispatchDurableQr(input, store, io)
    expect(rows.get(input.idempotencyKey)?.dispatchStartedAt).toBeGreaterThan(0)
    native.mockResolvedValueOnce(response({}, 404))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('новая копия не отправлена')
    expect(posts(native)).toHaveLength(1)
    expect(rows.get(input.idempotencyKey)?.acceptedReceipt).toBe(kind === 'accepted-receipt' ? 'original-queue' : undefined)
  })
  it('persists dispatchStarted before native POST; storage failure prevents sending', async () => {
    const { store, io, native } = fixture()
    await prepareDurableQr(input, store)
    native.mockResolvedValueOnce(response({}, 404))
    vi.mocked(store.put).mockRejectedValueOnce(new Error('boundary commit failed'))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('boundary commit failed')
    expect(posts(native)).toHaveLength(0)
  })
  it.each([
    { receipt: {} }, { receipt: '' }, { receipt: 123 }, { hash: 'b'.repeat(64) }, { hash: undefined },
    { context: {} }, { context: undefined }, { widthMm: undefined }, { heightMm: undefined },
    { idempotencyKey: undefined }, { status: 'nonsense' },
  ])('rejects malformed v2 proof without marking accepted: %j', async (override) => {
    const { store, rows, io, native } = fixture()
    native.mockResolvedValueOnce(response({ status: 'accepted', receipt: 'queue-1', ...override }))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow()
    expect(rows.get(input.idempotencyKey)?.result).toBeUndefined()
  })
  it('legacy imported receipt with verified image remains diagnostic, never permission to pack or send', async () => {
    const { store, io, native } = fixture()
    native.mockResolvedValueOnce(response({ legacy: true, context: {}, widthMm: undefined, heightMm: undefined,
      hash: await directQrHash(input, ''), status: 'accepted', receipt: 'old-queue' }))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('старую квитанцию исходной этикетки')
    expect(posts(native)).toHaveLength(0)
  })
  it.each([
    [58, 40, '|58x40', '1b97a75d5f477750aa77ee2cd69a0fff0a53c8e12cd250ad0a7b180e30eb211b'],
    [58, 40, '|58.0x40.0', '140fa7a991b62fee146aa0a2739e800bbc81c650ed49bfa71f508033fd0705d2'],
    [58.5, 40, '|58.5x40.0', 'f23d8b4ed94e637ab5d72d3bc17e9197ca4c92b592a6d4376d32863a9f705f81'],
  ])('matches exact native Python/Swift numeric identity %s x %s (%s)', async (width, height, suffix, expectedHash) => {
    const current = { ...input, widthMm: Number(width), heightMm: Number(height) }
    const { store, io, native } = fixture()
    native.mockResolvedValueOnce(response({ widthMm: current.widthMm, heightMm: current.heightMm,
      hash: String(expectedHash), status: 'accepted', receipt: 'queue-1' }))
    expect(await directQrHash(current, String(suffix))).toBe(expectedHash)
    await dispatchDurableQr(current, store, io)
  })
  it('waits for real queue acceptance after async202 and retains accepted history', async () => {
    const { store, rows, io, native } = fixture()
    native.mockResolvedValueOnce(response({}, 404))
      .mockResolvedValueOnce(response({ status: 'saved' }, 202))
      .mockResolvedValueOnce(response({ status: 'submitting' }))
      .mockResolvedValueOnce(response({ status: 'accepted', receipt: 'printer-2' }))
    await dispatchDurableQr(input, store, io)
    expect(io.wait).toHaveBeenCalledTimes(2)
    expect(JSON.parse(String(native.mock.calls[1][1]?.body))).toEqual({ ...input, protocolVersion: 2 })
    expect(rows.get(input.idempotencyKey)?.result?.receipt).toBe('printer-2')
  })
  it.each(['unknown', 'canceled', 'aborted', 'stopped', 'held'])('retains %s as unresolved despite a receipt and never blindly sends a copy', async (status) => {
    const { store, rows, io, native } = fixture()
    native.mockImplementation(async () => response({ status, receipt: 'printer-1' }))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('Исходная этикетка сохранена')
    expect(rows.get(input.idempotencyKey)?.result?.status).toBe(status)
    expect(native.mock.calls.some(([url]) => String(url).endsWith('/print'))).toBe(false)
  })
  it('names the order, barcode, key and the WMS Print history in an unresolved result', async () => {
    const { store, io, native } = fixture()
    native.mockImplementation(async () => response({ status: 'stopped', receipt: 'printer-1', reason: 'paused' }))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow(
      'WMS Print: очередь остановлена (paused). Заказ WB № 123, штрихкод 4601, задание scan-one. Исходная этикетка сохранена. Повторите этот штрихкод для проверки и восстановления; журнал: http://127.0.0.1:17843.')
  })
  it('retries only a proven pre-submit failure with saved job and original key', async () => {
    const { store, io, native } = fixture()
    native.mockResolvedValueOnce(response({ status: 'failed_before_submit' }))
      .mockResolvedValueOnce(response({ status: 'accepted', receipt: 'printer-1' }))
    await dispatchDurableQr(input, store, io)
    expect(String(native.mock.calls[1][0])).toBe('http://127.0.0.1:17843/jobs/scan-one/retry')
    expect(native.mock.calls.some(([url]) => String(url).endsWith('/print'))).toBe(false)
  })
  it('cannot complete when acceptance result fails to commit; recovery queries existing job', async () => {
    const { store, rows, io, native } = fixture()
    await prepareDurableQr(input, store)
    vi.mocked(store.put).mockRejectedValueOnce(new Error('disk full after receipt'))
    native.mockImplementation(async () => response({ status: 'accepted', receipt: 'printer-1' }))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('disk full after receipt')
    expect(rows.get(input.idempotencyKey)?.result).toBeUndefined()
    await dispatchDurableQr(input, store, io)
    expect(rows.get(input.idempotencyKey)?.result?.receipt).toBe('printer-1')
    expect(native.mock.calls.every(([, opts]) => opts?.method === 'GET')).toBe(true)
  })
  it('keeps sending the first saved label of a key, never a later preload or size', async () => {
    const { store, rows, io, native } = fixture()
    await prepareDurableQr(input, store)
    native.mockResolvedValueOnce(response({}, 404)).mockResolvedValueOnce(response({ status: 'accepted', receipt: 'printer-1' }))
    await dispatchDurableQr({ ...input, imageDataUrl: 'data:image/png;base64,BBBB', widthMm: 100 }, store, io)
    expect(JSON.parse(String(posts(native)[0][1]?.body))).toEqual({ ...input, protocolVersion: 2 })
    expect(rows.get(input.idempotencyKey)?.input).toEqual(input)
  })
  it('rejects a saved attempt of another client, operator or order without overwriting it', async () => {
    const { store, rows, io, native } = fixture()
    await prepareDurableQr(input, store)
    await expect(restoreDurableQr(input.idempotencyKey, { ...input.context, userId: 'other' }, store)).rejects.toThrow('не соответствует')
    await expect(dispatchDurableQr({ ...input, context: { ...input.context, orderId: 'other' } }, store, io)).rejects.toThrow('не соответствует')
    expect(rows.get(input.idempotencyKey)?.input).toEqual(input)
    expect(native).not.toHaveBeenCalled()
  })
  it('the same key resumed by another scanned code (sticker, row) is the same job', async () => {
    const { store, io, native } = fixture()
    await prepareDurableQr(input, store)
    native.mockResolvedValueOnce(response({ status: 'accepted', receipt: 'printer-1' }))
    await dispatchDurableQr({ ...input, context: { ...input.context, barcode: 'order:order' } }, store, io)
    expect(posts(native)).toHaveLength(0)
  })
  it('does not hide canceled job when server already says started; missing native history cannot print', async () => {
    const { store, io, native } = fixture()
    await prepareDurableQr(input, store)
    native.mockResolvedValueOnce(response({ status: 'canceled', receipt: 'printer-1' }))
    await expect(dispatchDurableQr(input, store, io, true)).rejects.toThrow('отменено')
    native.mockResolvedValueOnce(response({}, 404))
    await expect(dispatchDurableQr(input, store, io, true)).rejects.toThrow('новая копия не отправлена')
    expect(native.mock.calls.every(([, opts]) => opts?.method === 'GET')).toBe(true)
  })
  it('server says started and this browser never sent the key: an unknown job is left as it was, nothing printed', async () => {
    const { store, rows, io, native } = fixture()
    native.mockResolvedValueOnce(response({}, 404))
    await dispatchDurableQr(input, store, io, true)
    expect(posts(native)).toHaveLength(0)
    expect(rows.size).toBe(0)
  })
  it('successive identical goods use separate intent keys and both retained images', async () => {
    const { store, rows, io, native } = fixture()
    native.mockImplementation(async (_url, init) => init?.method === 'GET' ? response({}, 404) : (() => { const sent = JSON.parse(String(init?.body)); return response({ idempotencyKey: sent.idempotencyKey, context: sent.context, status: 'accepted', receipt: 'printer-1' }) })())
    await dispatchDurableQr(input, store, io)
    await dispatchDurableQr({ ...input, idempotencyKey: 'scan-two', context: { ...input.context, orderId: 'order-two', scanId: 'scan-two' } }, store, io)
    expect(rows.size).toBe(2)
    expect(posts(native)).toHaveLength(2)
  })
  it('asks /health once a minute, not before every label', async () => {
    const { store, io, native } = fixture()
    const health = vi.spyOn(io, 'fetch')
    native.mockImplementation(async (_url, init) => init?.method === 'GET' ? response({}, 404) : (() => { const sent = JSON.parse(String(init?.body)); return response({ idempotencyKey: sent.idempotencyKey, context: sent.context, status: 'accepted', receipt: 'printer-1' }) })())
    await dispatchDurableQr(input, store, io)
    await dispatchDurableQr({ ...input, idempotencyKey: 'scan-two', context: { ...input.context, orderId: 'order-two', scanId: 'scan-two' } }, store, io)
    expect(health.mock.calls.filter(([url]) => String(url).endsWith('/health'))).toHaveLength(1)
  })
})

describe('WMS-625 older WMS Print (v2026.09.30.4/.5): exactly the production request', () => {
  it.each<Health>(['old', 'none', 'no-printer', 'offline'])('/health %s → one production POST /print with the label only', async (health) => {
    const { store, io, native, legacy } = fixture(health)
    await dispatchDurableQr(input, store, io)
    expect(legacy).toHaveBeenCalledTimes(1)
    expect(legacy).toHaveBeenCalledWith(productionBody)
    expect(native).not.toHaveBeenCalled()
  })
  it('production errors of the older program reach the operator unchanged', async () => {
    const { store, io, legacy } = fixture('no-printer')
    legacy.mockRejectedValueOnce(new Error('В системе не выбран принтер по умолчанию'))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow(/^В системе не выбран принтер по умолчанию$/)
  })
  it('a retry of a lost answer posts the same key and label again (the older program keeps it by key)', async () => {
    const { store, io, legacy } = fixture('old')
    legacy.mockRejectedValueOnce(new Error('Нет ответа WMS Print. Запустите программу.'))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('Нет ответа WMS Print')
    await dispatchDurableQr({ ...input, imageDataUrl: 'data:image/png;base64,BBBB' }, store, io)
    expect(legacy.mock.calls).toEqual([[productionBody], [productionBody]])
  })
  it('a label the older program accepted is not posted again when its order is retried', async () => {
    const { store, io, legacy } = fixture('old')
    await dispatchDurableQr(input, store, io)
    await dispatchDurableQr(input, store, io)
    expect(legacy).toHaveBeenCalledTimes(1)
  })
  it('browser storage failure never stops the older program path', async () => {
    const { store, io, legacy } = fixture('old')
    vi.mocked(store.get).mockRejectedValue(new Error('no IndexedDB'))
    vi.mocked(store.put).mockRejectedValue(new Error('no IndexedDB'))
    await dispatchDurableQr(input, store, io)
    expect(legacy).toHaveBeenCalledWith(productionBody)
  })
  it('server says started: an older program is not asked anything, as before', async () => {
    const { store, io, native, legacy } = fixture('old')
    await dispatchDurableQr(input, store, io, true)
    expect(legacy).not.toHaveBeenCalled()
    expect(native).not.toHaveBeenCalled()
  })
  it('a label the older program accepted is not sent again after the program is updated', async () => {
    const old = fixture('old')
    await dispatchDurableQr(input, old.store, old.io)
    const updated = fixture('v2')
    for (const [key, row] of old.rows) updated.rows.set(key, row)
    await dispatchDurableQr(input, updated.store, updated.io)
    expect(updated.native).not.toHaveBeenCalled()
  })
  it('a label the older program never got is sent once to the updated program', async () => {
    const old = fixture('offline')
    old.legacy.mockRejectedValueOnce(new Error('Нет ответа WMS Print. Запустите программу.'))
    await expect(dispatchDurableQr(input, old.store, old.io)).rejects.toThrow('Нет ответа WMS Print')
    const updated = fixture('v2')
    for (const [key, row] of old.rows) updated.rows.set(key, row)
    updated.native.mockResolvedValueOnce(response({}, 404)).mockResolvedValueOnce(response({ status: 'accepted', receipt: 'printer-1' }))
    await dispatchDurableQr(input, updated.store, updated.io)
    expect(posts(updated.native)).toHaveLength(1)
  })
  it('a job started in the program with a journal is never re-sent to a program without one', async () => {
    const modern = fixture('v2')
    modern.native.mockResolvedValueOnce(response({}, 404)).mockRejectedValueOnce(new Error('lost'))
    await expect(dispatchDurableQr(input, modern.store, modern.io)).rejects.toThrow()
    const old = fixture('old')
    for (const [key, row] of modern.rows) old.rows.set(key, row)
    await expect(dispatchDurableQr(input, old.store, old.io)).rejects.toThrow('новая копия не отправлена')
    expect(old.legacy).not.toHaveBeenCalled()
  })
  it('a WMS Print with a journal reached by the production request keeps the order; the later retry is the same job', async () => {
    const first = fixture('offline')
    let kept: Record<string, unknown> | undefined
    first.legacy.mockImplementationOnce(async (sent) => {
      // The program got the job (with the order context) and the answer was lost.
      kept = { ...sent, imageDataUrl: undefined, hash, status: 'accepted', receipt: 'printer-3' }
      throw new Error('Нет ответа WMS Print. Запустите программу.')
    })
    await expect(dispatchDurableQr(input, first.store, first.io)).rejects.toThrow('Нет ответа WMS Print')
    const later = fixture('v2')
    for (const [key, row] of first.rows) later.rows.set(key, row)
    later.native.mockResolvedValueOnce(rawResponse(kept))
    await dispatchDurableQr(input, later.store, later.io)
    expect(posts(later.native)).toHaveLength(0)
    expect(later.rows.get(input.idempotencyKey)?.result?.receipt).toBe('printer-3')
  })
  it('the program replaced by an older one after /health: its plain receipt completes the label', async () => {
    const { store, rows, io, native } = fixture('v2')
    native.mockResolvedValueOnce(rawResponse({}, 404)).mockResolvedValueOnce(rawResponse({ receipt: 'printer-7' }))
    await dispatchDurableQr(input, store, io)
    expect(rows.get(input.idempotencyKey)?.legacyAcceptedAt).toBeGreaterThan(0)
    expect(io.protocol).toBeUndefined()
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

describe('WMS-625 explicit native reprint recovers original packing intent', () => {
  it('reconciles linked child and persists canceled parent with accepted child before packing original order', async () => {
    const { store, rows, io, native } = fixture()
    const { parent, child } = linkedJobs()
    native.mockResolvedValueOnce(response(parent)).mockResolvedValueOnce(response(child)).mockResolvedValueOnce(response(parent))
    const { controller, pack, complete } = recoveryController(store, io)
    vi.mocked(pack).mockImplementation(async () => {
      expect(rows.get(input.idempotencyKey)?.result).toEqual(parent)
    })
    await controller.scan(input.context.barcode)
    expect(pack).toHaveBeenCalledWith(expect.objectContaining({ order_id: input.context.orderId }), false, input.context.barcode, expect.anything())
    expect(complete).toHaveBeenCalledWith(input.context.barcode)
    expect(controller.hasPending()).toBe(false)
    expect(native.mock.calls.map(([url]) => String(url))).toEqual([
      'http://127.0.0.1:17843/jobs/scan-one',
      'http://127.0.0.1:17843/jobs/explicit-reprint/reconcile',
      'http://127.0.0.1:17843/jobs/scan-one',
    ])
    expect(rows.get(input.idempotencyKey)?.result?.status).toBe('canceled')
  })
  it.each([
    { duplicateRiskAcknowledged: false }, { duplicateRiskAcknowledged: undefined }, { parentKey: 'another-original' }, { hash: 'b'.repeat(64) }, { hash: undefined },
    { widthMm: 70 }, { heightMm: 120 }, { context: { ...input.context, userId: 'other' } },
    { context: { ...input.context, wbOrderId: 999 } }, { context: undefined },
    { idempotencyKey: input.idempotencyKey }, { status: 'unknown' }, { status: 'canceled' },
    { status: 'submitting' }, { status: undefined }, { receipt: '' }, { receipt: undefined },
  ])('does not pack or silently repeat parent when child proof is insufficient: %j', async (override) => {
    const { store, io, native } = fixture()
    const { parent, child } = linkedJobs(override)
    native.mockImplementation(async (url) => response(String(url).includes('/explicit-reprint/') ? child : parent))
    const { controller, pack, complete } = recoveryController(store, io)
    await expect(controller.scan(input.context.barcode)).rejects.toThrow()
    expect(pack).not.toHaveBeenCalled()
    expect(complete).not.toHaveBeenCalled()
    expect(controller.hasPending()).toBe(true)
    expect(native.mock.calls.some(([url]) => String(url).endsWith('/print') || String(url).endsWith('/retry'))).toBe(false)
  })
  it('does not trust an old accepted child after reconciliation says canceled', async () => {
    const { store, io, native } = fixture()
    const { parent, child } = linkedJobs()
    const canceled = { ...child, status: 'canceled' }
    native.mockResolvedValueOnce(response(parent)).mockResolvedValueOnce(response(canceled))
      .mockResolvedValueOnce(response({ ...parent, reprints: [canceled] }))
    const { controller, pack } = recoveryController(store, io)
    await expect(controller.scan(input.context.barcode)).rejects.toThrow('отменено')
    expect(pack).not.toHaveBeenCalled()
  })
  it('does not retry a pre-submit parent while its explicit child remains unknown', async () => {
    const { store, io, native } = fixture()
    const { parent, child } = linkedJobs({ status: 'unknown' })
    parent.status = 'failed_before_submit'
    native.mockImplementation(async (url) => response(String(url).includes('/explicit-reprint/') ? child : parent))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow()
    expect(native.mock.calls.some(([url]) => String(url).endsWith('/retry') || String(url).endsWith('/print'))).toBe(false)
  })
  it('does not pack before updated parent and linked acceptance commit to browser storage', async () => {
    const { store, io, native } = fixture()
    const { parent, child } = linkedJobs()
    const put = store.put
    let writes = 0
    store.put = async (attempt) => { if (++writes === 3) throw new Error('result commit failed'); await put(attempt) }
    native.mockResolvedValueOnce(response(parent)).mockResolvedValueOnce(response(child)).mockResolvedValueOnce(response(parent))
    const { controller, pack } = recoveryController(store, io)
    await expect(controller.scan(input.context.barcode)).rejects.toThrow('result commit failed')
    expect(pack).not.toHaveBeenCalled()
  })
})
