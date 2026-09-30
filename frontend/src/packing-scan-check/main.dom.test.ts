// @vitest-environment jsdom
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { TEST_LABELS } from './catalog'
const { printDirectQr, toCanvas } = vi.hoisted(() => ({ printDirectQr: vi.fn().mockResolvedValue(undefined), toCanvas: vi.fn() }))
vi.mock('../utils/printDirectQr', () => ({ printDirectQr }))
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
  it('shows only barcode input without preview, catalog or buttons', () => {
    expect(document.querySelectorAll('input')).toHaveLength(1)
    expect(document.querySelectorAll('select')).toHaveLength(0)
    expect(document.querySelectorAll('h1,p,button,img,details,input[type="checkbox"]')).toHaveLength(0)
    expect(document.querySelector<HTMLElement>('#error')!.hidden).toBe(true)
    expect(toCanvas).toHaveBeenCalledTimes(10)
  })
  it('dispatches all ten codes immediately through direct native transport, with focus preserved', () => {
    for (const label of TEST_LABELS) scan(label.barcode)
    expect(printDirectQr).toHaveBeenCalledTimes(10)
    expect(printDirectQr.mock.calls[0]![0]).toMatchObject({ widthMm: 58, heightMm: 40, imageDataUrl: 'data:image/png;base64,test' })
    expect(new Set(printDirectQr.mock.calls.map(([input]) => input.idempotencyKey)).size).toBe(10)
    expect(document.querySelector<HTMLInputElement>('#scan')!.value).toBe('')
    expect(document.querySelectorAll('iframe')).toHaveLength(0)
    expect(printSpy).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(document.querySelector('#scan'))
  })
  it('reports an unknown barcode without printing', () => {
    printDirectQr.mockClear()
    scan('unknown')
    expect(document.querySelector('#error')!.textContent).toBe('Неизвестный штрихкод: unknown')
    expect(printDirectQr).not.toHaveBeenCalled()
    expect(printSpy).not.toHaveBeenCalled()
  })
  it('shows a transport failure without a second print path or retry', async () => {
    printDirectQr.mockRejectedValueOnce(new Error('Ошибка очереди принтера'))
    scan(TEST_LABELS[0]!.barcode)
    await vi.waitFor(() => expect(document.querySelector('#error')!.textContent).toBe('Ошибка очереди принтера'))
    expect(document.querySelector('#error')!.textContent).toBe('Ошибка очереди принтера')
    expect(printDirectQr).toHaveBeenCalledTimes(1)
    expect(printSpy).not.toHaveBeenCalled()
  })
})
