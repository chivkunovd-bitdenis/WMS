import { describe, expect, it, vi } from 'vitest'
import { createScannerListener } from './useBarcodeScanner'

const burst = [
  ['Ы', 'KeyS', true], ['Л', 'KeyK', true], ['Г', 'KeyU', true], ['.', 'Slash', false],
  ['У', 'KeyE', true], ['Ч', 'KeyX', true], ['Е', 'KeyT', true], [',', 'Slash', true],
  ['1', 'Digit1', false], ['3', 'Digit3', false], ['7', 'Digit7', false], ['?', 'Digit7', true], ['Ф', 'KeyA', true],
] as const

describe('WMS-696 physical RU punctuation in picking scanner bursts', () => {
  it('recovers slash, question mark and ampersand with RU letters', () => {
    const onScan = vi.fn(); let now = 0
    const listener = createScannerListener({ onScan, minLength: 5, maxIntervalMs: 50, getNow: () => now, getActiveElement: () => null, normalizeLayoutPunctuation: true })
    for (const [key, code, shiftKey] of [...burst, ['Enter', 'Enter', false] as const]) {
      listener({ key, code, shiftKey, ctrlKey: false, metaKey: false, altKey: false, preventDefault() {}, stopPropagation() {} }); now += 10
    }
    expect(onScan).toHaveBeenCalledWith('SKU/EXT?137&A')
  })

  it('preserves literal ASCII special symbols even when physical code is omitted', () => {
    const onScan = vi.fn(); let now = 0
    const listener = createScannerListener({ onScan, minLength: 5, maxIntervalMs: 50, getNow: () => now, getActiveElement: () => null, normalizeLayoutPunctuation: true })
    for (const key of [...'SKU/EXT?137&A', 'Enter']) {
      listener({ key, code: '', shiftKey: false, ctrlKey: false, metaKey: false, altKey: false, preventDefault() {}, stopPropagation() {} }); now += 10
    }
    expect(onScan).toHaveBeenCalledWith('SKU/EXT?137&A')
  })
})
