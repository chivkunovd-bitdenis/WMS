import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PrintQuantityField, parsePrintQuantityDraft } from './PrintQuantityField'

describe('quantity editing in individual and batch print forms', () => {
  it('allows erasing zero before typing the full replacement quantity', () => {
    expect(parsePrintQuantityDraft('0', 0, 99)).toBe(0)
    expect(parsePrintQuantityDraft('', 0, 99)).toBeNull()
    expect(parsePrintQuantityDraft('12', 0, 99)).toBe(12)
  })

  it('preserves each scenario minimum without forcing one during editing', () => {
    expect(parsePrintQuantityDraft('', 1, 999)).toBeNull()
    expect(parsePrintQuantityDraft('0', 1, 999)).toBe(1)
    expect(parsePrintQuantityDraft('0', 0, 99)).toBe(0)
    expect(parsePrintQuantityDraft('1000', 1, 999)).toBe(999)
    expect(parsePrintQuantityDraft('2.5', 0, 99)).toBe(2)
  })

  it('renders a manually editable number input including a permitted zero', () => {
    const markup = renderToStaticMarkup(<PrintQuantityField
      label="ШК на заказ" value={0} onChange={() => {}} min={0} max={99}
    />)
    expect(markup).toContain('type="number"')
    expect(markup).toContain('value="0"')
    expect(markup).toContain('min="0"')
    expect(markup).toContain('max="99"')
    expect(markup).not.toContain('readonly')
  })
})
