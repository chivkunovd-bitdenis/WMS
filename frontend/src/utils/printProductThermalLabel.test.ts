import { describe, expect, it } from 'vitest'
import { buildProductLabelContentCss, labelScale } from './printProductThermalLabel'
import { LABEL_SIZES, resolveLabelSize } from './labelSize'

describe('printProductThermalLabel', () => {
  it.each(LABEL_SIZES.map((s) => [s.id, s.heightMm] as const))(
    '%s — barcode height does not scale by label height ratio (no 2-label split)',
    (id, heightMm) => {
      const size = resolveLabelSize(id)
      const k = labelScale(size)
      const css = buildProductLabelContentCss(size)
      const brokenHeightMm = 14 * k.h
      expect(css).not.toContain('object-fit: fill')
      expect(css).toContain('object-fit: contain')
      if (k.h > 1.01) {
        // Старый баг: 14*k.h давал слишком высокий ШК на вытянутых этикетках.
        expect(brokenHeightMm).toBeGreaterThan(14 * k.uniform + 0.5)
        expect(css).not.toMatch(new RegExp(`max-height:\\s*${Math.round(brokenHeightMm * 100) / 100}mm`))
      }
      const maxBarcodeShare = (14 * k.uniform) / heightMm
      expect(maxBarcodeShare).toBeLessThanOrEqual(0.36)
    },
  )

  it('scales barcode with uniform factor, not independent height stretch', () => {
    const k = labelScale(resolveLabelSize('70x120'))
    expect(k.uniform).toBeCloseTo(70 / 58, 2)
    const css = buildProductLabelContentCss(resolveLabelSize('70x120'))
    expect(css).toContain(`width: ${Math.round(52 * k.uniform * 100) / 100}mm`)
    expect(css).toContain(`max-height: ${Math.round(14 * k.uniform * 100) / 100}mm`)
  })

  it('58×40 baseline matches historical barcode box', () => {
    const css = buildProductLabelContentCss(resolveLabelSize('58x40'))
    expect(css).toContain('width: 52mm')
    expect(css).toContain('max-height: 14mm')
  })
})
