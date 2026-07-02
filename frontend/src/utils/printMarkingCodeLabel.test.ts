import { describe, expect, it } from 'vitest'

import { formatGtinDisplay, maskCisTail, parseGs1Cis } from './parseGs1Cis'
import { buildCzArtifactLabelHtml, buildCzLabelHtml, buildMarkingTapeDocument } from './printMarkingCodeLabel'

const SAMPLE_CIS = `01${'04600000000001'}21${'A'.repeat(20)}0001`
const MATRIX_STUB = 'data:image/png;base64,stub'

describe('parseGs1Cis', () => {
  it('extracts GTIN and serial from GS1 CIS', () => {
    const parsed = parseGs1Cis(SAMPLE_CIS)
    expect(parsed.gtin14).toBe('04600000000001')
    expect(parsed.gtinDisplay).toBe('4600000000001')
    expect(parsed.serial).toBe(`${'A'.repeat(20)}0001`)
  })

  it('formats 14-digit GTIN as EAN-13 display', () => {
    expect(formatGtinDisplay('00000000123456')).toBe('0000000123456')
  })

  it('masks long CIS tail for print', () => {
    expect(maskCisTail(SAMPLE_CIS)).toMatch(/^…/)
    expect(maskCisTail('short')).toBe('short')
  })
})

// TC-NEW-CZ-PRINT-01 — CZ label HTML: DataMatrix left + info panel right, 58×40 layout.
describe('buildCzLabelHtml', () => {
  it('renders matrix and right info panel instead of tail-only layout', () => {
    const section = buildCzLabelHtml(SAMPLE_CIS, MATRIX_STUB)
    expect(section).toContain('class="label label--cz"')
    expect(section).toContain('data-tape-block="cz"')
    expect(section).toContain('class="matrix cz-matrix"')
    expect(section).toContain('data-testid="cz-label-info"')
    expect(section).toContain('cz-field--gtin')
    expect(section).toContain('cz-field--serial')
    expect(section).toContain('cz-code')
    expect(section).not.toContain('class="tail"')
  })

  it('builds seller artifact label section', () => {
    const section = buildCzArtifactLabelHtml('data:image/png;base64,abc')
    expect(section).toContain('label--cz-artifact')
    expect(section).toContain('cz-label-artifact-img')
    expect(section).not.toContain('cz-label-info')
  })

  it('builds mixed tape with cz and label blocks', () => {
    const doc = buildMarkingTapeDocument([
      buildCzLabelHtml(SAMPLE_CIS, MATRIX_STUB),
      '<section class="label" data-tape-block="label" data-testid="product-thermal-label"></section>',
    ])
    expect(doc).toContain('size: 58mm 40mm')
    expect(doc).toContain('data-tape-block="cz"')
    expect(doc).toContain('data-tape-block="label"')
    expect(doc).toContain('flex-direction: row')
  })

  // TC-NEW-PRINT-SIZE-01 — выбранный размер этикетки реально попадает в @page/размер листа.
  it('applies chosen label size to page and label box', () => {
    const doc = buildMarkingTapeDocument(
      [buildCzLabelHtml(SAMPLE_CIS, MATRIX_STUB)],
      { id: '70x120', label: '70 × 120 мм', widthMm: 70, heightMm: 120 },
    )
    expect(doc).toContain('size: 70mm 120mm')
    expect(doc).toContain('width: 70mm')
    expect(doc).toContain('height: 120mm')
  })
})
