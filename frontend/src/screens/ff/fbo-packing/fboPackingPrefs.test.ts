// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import {
  fboPackingPrintStorageKey,
  loadFboPackingPrintPreferences,
  saveFboPackingPrintPreferences,
} from './fboPackingPrefs'

const token = `x.${btoa(JSON.stringify({ sub: 'u1', tenant_id: 't1' }))}.y`

beforeEach(() => window.localStorage.clear())

describe('WMS-686 R25 · галки печати упаковки FBO', () => {
  it('по умолчанию выключены: печатать нечего, WMS Print не нужен', () => {
    expect(loadFboPackingPrintPreferences(token)).toEqual({ printBarcode: false, printChz: false })
  })

  it('хранятся под своим ключом, не пересекаются с FBS и с другим сотрудником', () => {
    saveFboPackingPrintPreferences(token, { printBarcode: true, printChz: false })
    expect(fboPackingPrintStorageKey(token)).toBe('wms:fbo:scan-auto-print:t1:u1')
    expect(window.localStorage.getItem('wms:fbo:scan-auto-print:t1:u1')).toContain('"printBarcode":true')
    expect(Object.keys(window.localStorage).some((key) => key.startsWith('wms:fbs:'))).toBe(false)
    expect(loadFboPackingPrintPreferences(token)).toEqual({ printBarcode: true, printChz: false })
    const other = `x.${btoa(JSON.stringify({ sub: 'u2', tenant_id: 't1' }))}.y`
    expect(loadFboPackingPrintPreferences(other)).toEqual({ printBarcode: false, printChz: false })
  })

  it('повреждённое значение никогда не включает печать', () => {
    window.localStorage.setItem(fboPackingPrintStorageKey(token), '{broken')
    expect(loadFboPackingPrintPreferences(token)).toEqual({ printBarcode: false, printChz: false })
  })
})
