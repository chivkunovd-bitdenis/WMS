// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { FbsScanPrintToggles } from './FbsScanPrintToggles'
import type { FbsScanPrintPreferences } from './fbsScanAutoPrint'

beforeAll(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

let host: HTMLDivElement
let root: Root
let scanField: HTMLInputElement
let value: FbsScanPrintPreferences
const onChange = vi.fn((next: FbsScanPrintPreferences) => { value = next; render() })
const render = () => act(() => root.render(<FbsScanPrintToggles value={value} onChange={onChange} />))
const q = (id: string) => host.querySelector<HTMLElement>(`[data-testid="${id}"]`)

beforeEach(() => {
  host = document.createElement('div')
  scanField = document.createElement('input')
  document.body.append(scanField, host)
  root = createRoot(host)
  onChange.mockClear()
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
  scanField.remove()
})

describe('WMS-633 · «− N +» counter never takes the scanner', () => {
  it('is shown only with its checkbox and has no input that could receive a scan', () => {
    value = { printQr: true, printChz: false, reprintChz: false }
    render()
    expect(q('fbs-scan-print-chz-copies')).toBeNull()
    value = { ...value, printChz: true, printChzCopies: 3 }
    render()
    expect(q('fbs-scan-print-chz-copies-value')?.textContent).toBe('3')
    expect(q('fbs-scan-print-chz-copies')?.querySelector('input, textarea, [contenteditable]')).toBeNull()
    expect(q('fbs-scan-reprint-chz-copies')).toBeNull()
  })

  it('+/− change N within 1…10 and leave the focus on the scan field', () => {
    value = { printQr: false, printChz: true, reprintChz: false, printChzCopies: 9 }
    render()
    scanField.focus()
    for (const id of ['fbs-scan-print-chz-copies-plus', 'fbs-scan-print-chz-copies-minus']) {
      const button = q(id)!
      expect(button.tabIndex).toBe(-1)
      const down = new MouseEvent('mousedown', { bubbles: true, cancelable: true })
      act(() => { button.dispatchEvent(down) })
      expect(down.defaultPrevented).toBe(true)
    }
    act(() => q('fbs-scan-print-chz-copies-plus')!.click())
    expect(value.printChzCopies).toBe(10)
    expect((q('fbs-scan-print-chz-copies-plus') as HTMLButtonElement).disabled).toBe(true)
    act(() => q('fbs-scan-print-chz-copies-minus')!.click())
    expect(value.printChzCopies).toBe(9)
    expect(document.activeElement).toBe(scanField)
  })

  it('typed digits and Enter of a scanner do not change N', () => {
    value = { printQr: false, printChz: false, reprintChz: true, reprintChzCopies: 3 }
    render()
    onChange.mockClear()
    const counter = q('fbs-scan-reprint-chz-copies')!
    for (const key of [...'4606310000004', 'Enter']) {
      act(() => {
        counter.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
        document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
      })
    }
    expect(onChange).not.toHaveBeenCalled()
    expect(q('fbs-scan-reprint-chz-copies-value')?.textContent).toBe('3')
  })
})
