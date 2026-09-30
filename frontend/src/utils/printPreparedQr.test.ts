// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { printPreparedQr } from './printPreparedQr'
const input = { imageDataUrl: 'data:image/png;base64,cG5n', idempotencyKey: '54afadf6-8c67-43a2-bbf3-545ca3e8a01a', widthMm: 58, heightMm: 40 }
afterEach(() => vi.unstubAllGlobals())
describe('native printer transport', () => {
  it('accepts only the matching native receipt and makes one local request', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'submitted', job_id: input.idempotencyKey, receipt: 'thermal-7' }) })
    vi.stubGlobal('fetch', fetch)
    await printPreparedQr(input)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0]![0]).toBe('http://127.0.0.1:17845/print-image')
    expect(JSON.parse(fetch.mock.calls[0]![1].body)).toEqual({ job_id: input.idempotencyKey, image_data_url: input.imageDataUrl, width_mm: 58, height_mm: 40 })
  })
  it('does not retry after a lost response and never invokes print UI', async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError('network'))
    const print = vi.spyOn(window, 'print').mockImplementation(() => undefined)
    vi.stubGlobal('fetch', fetch)
    await expect(printPreparedQr(input)).rejects.toThrow('Нет связи')
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(print).not.toHaveBeenCalled()
    print.mockRestore()
  })
  it('does not treat HTTP success without a matching receipt as printing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'submitted', job_id: 'other', receipt: 'thermal-1' }) }))
    await expect(printPreparedQr(input)).rejects.toThrow('не подтверждена')
  })
})
