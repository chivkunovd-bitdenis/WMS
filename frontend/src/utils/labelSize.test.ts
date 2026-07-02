import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  DEFAULT_LABEL_SIZE_ID,
  LABEL_SIZES,
  loadLabelSizeId,
  resolveLabelSize,
  saveLabelSizeId,
} from './labelSize'

// vitest env is `node`; provide a minimal localStorage-backed window for persistence tests.
function installFakeWindow(): void {
  const store = new Map<string, string>()
  ;(globalThis as { window?: unknown }).window = {
    localStorage: {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    },
  }
}

describe('labelSize', () => {
  beforeEach(() => {
    installFakeWindow()
  })

  afterEach(() => {
    delete (globalThis as { window?: unknown }).window
  })

  it('exposes the four required label sizes', () => {
    expect(LABEL_SIZES.map((s) => s.id)).toEqual(['58x40', '60x80', '60x40', '70x120'])
  })

  it('default is 58×40 (as previously hardcoded)', () => {
    expect(DEFAULT_LABEL_SIZE_ID).toBe('58x40')
    expect(resolveLabelSize(null)).toMatchObject({ widthMm: 58, heightMm: 40 })
  })

  it('resolves unknown id to default', () => {
    // @ts-expect-error intentionally invalid id
    expect(resolveLabelSize('99x99')).toMatchObject({ id: '58x40' })
  })

  it('persists and restores the last selected size', () => {
    saveLabelSizeId('60x80')
    expect(loadLabelSizeId()).toBe('60x80')
  })

  it('falls back to default when nothing stored', () => {
    expect(loadLabelSizeId()).toBe('58x40')
  })
})
