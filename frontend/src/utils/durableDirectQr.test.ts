import { describe, expect, it, vi } from 'vitest'
import { dispatchDurableQr, prepareDurableQr, restoreDurableQr, type DurableQrAttempt, type DurableQrInput, type QrAttemptStore, type NativeQrJob } from './durableDirectQr'

import { createPackingScanController } from '../screens/v2/fbsSequentialPacking'
import type { FbsScanAutoPrintResult } from '../screens/v2/fbsApi'

const input: DurableQrInput = {
  idempotencyKey: 'scan-one', imageDataUrl: 'data:image/png;base64,EXACT', widthMm: 58, heightMm: 40,
  context: { tenantId: 'tenant', userId: 'user', supplyId: 'supply', orderId: 'order', scanId: 'scan-one', barcode: '4601', marketplace: 'wildberries', wbOrderId: 123 },
}
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
function fixture() {
  const rows = new Map<string, DurableQrAttempt>()
  const store: QrAttemptStore = {
    get: vi.fn(async (key) => structuredClone(rows.get(key))),
    put: vi.fn(async (attempt) => { rows.set(attempt.input.idempotencyKey, structuredClone(attempt)) }),
  }
  const io = { fetch: vi.fn<typeof fetch>(), wait: vi.fn(async () => undefined), polls: 3 }
  return { store, rows, io }
}

describe('durable direct QR protocol', () => {
  it('commits the exact artifacts before any native request and preserves them on unavailability', async () => {
    const { store, rows, io } = fixture()
    io.fetch.mockImplementation(async () => {
      expect(rows.get(input.idempotencyKey)?.input).toEqual(input)
      throw new TypeError('offline')
    })
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('Исходная этикетка сохранена')
    expect(rows.get(input.idempotencyKey)?.input).toEqual(input)
  })
  it('does not contact native if storage cannot commit', async () => {
    const { store, io } = fixture()
    vi.mocked(store.put).mockRejectedValue(new Error('disk full'))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('disk full')
    expect(io.fetch).not.toHaveBeenCalled()
  })
  it('queries the same native key after lost POST response and never resubmits accepted job', async () => {
    const { store, rows, io } = fixture()
    io.fetch.mockResolvedValueOnce(response({}, 404)).mockRejectedValueOnce(new Error('response lost'))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('Нет ответа')
    const persisted = structuredClone(rows.get(input.idempotencyKey)!)
    io.fetch.mockResolvedValueOnce(response({ idempotencyKey: input.idempotencyKey, status: 'pending', receipt: 'printer-1' }))
    await dispatchDurableQr(persisted.input, store, io)
    expect(io.fetch.mock.calls.filter(([, opts]) => opts?.method === 'POST')).toHaveLength(1)
    expect(rows.get(input.idempotencyKey)?.result?.receipt).toBe('printer-1')
  })
  it('waits for real queue acceptance after async202 and retains accepted history', async () => {
    const { store, rows, io } = fixture()
    io.fetch.mockResolvedValueOnce(response({}, 404))
      .mockResolvedValueOnce(response({ status: 'saved' }, 202))
      .mockResolvedValueOnce(response({ status: 'submitting' }))
      .mockResolvedValueOnce(response({ status: 'accepted', receipt: 'printer-2' }))
    await dispatchDurableQr(input, store, io)
    expect(io.wait).toHaveBeenCalledTimes(2)
    expect(JSON.parse(String(io.fetch.mock.calls[1][1]?.body))).toEqual({ ...input, protocolVersion: 2 })
    expect(rows.get(input.idempotencyKey)?.result?.receipt).toBe('printer-2')
  })
  it.each(['unknown', 'canceled', 'aborted', 'stopped', 'held'])('retains %s as unresolved despite a receipt and never blindly sends a copy', async (status) => {
    const { store, rows, io } = fixture()
    io.fetch.mockImplementation(async () => response({ status, receipt: 'printer-1' }))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('Исходная этикетка сохранена')
    expect(rows.get(input.idempotencyKey)?.result?.status).toBe(status)
    expect(io.fetch.mock.calls.some(([url]) => String(url).endsWith('/print'))).toBe(false)
  })
  it('retries only a proven pre-submit failure with saved job and original key', async () => {
    const { store, io } = fixture()
    io.fetch.mockResolvedValueOnce(response({ status: 'failed_before_submit' }))
      .mockResolvedValueOnce(response({ status: 'accepted', receipt: 'printer-1' }))
    await dispatchDurableQr(input, store, io)
    expect(String(io.fetch.mock.calls[1][0])).toBe('http://127.0.0.1:17843/jobs/scan-one/retry')
    expect(io.fetch.mock.calls.some(([url]) => String(url).endsWith('/print'))).toBe(false)
  })
  it('cannot complete when acceptance result fails to commit; recovery queries existing job', async () => {
    const { store, rows, io } = fixture()
    await prepareDurableQr(input, store)
    vi.mocked(store.put).mockRejectedValueOnce(new Error('disk full after receipt'))
    io.fetch.mockImplementation(async () => response({ status: 'accepted', receipt: 'printer-1' }))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow('disk full after receipt')
    expect(rows.get(input.idempotencyKey)?.result).toBeUndefined()
    await dispatchDurableQr(input, store, io)
    expect(rows.get(input.idempotencyKey)?.result?.receipt).toBe('printer-1')
    expect(io.fetch.mock.calls.every(([, opts]) => opts?.method === 'GET')).toBe(true)
  })
  it('rejects changed dimensions, image, or user context without overwriting original', async () => {
    const { store, rows, io } = fixture()
    await prepareDurableQr(input, store)
    await expect(dispatchDurableQr({ ...input, widthMm: 100 }, store, io)).rejects.toThrow('размер')
    await expect(dispatchDurableQr({ ...input, imageDataUrl: 'other' }, store, io)).rejects.toThrow('Изображение')
    await expect(restoreDurableQr(input.idempotencyKey, { ...input.context, userId: 'other' }, store)).rejects.toThrow('не соответствует')
    expect(rows.get(input.idempotencyKey)?.input).toEqual(input)
    expect(io.fetch).not.toHaveBeenCalled()
  })
  it('does not hide canceled job when server already says started; missing native history cannot print', async () => {
    const { store, io } = fixture()
    io.fetch.mockResolvedValueOnce(response({ status: 'canceled', receipt: 'printer-1' }))
    await expect(dispatchDurableQr(input, store, io, true)).rejects.toThrow('отменено')
    io.fetch.mockResolvedValueOnce(response({}, 404))
    await expect(dispatchDurableQr(input, store, io, true)).rejects.toThrow('новая копия не отправлена')
    expect(io.fetch.mock.calls.every(([, opts]) => opts?.method === 'GET')).toBe(true)
  })
  it('supports legacy native receipts with retained exact artifact and no invented paper claim', async () => {
    const { store, rows, io } = fixture()
    io.fetch.mockResolvedValueOnce(response({}, 404)).mockResolvedValueOnce(response({ receipt: 'legacy-printer-1' }))
    await dispatchDurableQr(input, store, io)
    expect(rows.get(input.idempotencyKey)?.result).toEqual({ receipt: 'legacy-printer-1' })
    io.fetch.mockResolvedValueOnce(response({}, 404))
    await dispatchDurableQr(input, store, io, true)
    expect(io.fetch).toHaveBeenCalledTimes(3)
  })
  it('successive identical goods use separate intent keys and both retained images', async () => {
    const { store, rows, io } = fixture()
    io.fetch.mockImplementation(async (_url, init) => init?.method === 'GET' ? response({}, 404) : response({ receipt: 'printer-1' }))
    await dispatchDurableQr(input, store, io)
    await dispatchDurableQr({ ...input, idempotencyKey: 'scan-two', context: { ...input.context, orderId: 'order-two', scanId: 'scan-two' } }, store, io)
    expect(rows.size).toBe(2)
    expect(io.fetch.mock.calls.filter(([, opts]) => opts?.method === 'POST')).toHaveLength(2)
  })
})


function linkedJobs(childOverrides: Partial<NativeQrJob> = {}) {
  const hash = 'a'.repeat(64)
  const child: NativeQrJob = {
    idempotencyKey: 'explicit-reprint', parentKey: input.idempotencyKey, hash,
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
    const { store, rows, io } = fixture()
    const { parent, child } = linkedJobs()
    io.fetch.mockResolvedValueOnce(response(parent)).mockResolvedValueOnce(response(child)).mockResolvedValueOnce(response(parent))
    const { controller, pack, complete } = recoveryController(store, io)
    pack.mockImplementation(async () => {
      expect(rows.get(input.idempotencyKey)?.result).toEqual(parent)
    })
    await controller.scan(input.context.barcode)
    expect(pack).toHaveBeenCalledWith(expect.objectContaining({ order_id: input.context.orderId }))
    expect(complete).toHaveBeenCalledWith(input.context.barcode)
    expect(controller.hasPending()).toBe(false)
    expect(io.fetch.mock.calls.map(([url]) => String(url))).toEqual([
      'http://127.0.0.1:17843/jobs/scan-one',
      'http://127.0.0.1:17843/jobs/explicit-reprint/reconcile',
      'http://127.0.0.1:17843/jobs/scan-one',
    ])
    expect(rows.get(input.idempotencyKey)?.result?.status).toBe('canceled')
  })
  it.each([
    { parentKey: 'another-original' }, { hash: 'b'.repeat(64) }, { hash: undefined },
    { widthMm: 70 }, { heightMm: 120 }, { context: { ...input.context, userId: 'other' } },
    { context: { ...input.context, wbOrderId: 999 } }, { context: undefined },
    { idempotencyKey: input.idempotencyKey }, { status: 'unknown' }, { status: 'canceled' },
    { status: 'submitting' }, { status: undefined }, { receipt: '' }, { receipt: undefined },
  ])('does not pack or silently repeat parent when child proof is insufficient: %j', async (override) => {
    const { store, io } = fixture()
    const { parent, child } = linkedJobs(override)
    io.fetch.mockImplementation(async (url) => response(String(url).includes('/explicit-reprint/') ? child : parent))
    const { controller, pack, complete } = recoveryController(store, io)
    await expect(controller.scan(input.context.barcode)).rejects.toThrow()
    expect(pack).not.toHaveBeenCalled()
    expect(complete).not.toHaveBeenCalled()
    expect(controller.hasPending()).toBe(true)
    expect(io.fetch.mock.calls.some(([url]) => String(url).endsWith('/print') || String(url).endsWith('/retry'))).toBe(false)
  })
  it('does not trust an old accepted child after reconciliation says canceled', async () => {
    const { store, io } = fixture()
    const { parent, child } = linkedJobs()
    const canceled = { ...child, status: 'canceled' }
    io.fetch.mockResolvedValueOnce(response(parent)).mockResolvedValueOnce(response(canceled))
      .mockResolvedValueOnce(response({ ...parent, reprints: [canceled] }))
    const { controller, pack } = recoveryController(store, io)
    await expect(controller.scan(input.context.barcode)).rejects.toThrow('отменено')
    expect(pack).not.toHaveBeenCalled()
  })
  it('does not retry a pre-submit parent while its explicit child remains unknown', async () => {
    const { store, io } = fixture()
    const { parent, child } = linkedJobs({ status: 'unknown' })
    parent.status = 'failed_before_submit'
    io.fetch.mockImplementation(async (url) => response(String(url).includes('/explicit-reprint/') ? child : parent))
    await expect(dispatchDurableQr(input, store, io)).rejects.toThrow()
    expect(io.fetch.mock.calls.some(([url]) => String(url).endsWith('/retry') || String(url).endsWith('/print'))).toBe(false)
  })
  it('does not pack before updated parent and linked acceptance commit to browser storage', async () => {
    const { store, io } = fixture()
    const { parent, child } = linkedJobs()
    const put = store.put
    let writes = 0
    store.put = async (attempt) => { if (++writes === 3) throw new Error('result commit failed'); await put(attempt) }
    io.fetch.mockResolvedValueOnce(response(parent)).mockResolvedValueOnce(response(child)).mockResolvedValueOnce(response(parent))
    const { controller, pack } = recoveryController(store, io)
    await expect(controller.scan(input.context.barcode)).rejects.toThrow('result commit failed')
    expect(pack).not.toHaveBeenCalled()
  })
})
