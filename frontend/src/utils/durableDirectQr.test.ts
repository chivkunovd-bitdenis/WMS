import { describe, expect, it, vi } from 'vitest'
import { dispatchDurableQr, prepareDurableQr, restoreDurableQr, type DurableQrAttempt, type DurableQrInput, type QrAttemptStore } from './durableDirectQr'

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
