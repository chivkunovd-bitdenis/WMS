// @vitest-environment jsdom
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { TEST_LABELS } from './catalog'
const printSpy = vi.fn()
beforeAll(async () => {
  document.body.innerHTML = '<div id="app"></div>'
  window.print = printSpy
  await import('./main')
})
function scan(barcode: string) {
  document.querySelector<HTMLInputElement>('#scan')!.value = barcode
  document.querySelector('#scan-form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
}
describe('minimal printer check', () => {
  it('shows only barcode input and size without preview, catalog or buttons', () => {
    expect(document.querySelectorAll('input')).toHaveLength(1)
    expect(document.querySelectorAll('select')).toHaveLength(1)
    expect(document.querySelectorAll('h1,p,button,img,details,input[type="checkbox"]')).toHaveLength(0)
    expect(document.querySelector<HTMLElement>('#error')!.hidden).toBe(true)
  })
  it('reports disconnected printer for all ten codes, without a print dialog or frame', () => {
    for (const label of TEST_LABELS) {
      scan(label.barcode)
      expect(document.querySelector('#error')!.textContent).toBe('Принтер не подключён')
    }
    expect(document.querySelector<HTMLInputElement>('#scan')!.value).toBe('')
    expect(document.querySelector<HTMLElement>('#error')!.hidden).toBe(false)
    expect(document.querySelectorAll('iframe')).toHaveLength(0)
    expect(printSpy).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(document.querySelector('#scan'))
  })
  it('reports an unknown barcode without printing', () => {
    scan('unknown')
    expect(document.querySelector('#error')!.textContent).toBe('Неизвестный штрихкод: unknown')
    expect(printSpy).not.toHaveBeenCalled()
  })
})
