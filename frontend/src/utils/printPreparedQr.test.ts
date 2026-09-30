// @vitest-environment jsdom
import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPackingScanController, type PackingScanDeps } from '../screens/v2/fbsSequentialPacking'
import { dispatchPreparedQrForCheck, printPreparedQr } from './printPreparedQr'
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
  vi.spyOn(window, 'confirm').mockReturnValue(false)
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
    await dispatchPreparedQrForCheck(input)
    expect(decode).toHaveBeenCalledOnce()
    expect(targets[0]!.print).toHaveBeenCalledOnce()
    expect(decode.mock.invocationCallOrder[0]).toBeLessThan(targets[0]!.print.mock.invocationCallOrder[0]!)
    expect(frames[0]!.srcdoc).toContain('@page { size: 40mm 58mm; margin: 0; }')
    expect(document.querySelectorAll('iframe')).toHaveLength(0)
    expect(document.activeElement?.id).toBe('scan')
    expect(window.confirm).not.toHaveBeenCalled()
  })
  it.each([[58, 40, 40, 58], [60, 40, 40, 60], [60, 80, 60, 80], [70, 120, 70, 120]])('keeps physical %sx%s paper as portrait %sx%s', async (widthMm, heightMm, pageWidth, pageHeight) => {
    await dispatchPreparedQrForCheck({ ...input, widthMm, heightMm })
    expect(frames[0]!.srcdoc).toContain(`@page { size: ${pageWidth}mm ${pageHeight}mm; margin: 0; }`)
    expect(frames[0]!.style.width).toBe(`${pageWidth}mm`)
    expect(frames[0]!.style.height).toBe(`${pageHeight}mm`)
    expect(frames[0]!.srcdoc).toContain('margin: 0; padding: 0; object-fit: contain;')
    expect(frames[0]!.srcdoc).not.toContain('padding: 2mm')
    expect(frames[0]!.srcdoc).not.toContain('image-rendering:')
    if (widthMm > heightMm) {
      expect(frames[0]!.srcdoc).toContain(`width: ${widthMm}mm; height: ${heightMm}mm;`)
      expect(frames[0]!.srcdoc).toContain(`transform: translateX(${heightMm}mm) rotate(90deg);`)
    } else {
      expect(frames[0]!.srcdoc).toContain('inset: 0; width: 100%; height: 100%;')
      expect(frames[0]!.srcdoc).not.toContain('rotate(')
    }
  })
  it('serializes scans until afterprint and retains each label size', async () => {
    autoFinish = false
    const first = dispatchPreparedQrForCheck(input)
    const second = dispatchPreparedQrForCheck({ ...input, idempotencyKey: 'second', widthMm: 60, heightMm: 80 })
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
    await dispatchPreparedQrForCheck(input)
    await dispatchPreparedQrForCheck(input)
    expect(frames).toHaveLength(1)
    await expect(dispatchPreparedQrForCheck({ ...input, widthMm: 60 })).rejects.toThrow('изменилась')
    expect(window.confirm).not.toHaveBeenCalled()
  })
  it('keeps an uncertain dispatch unchanged after cancelled recovery, without printing', async () => {
    await expect(printPreparedQr(input)).rejects.toThrow('Заказ не упакован')
    const key = `wms:qr-print:${input.idempotencyKey}`
    const record = JSON.parse(localStorage.getItem(key)!)
    localStorage.setItem(key, JSON.stringify({ ...record, state: 'dispatched' }))
    await expect(printPreparedQr(input)).rejects.toThrow('уже передано браузеру')
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(JSON.parse(localStorage.getItem(key)!).state).toBe('dispatched')
    expect(frames).toHaveLength(1)
  })
  it('continues after operator confirms the existing label, without reprinting', async () => {
    await expect(printPreparedQr(input)).rejects.toThrow('Заказ не упакован')
    const key = `wms:qr-print:${input.idempotencyKey}`
    const record = JSON.parse(localStorage.getItem(key)!)
    localStorage.setItem(key, JSON.stringify({ ...record, state: 'dispatched' }))
    vi.mocked(window.confirm).mockReturnValue(true)
    await expect(printPreparedQr({ ...input, imageDataUrl: 'data:image/png;base64,b3RoZXI=' })).rejects.toThrow('изменилась')
    expect(window.confirm).not.toHaveBeenCalled()
    await printPreparedQr(input)
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(JSON.parse(localStorage.getItem(key)!).state).toBe('operator-confirmed')
    await printPreparedQr(input)
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(frames).toHaveLength(1)
    expect(targets[0]!.print).toHaveBeenCalledOnce()
  })
  it('does not print if decoding fails; same UUID can retry', async () => {
    decode.mockRejectedValueOnce(new Error('broken image'))
    await expect(dispatchPreparedQrForCheck(input)).rejects.toThrow('broken image')
    expect(targets[0]!.print).not.toHaveBeenCalled()
    expect(localStorage.getItem(`wms:qr-print:check:${input.idempotencyKey}`)).toBeNull()
    await dispatchPreparedQrForCheck(input)
    expect(targets[1]!.print).toHaveBeenCalledOnce()
  })
  it('never resolves packing after Cancel/afterprint and does not automatically retry', async () => {
    const pack = vi.fn()
    await expect(printPreparedQr(input).then(pack)).rejects.toThrow('Заказ не упакован')
    expect(pack).not.toHaveBeenCalled()
    expect(window.confirm).not.toHaveBeenCalled()
    expect(targets[0]!.print).toHaveBeenCalledOnce()
    await expect(printPreparedQr(input).then(pack)).rejects.toThrow('уже передано браузеру')
    expect(pack).not.toHaveBeenCalled()
    expect(frames).toHaveLength(1)
    expect(JSON.parse(localStorage.getItem(`wms:qr-print:${input.idempotencyKey}`)!).state).toBe('browser-ended')
  })
  it('does not trust legacy browser-ended records as receipts', async () => {
    await expect(printPreparedQr(input)).rejects.toThrow('Заказ не упакован')
    // This is exactly the persisted state written by older versions on Cancel.
    await expect(printPreparedQr(input)).rejects.toThrow('уже передано браузеру')
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(targets[0]!.print).toHaveBeenCalledOnce()
  })
  it('isolates printer checks from packing acknowledgements even with the same UUID', async () => {
    await dispatchPreparedQrForCheck(input)
    await expect(printPreparedQr(input)).rejects.toThrow('Заказ не упакован')
    expect(frames).toHaveLength(2)
    expect(window.confirm).not.toHaveBeenCalled()
  })

  it('retains the selected order in the real packing controller after print cancellation', async () => {
    const deps: PackingScanDeps = {
      select: vi.fn().mockResolvedValue({ scan_id: input.idempotencyKey, order_id: 'order-1', requires_honest_sign: false }),
      preload: vi.fn().mockResolvedValue(input.imageDataUrl), bind: vi.fn(),
      print: (result, imageDataUrl) => printPreparedQr({ ...input, idempotencyKey: result.scan_id, imageDataUrl }),
      pack: vi.fn(), claim: () => 'request-1', saved: () => false,
      remember: vi.fn(), complete: vi.fn(), changed: vi.fn(),
    }
    const scanner = createPackingScanController(deps)
    await expect(scanner.scan('barcode')).rejects.toThrow('Заказ не упакован')
    expect(deps.pack).not.toHaveBeenCalled()
    expect(deps.complete).not.toHaveBeenCalled()
    expect(scanner.view()).toMatchObject({ orderId: 'order-1' })
    await expect(scanner.scan('barcode')).rejects.toThrow('уже передано браузеру')
    expect(deps.select).toHaveBeenCalledOnce()
    expect(deps.pack).not.toHaveBeenCalled()
    expect(targets[0]!.print).toHaveBeenCalledOnce()
    vi.mocked(window.confirm).mockReturnValue(true)
    await scanner.scan('barcode')
    expect(deps.pack).toHaveBeenCalledOnce()
    expect(scanner.hasPending()).toBe(false)
    expect(targets[0]!.print).toHaveBeenCalledOnce()
  })
  it('a late afterprint cannot overwrite operator confirmation after a timeout', async () => {
    autoFinish = false
    let expire: (() => void) | undefined
    const setTimeout = window.setTimeout.bind(window)
    vi.spyOn(window, 'setTimeout').mockImplementation(((callback: () => void, delay?: number) => {
      if (delay === 60_000) { expire = callback; return 123 }
      return setTimeout(callback, delay)
    }) as typeof window.setTimeout)
    const first = printPreparedQr(input)
    const failed = expect(first).rejects.toThrow('не подтвердил')
    await vi.waitFor(() => expect(targets[0]?.print).toHaveBeenCalledOnce())
    expire!()
    await failed
    vi.mocked(window.confirm).mockReturnValue(true)
    await printPreparedQr(input)
    targets[0]!.dispatchEvent(new Event('afterprint'))
    expect(JSON.parse(localStorage.getItem(`wms:qr-print:${input.idempotencyKey}`)!).state).toBe('operator-confirmed')
    expect(document.querySelectorAll('iframe')).toHaveLength(0)
    await printPreparedQr(input)
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(targets[0]!.print).toHaveBeenCalledOnce()
  })

})
