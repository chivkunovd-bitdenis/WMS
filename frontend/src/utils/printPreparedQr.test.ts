// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPackingScanController, type PackingScanDeps } from '../screens/v2/fbsSequentialPacking'
import { dispatchPreparedQrForCheck, printPreparedQr } from './printPreparedQr'
const input = { imageDataUrl: 'data:image/png;base64,cG5n', idempotencyKey: 'scan-1', widthMm: 58, heightMm: 40 }
const receipt = () => ({ ok: true, json: async () => ({ receipt: 'printer-123' }) })
let fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => {
  document.body.innerHTML = '<input id="scan">'
  document.querySelector<HTMLInputElement>('input')!.focus()
  vi.spyOn(window, 'print').mockImplementation(() => undefined)
  vi.spyOn(window, 'confirm').mockReturnValue(false)
  fetchMock = vi.fn().mockResolvedValue(receipt())
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('direct OS queue printing', () => {
  it('preserves scanner focus without browser print UI or confirmation', async () => {
    await dispatchPreparedQrForCheck(input)
    expect(document.activeElement?.id).toBe('scan')
    expect(document.querySelectorAll('iframe')).toHaveLength(0)
    expect(window.print).not.toHaveBeenCalled()
    expect(window.confirm).not.toHaveBeenCalled()
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual(input)
  })
  it('waits for the first OS receipt before sending the next scan', async () => {
    let finish!: (value: ReturnType<typeof receipt>) => void
    fetchMock.mockReturnValueOnce(new Promise((resolve) => { finish = resolve }))
    const first = printPreparedQr(input)
    const second = printPreparedQr({ ...input, idempotencyKey: 'scan-2' })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    finish(receipt())
    await first; await second
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
  it('does not retry automatically or use browser printing after losing the response', async () => {
    fetchMock.mockRejectedValueOnce(new Error('disconnected'))
    await expect(printPreparedQr(input)).rejects.toThrow('Нет ответа WMS Print')
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(window.print).not.toHaveBeenCalled()
  })
  it('keeps the selected packing order until a real queue receipt is recovered', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, json: async () => ({ error: 'Результат неизвестен' }) })
    const qrOnly = { printQr: true, printChz: false, reprintChz: false }
    const deps: PackingScanDeps = {
      preferences: () => qrOnly,
      select: vi.fn().mockResolvedValue({ scan_id: input.idempotencyKey, order_id: 'order-1', requires_honest_sign: false, printed_codes: [] }),
      lookupSticker: vi.fn(), directReprint: vi.fn(), release: vi.fn(), undo: vi.fn(),
      preload: vi.fn().mockResolvedValue(input.imageDataUrl), bind: vi.fn(),
      print: (result, imageDataUrl) => printPreparedQr({ ...input, idempotencyKey: result.scan_id, imageDataUrl }),
      printChz: vi.fn(), printCopy: vi.fn(),
      pack: vi.fn(), claim: () => ({ key: 'request-1', preferences: qrOnly }), saved: () => false,
      remember: vi.fn(), complete: vi.fn(), changed: vi.fn(),
    }
    const scanner = createPackingScanController(deps)
    await expect(scanner.scan('barcode')).rejects.toThrow('Результат неизвестен')
    expect(deps.pack).not.toHaveBeenCalled()
    expect(scanner.view()).toMatchObject({ orderId: 'order-1' })
    await scanner.scan('barcode')
    expect(deps.select).toHaveBeenCalledOnce()
    expect(deps.pack).toHaveBeenCalledOnce()
    expect(scanner.hasPending()).toBe(false)
    expect(JSON.parse(fetchMock.mock.calls[1]![1].body).idempotencyKey).toBe(input.idempotencyKey)
  })
})
