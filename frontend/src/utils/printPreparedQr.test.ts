// @vitest-environment jsdom
import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { printPreparedQr } from './printPreparedQr'
const input = { imageDataUrl: 'data:image/png;base64,cG5n', idempotencyKey: '54afadf6-8c67-43a2-bbf3-545ca3e8a01a', widthMm: 58, heightMm: 40 }
let frames: HTMLIFrameElement[]
let targets: Array<EventTarget & { print: ReturnType<typeof vi.fn> }>
let decode: ReturnType<typeof vi.fn>
let autoFinish: boolean
beforeEach(() => {
  localStorage.clear()
  document.body.innerHTML = '<input id="scan">'
  document.querySelector<HTMLInputElement>('input')!.focus()
  vi.stubGlobal('crypto', webcrypto)
  frames = []; targets = []; autoFinish = true
  decode = vi.fn().mockResolvedValue(undefined)
  const create = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation((name: string) => {
    const element = create(name)
    if (name !== 'iframe') return element
    const frame = element as HTMLIFrameElement
    const target = Object.assign(new EventTarget(), { print: vi.fn() })
    target.print.mockImplementation(() => { if (autoFinish) target.dispatchEvent(new Event('afterprint')) })
    Object.defineProperty(frame, 'contentWindow', { value: target })
    Object.defineProperty(frame, 'contentDocument', { value: { querySelector: () => ({ decode }) } })
    frames.push(frame); targets.push(target)
    return frame
  })
  const append = document.body.appendChild.bind(document.body)
  vi.spyOn(document.body, 'appendChild').mockImplementation(<T extends Node>(node: T): T => {
    const result = append(node)
    if (node instanceof HTMLIFrameElement) queueMicrotask(() => node.dispatchEvent(new Event('load')))
    return result
  })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('Chrome prepared-image printing', () => {
  it('decodes before print, sets exact size and preserves scanner focus', async () => {
    await printPreparedQr(input)
    expect(decode).toHaveBeenCalledOnce()
    expect(targets[0]!.print).toHaveBeenCalledOnce()
    expect(decode.mock.invocationCallOrder[0]).toBeLessThan(targets[0]!.print.mock.invocationCallOrder[0]!)
    expect(frames[0]!.srcdoc).toContain('@page { size: 40mm 58mm; margin: 0; }')
    expect(document.querySelectorAll('iframe')).toHaveLength(0)
    expect(document.activeElement?.id).toBe('scan')
  })
  it.each([[58, 40, 40, 58], [60, 40, 40, 60], [60, 80, 60, 80], [70, 120, 70, 120]])('keeps physical %sx%s paper as portrait %sx%s', async (widthMm, heightMm, pageWidth, pageHeight) => {
    await printPreparedQr({ ...input, widthMm, heightMm })
    expect(frames[0]!.srcdoc).toContain(`@page { size: ${pageWidth}mm ${pageHeight}mm; margin: 0; }`)
    expect(frames[0]!.style.width).toBe(`${pageWidth}mm`)
    expect(frames[0]!.style.height).toBe(`${pageHeight}mm`)
  })
  it('serializes scans until afterprint and retains each label size', async () => {
    autoFinish = false
    const first = printPreparedQr(input)
    const second = printPreparedQr({ ...input, idempotencyKey: 'second', widthMm: 60, heightMm: 80 })
    await vi.waitFor(() => expect(targets[0]?.print).toHaveBeenCalledOnce())
    expect(frames).toHaveLength(1)
    targets[0]!.dispatchEvent(new Event('afterprint'))
    await first
    await vi.waitFor(() => expect(targets[1]?.print).toHaveBeenCalledOnce())
    expect(frames[1]!.srcdoc).toContain('@page { size: 60mm 80mm; margin: 0; }')
    targets[1]!.dispatchEvent(new Event('afterprint'))
    await second
  })
  it('reuses completed UUID without printing again and rejects changed payload', async () => {
    await printPreparedQr(input)
    await printPreparedQr(input)
    expect(frames).toHaveLength(1)
    await expect(printPreparedQr({ ...input, widthMm: 60 })).rejects.toThrow('изменилась')
  })
  it('does not resubmit a persisted uncertain dispatch', async () => {
    await printPreparedQr(input)
    const key = `wms:qr-print:${input.idempotencyKey}`
    const record = JSON.parse(localStorage.getItem(key)!)
    localStorage.setItem(key, JSON.stringify({ ...record, state: 'dispatched' }))
    await expect(printPreparedQr(input)).rejects.toThrow('уже передано браузеру')
    expect(frames).toHaveLength(1)
  })
  it('does not print if decoding fails; same UUID can retry', async () => {
    decode.mockRejectedValueOnce(new Error('broken image'))
    await expect(printPreparedQr(input)).rejects.toThrow('broken image')
    expect(targets[0]!.print).not.toHaveBeenCalled()
    expect(localStorage.getItem(`wms:qr-print:${input.idempotencyKey}`)).toBeNull()
    await printPreparedQr(input)
    expect(targets[1]!.print).toHaveBeenCalledOnce()
  })
})
