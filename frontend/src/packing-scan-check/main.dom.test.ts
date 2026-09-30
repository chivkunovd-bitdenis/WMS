// @vitest-environment jsdom
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { TEST_LABELS } from './catalog'
const { dispatchPreparedQrForCheck, toCanvas } = vi.hoisted(() => ({ dispatchPreparedQrForCheck: vi.fn().mockResolvedValue(undefined), toCanvas: vi.fn() }))
vi.mock('../utils/printPreparedQr', () => ({ dispatchPreparedQrForCheck }))
vi.mock('bwip-js', () => ({ toCanvas }))
const printSpy = vi.fn()
beforeAll(async () => {
  document.body.innerHTML = '<div id="app"></div>'
  window.print = printSpy
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,test')
  await import('./main')
})
function scan(barcode: string) {
  document.querySelector<HTMLInputElement>('#scan')!.value = barcode
  document.querySelector('#scan-form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
}
describe('minimal Chrome printer check', () => {
  it('shows only barcode input and size without preview, catalog or buttons', () => {
    expect(document.querySelectorAll('input')).toHaveLength(1)
    expect(document.querySelectorAll('select')).toHaveLength(1)
    expect(document.querySelectorAll('h1,p,button,img,details,input[type="checkbox"]')).toHaveLength(0)
    expect(document.querySelector<HTMLElement>('#error')!.hidden).toBe(true)
    expect(toCanvas).toHaveBeenCalledTimes(10)
  })
  it('dispatches all ten codes immediately through shared browser transport, with focus preserved', () => {
    for (const label of TEST_LABELS) scan(label.barcode)
    expect(dispatchPreparedQrForCheck).toHaveBeenCalledTimes(10)
    expect(dispatchPreparedQrForCheck.mock.calls[0]![0]).toMatchObject({ widthMm: 58, heightMm: 40, imageDataUrl: 'data:image/png;base64,test' })
    expect(new Set(dispatchPreparedQrForCheck.mock.calls.map(([input]) => input.idempotencyKey)).size).toBe(10)
    expect(document.querySelector<HTMLInputElement>('#scan')!.value).toBe('')
    expect(document.querySelectorAll('iframe')).toHaveLength(0)
    expect(printSpy).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(document.querySelector('#scan'))
  })
  it('reports an unknown barcode without printing', () => {
    dispatchPreparedQrForCheck.mockClear()
    scan('unknown')
    expect(document.querySelector('#error')!.textContent).toBe('Неизвестный штрихкод: unknown')
    expect(dispatchPreparedQrForCheck).not.toHaveBeenCalled()
    expect(printSpy).not.toHaveBeenCalled()
  })
  it('shows a transport failure without a second print path or retry', async () => {
    dispatchPreparedQrForCheck.mockRejectedValueOnce(new Error('Ошибка очереди принтера'))
    scan(TEST_LABELS[0]!.barcode)
    await Promise.resolve()
    expect(document.querySelector('#error')!.textContent).toBe('Ошибка очереди принтера')
    expect(dispatchPreparedQrForCheck).toHaveBeenCalledTimes(1)
    expect(printSpy).not.toHaveBeenCalled()
  })
})
