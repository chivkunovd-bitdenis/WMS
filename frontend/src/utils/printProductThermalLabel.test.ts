import { describe, expect, it } from 'vitest'
import {
  buildProductLabelContentCss,
  buildProductLabelSectionHtml,
  buildProductLabelTextLines,
  labelScale,
  labelTextFontScale,
  trimProductLabelTextLinesFromBottom,
  type ProductThermalLabelData,
} from './printProductThermalLabel'
import { LABEL_SIZES, resolveLabelSize } from './labelSize'

const FULL_WB_LABEL: ProductThermalLabelData = {
  product_name: 'Большой набор для лепки подарочный 45 предметов',
  sku_code: 'Kids-Growth-(ПД)',
  wb_vendor_code: 'Kids-Growth-(ПД)',
  wb_size: '0',
  wb_color: null,
  wb_brand: null,
  wb_composition: 'пластилин мягкий со стеком, пластилин воздушный',
  seller_name: 'ИП Дорощ А.В.',
  barcode: '2043540288635',
}

const SUNGLASSES_LABEL: ProductThermalLabelData = {
  product_name: 'Очки солнцезащитные квадратные модные',
  sku_code: 'ОчкиАVКоричневыйКВ',
  wb_vendor_code: 'ОчкиАVКоричневыйКВ',
  wb_size: '0',
  wb_color: 'коричневый, шоколадный, шоколадный трюфель',
  wb_brand: 'Alte Vette',
  wb_composition: null,
  seller_name: 'ИП Горячкина Т И',
  barcode: '2052582795896',
}

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

  it('text stack uses non-shrinking lines and clips overflow from bottom', () => {
    const css = buildProductLabelContentCss(resolveLabelSize('58x40'))
    expect(css).toContain('overflow: hidden')
    expect(css).toContain('flex: 0 0 auto')
    expect(css).toContain('flex-shrink: 0')
    expect(css).toContain('min-height:')
    expect(css).not.toContain('-webkit-line-clamp')
    expect(css).not.toContain('gap: 0.15mm')
  })

  it('caps text font growth on tall labels so seller line is not crushed', () => {
    const tall = labelTextFontScale(resolveLabelSize('70x120'))
    const short = labelTextFontScale(resolveLabelSize('58x40'))
    const legacyTall = labelScale(resolveLabelSize('70x120')).font
    expect(short).toBeCloseTo(1.12, 2)
    expect(tall).toBeLessThanOrEqual(1.28)
    expect(tall).toBeLessThan(legacyTall)
  })

  it('seller CSS reserves min-height and line spacing uses margin (not flex gap)', () => {
    const css = buildProductLabelContentCss(resolveLabelSize('70x120'))
    expect(css).toMatch(/\.seller \{[\s\S]*min-height:/)
    // Межстрочный зазор — margin-bottom на строках, а не flex gap: термопринтер
    // игнорирует gap и строки слипаются (наезд названия на «Артикул»).
    expect(css).toMatch(/\.body > p \{[\s\S]*margin:\s*0 0 [0-9.]+mm/)
    expect(css).not.toMatch(/\.body \{[\s\S]*gap:/)
    expect(css).toMatch(/margin-top:\s*[0-9.]+mm/)
  })

  it('name has no max-height/overflow clamp (printer bled clamp over Артикул)', () => {
    const css = buildProductLabelContentCss(resolveLabelSize('58x40'))
    const nameBlock = css.slice(css.indexOf('.name {'), css.indexOf('.meta {'))
    expect(nameBlock).not.toContain('max-height')
    expect(nameBlock).not.toContain('overflow')
    const html = buildProductLabelSectionHtml(SUNGLASSES_LABEL, 'data:image/png;base64,xx', undefined, resolveLabelSize('58x40'))
    expect(html).not.toContain('max-height:')
  })

  it('over-long name is truncated by chars with ellipsis (fits the label lines)', () => {
    const size = resolveLabelSize('58x40')
    const longName = 'Очки '.repeat(60)
    const lines = buildProductLabelTextLines({ ...SUNGLASSES_LABEL, product_name: longName }, undefined, size)
    const nameLine = lines.find((l) => l.kind === 'name')
    expect(nameLine).toBeDefined()
    expect(nameLine!.text.endsWith('…')).toBe(true)
    expect(nameLine!.text.length).toBeLessThan(longName.length)
  })

  it('58×40 trims bottom lines when content does not fit', () => {
    const size = resolveLabelSize('58x40')
    const trimmed = trimProductLabelTextLinesFromBottom(
      buildProductLabelTextLines(FULL_WB_LABEL, undefined, size),
      size,
    )
    const kinds = trimmed.map((line) => line.kind)
    expect(kinds).toContain('seller')
    expect(kinds).toContain('name')
    expect(kinds).toContain('article')
    expect(kinds).not.toContain('footer')
  })

  it('58×40 keeps color and brand for ИП Горячкина, drops size and footer', () => {
    const size = resolveLabelSize('58x40')
    const html = buildProductLabelSectionHtml(SUNGLASSES_LABEL, 'data:image/png;base64,xx', undefined, size)
    expect(html).toContain('ИП Горячкина Т И')
    expect(html).toContain('class="seller"')
    expect(html).toContain('Цвет:')
    expect(html).toContain('Бренд: Alte Vette')
    expect(html).not.toContain('Размер:')
    expect(html).not.toContain('class="footer"')
    expect(html).not.toContain('-webkit-line-clamp')
  })

  it('70×120 keeps footer when there is enough height', () => {
    const size = resolveLabelSize('70x120')
    const trimmed = trimProductLabelTextLinesFromBottom(
      buildProductLabelTextLines(FULL_WB_LABEL, undefined, size),
      size,
    )
    expect(trimmed.some((line) => line.kind === 'footer')).toBe(true)
  })
})
