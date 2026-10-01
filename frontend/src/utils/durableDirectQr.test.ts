import { describe, expect, it, vi } from 'vitest'
import { dispatchDurableQr, prepareDurableQr, restoreDurableQr, type DurableQrAttempt, type DurableQrInput, type QrAttemptStore, type NativeQrJob, directQrHash } from './durableDirectQr'

import { createPackingScanController } from '../screens/v2/fbsSequentialPacking'
import type { FbsScanAutoPrintResult } from '../screens/v2/fbsApi'

const input: DurableQrInput = {
  idempotencyKey: 'scan-one', imageDataUrl: 'data:image/png;base64,AQID', widthMm: 58, heightMm: 40,
  context: { tenantId: 'tenant', userId: 'user', supplyId: 'supply', orderId: 'order', scanId: 'scan-one', barcode: '4601', marketplace: 'wildberries', wbOrderId: 123 },
}
const hash = await directQrHash(input)
const rawResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const response = (body: unknown, status = 200) => rawResponse(body && typeof body === 'object' && 'status' in body ? { idempotencyKey: input.idempotencyKey, widthMm: input.widthMm, heightMm: input.heightMm, context: input.context, hash, ...body } : body, status)
function fixture(protocol: 1 | 2 = 2) {
  const rows = new Map<string, DurableQrAttempt>()
  const store: QrAttemptStore = {
    get: vi.fn(async (key) => structuredClone(rows.get(key))),
    put: vi.fn(async (attempt) => { rows.set(attempt.input.idempotencyKey, structuredClone(attempt)) }),
  }
  const native = vi.fn<typeof fetch>()
  const io = { fetch: ((url, options) => String(url).endsWith('/health') ? Promise.resolve(rawResponse(protocol === 2 ? { app: 'WMS Print Direct', protocolVersion: 2 } : { app: 'WMS Print Direct', printer: 'fixture' })) : native(url, options)) as typeof fetch, wait: vi.fn(async () => undefined), polls: 3 }
  return { store, rows, io, native }
}

describe('durable direct QR protocol', () => {
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
    expect(native.mock.calls.filter(([, opts]) => opts?.method === 'POST')).toHaveLength(1)
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
    expect(native.mock.calls.filter(([, opts]) => opts?.method === 'POST')).toHaveLength(1)
    expect(rows.get(input.idempotencyKey)?.acceptedReceipt).toBe(kind === 'accepted-receipt' ? 'original-queue' : undefined)
  })
  it('persists dispatchStarted before native POST; storage failure prevents sending', async () => {
    const { store, io, native } = fixture()
    await prepareDurableQr(input, store)
    native.mockResolvedValueOnce(response({}, 404))
    vi.mocked(store.put).mockRejectedValueOnce(new Error('boundary commit failed'))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('boundary commit failed')
    expect(native.mock.calls.filter(([, opts]) => opts?.method === 'POST')).toHaveLength(0)
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
    expect(native.mock.calls.filter(([, opts]) => opts?.method === 'POST')).toHaveLength(0)
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
  it('rejects changed dimensions, image, or user context without overwriting original', async () => {
    const { store, rows, io, native } = fixture()
    await prepareDurableQr(input, store)
    await expect(dispatchDurableQr({ ...input, widthMm: 100 }, store, io)).rejects.toThrow('размер')
    await expect(dispatchDurableQr({ ...input, imageDataUrl: 'other' }, store, io)).rejects.toThrow('Изображение')
    await expect(restoreDurableQr(input.idempotencyKey, { ...input.context, userId: 'other' }, store)).rejects.toThrow('не соответствует')
    expect(rows.get(input.idempotencyKey)?.input).toEqual(input)
    expect(native).not.toHaveBeenCalled()
  })
  it('does not hide canceled job when server already says started; missing native history cannot print', async () => {
    const { store, io, native } = fixture()
    native.mockResolvedValueOnce(response({ status: 'canceled', receipt: 'printer-1' }))
    await expect(dispatchDurableQr(input, store, io, true)).rejects.toThrow('отменено')
    native.mockResolvedValueOnce(response({}, 404))
    await expect(dispatchDurableQr(input, store, io, true)).rejects.toThrow('новая копия не отправлена')
    expect(native.mock.calls.every(([, opts]) => opts?.method === 'GET')).toBe(true)
  })
  it('supports legacy native receipts with retained exact artifact and no invented paper claim', async () => {
    const { store, rows, io, native } = fixture(1)
    native.mockResolvedValueOnce(response({ receipt: 'legacy-printer-1' }))
    await dispatchDurableQr(input, store, io)
    expect(rows.get(input.idempotencyKey)?.result).toEqual({ receipt: 'legacy-printer-1' })
    await dispatchDurableQr(input, store, io, true)
    expect(native).toHaveBeenCalledTimes(1)
  })
  it('successive identical goods use separate intent keys and both retained images', async () => {
    const { store, rows, io, native } = fixture()
    native.mockImplementation(async (_url, init) => init?.method === 'GET' ? response({}, 404) : (() => { const sent = JSON.parse(String(init?.body)); return response({ idempotencyKey: sent.idempotencyKey, context: sent.context, status: 'accepted', receipt: 'printer-1' }) })())
    await dispatchDurableQr(input, store, io)
    await dispatchDurableQr({ ...input, idempotencyKey: 'scan-two', context: { ...input.context, orderId: 'order-two', scanId: 'scan-two' } }, store, io)
    expect(rows.size).toBe(2)
    expect(native.mock.calls.filter(([, opts]) => opts?.method === 'POST')).toHaveLength(2)
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
function recoveryController(store: QrAttemptStore, io: ReturnType<typeof fixture>['io']) {
  const pack = vi.fn(async () => undefined)
  const complete = vi.fn()
  const select = vi.fn(async () => ({ scan_id: input.idempotencyKey, order_id: input.context.orderId,
    wb_order_id: input.context.wbOrderId, requires_honest_sign: false } as FbsScanAutoPrintResult))
  const controller = createPackingScanController({ select, preload: async () => input.imageDataUrl,
    print: () => dispatchDurableQr(input, store, io, true), pack,
    bind: async () => undefined, claim: () => 'original-selection-key', saved: () => true,
    remember: () => undefined, complete, changed: () => undefined,
  })
  return { controller, pack, complete, select }
}

describe('explicit native reprint recovers original packing intent', () => {
  it('reconciles linked child and persists canceled parent with accepted child before packing original order', async () => {
    const { store, rows, io, native } = fixture()
    const { parent, child } = linkedJobs()
    native.mockResolvedValueOnce(response(parent)).mockResolvedValueOnce(response(child)).mockResolvedValueOnce(response(parent))
    const { controller, pack, complete } = recoveryController(store, io)
    pack.mockImplementation(async () => {
      expect(rows.get(input.idempotencyKey)?.result).toEqual(parent)
    })
    await controller.scan(input.context.barcode)
    expect(pack).toHaveBeenCalledWith(expect.objectContaining({ order_id: input.context.orderId }))
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
