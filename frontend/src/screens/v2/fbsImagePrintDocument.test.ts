// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { LABEL_SIZES, type LabelSize } from '../../utils/labelSize'
import { buildMarkingTapeDocument, buildWbOrderQrLabelHtml } from '../../utils/printMarkingCodeLabel'
import { buildFbsImagePrintDocument, type FbsImagePrintItem } from './fbsImagePrintDocument'

const qr: FbsImagePrintItem = { objectUrl: 'blob:qr-first', label: 'Печать стикера заказа WB' }
const boxQr: FbsImagePrintItem = { objectUrl: 'blob:qr-box', label: 'Печать QR короба WMS' }
const size58: LabelSize = LABEL_SIZES[0]!

type Declared = { value: string; specificity: number; order: number }

function specificity(selector: string): number {
  return (selector.match(/[.:][\w-]+/g) ?? []).length
}

/**
 * Каскад по правилам печатного документа для одного свойства: какое значение
 * получит элемент. Селекторы шаблона простые (.label, .label:last-child,
 * .label+.label), поэтому специфичность — число классов и псевдоклассов.
 */
function resolved(doc: Document, element: Element, property: string): string | null {
  // Свой разбор стиля: CSSOM jsdom отбрасывает незнакомые ему break-*.
  const css = Array.from(doc.querySelectorAll('style')).map((style) => style.textContent ?? '').join('')
  let best: Declared | null = null
  let order = 0
  for (const [, selectorText, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    order += 1
    if (selectorText!.trim().startsWith('@')) continue
    const value = body!
      .split(';')
      .map((declaration) => declaration.split(':'))
      .filter(([name]) => name?.trim() === property)
      .map(([, ...rest]) => rest.join(':').trim())
      .pop()
    if (!value) continue
    for (const selector of selectorText!.split(',').map((part) => part.trim())) {
      if (!element.matches(selector)) continue
      const candidate = { value, specificity: specificity(selector), order }
      if (!best || candidate.specificity > best.specificity
        || (candidate.specificity === best.specificity && candidate.order >= best.order)) {
        best = candidate
      }
    }
  }
  return best?.value ?? null
}

const forced = (value: string | null) => value === 'page' || value === 'always'

function parse(html: string): { doc: Document; labels: Element[] } {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  return { doc, labels: Array.from(doc.querySelectorAll('section.label')) }
}

/**
 * Страниц по принудительным разрывам: 1 + число «швов» с разрывом. Шов k —
 * граница перед этикеткой k; шов N — после последней. Разрыв после последней
 * этикетки и есть лишняя пустая страница.
 */
function forcedPageCount(html: string): number {
  const { doc, labels } = parse(html)
  const breakBefore = (label: Element) =>
    forced(resolved(doc, label, 'break-before')) || forced(resolved(doc, label, 'page-break-before'))
  const breakAfter = (label: Element) =>
    forced(resolved(doc, label, 'break-after')) || forced(resolved(doc, label, 'page-break-after'))
  let seams = 0
  for (let k = 0; k <= labels.length; k += 1) {
    const prev = labels[k - 1]
    const next = labels[k]
    if ((prev && breakAfter(prev)) || (next && breakBefore(next))) seams += 1
  }
  return 1 + seams
}

describe('WMS-583 печать QR из окна «Проверка перед печатью»', () => {
  it('один QR — одна этикетка: после последней этикетки нет принудительного разрыва страницы', () => {
    const { doc, labels } = parse(buildFbsImagePrintDocument([qr], 1, size58))
    expect(labels).toHaveLength(1)
    const last = labels[0]!
    expect(resolved(doc, last, 'break-after')).not.toBe('page')
    expect(resolved(doc, last, 'page-break-after')).not.toBe('always')
    expect(forcedPageCount(buildFbsImagePrintDocument([qr], 1, size58))).toBe(1)
  })

  it('QR короба — тоже одна этикетка', () => {
    expect(forcedPageCount(buildFbsImagePrintDocument([boxQr], 1, size58))).toBe(1)
  })

  it('пачка и копии: этикеток ровно столько, сколько макетов × копий, без пустой в конце', () => {
    expect(forcedPageCount(buildFbsImagePrintDocument([qr, boxQr], 1, size58))).toBe(2)
    expect(forcedPageCount(buildFbsImagePrintDocument([qr], 2, size58))).toBe(2)
    expect(forcedPageCount(buildFbsImagePrintDocument([qr, boxQr], 3, size58))).toBe(6)
  })

  it.each(LABEL_SIZES)('$id: высота этикетки — размер наклейки, как у автопечати, но не больше листа', (size) => {
    const html = buildFbsImagePrintDocument([qr], 1, size)
    const { doc, labels } = parse(html)
    expect(resolved(doc, labels[0]!, 'height')).toBe(`${size.heightMm}mm`)
    expect(resolved(doc, labels[0]!, 'max-height')).toBe('100vh')
    // Вид этикетки прежний: страница выбранного размера без полей, картинка вписана по ширине с полем 1 мм.
    expect(html).toContain(`@page{size:${size.widthMm}mm ${size.heightMm}mm;margin:0}`)
    expect(resolved(doc, labels[0]!, 'width')).toBe('100%')
    expect(resolved(doc, labels[0]!, 'padding')).toBe('1mm')
    expect(html).toContain('.label img{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;image-rendering:auto}')
  })

  it('контроль счётчика: документ автопечати QR при скане (WMS-514) тоже даёт одну страницу на этикетку', () => {
    expect(forcedPageCount(buildMarkingTapeDocument([buildWbOrderQrLabelHtml('blob:qr-first')], size58))).toBe(1)
    expect(forcedPageCount(buildMarkingTapeDocument(
      [buildWbOrderQrLabelHtml('blob:qr-first'), buildWbOrderQrLabelHtml('blob:qr-box')],
      size58,
    ))).toBe(2)
  })

  it('порядок картинок и копий сохраняется, число копий ограничено 1…99, печать запускается скриптом', () => {
    const html = buildFbsImagePrintDocument([qr, boxQr], 2, size58)
    expect([...html.matchAll(/<img src="([^"]+)"/g)].map((match) => match[1]))
      .toEqual(['blob:qr-first', 'blob:qr-first', 'blob:qr-box', 'blob:qr-box'])
    expect(parse(buildFbsImagePrintDocument([qr], 0, size58)).labels).toHaveLength(1)
    expect(parse(buildFbsImagePrintDocument([qr], 100, size58)).labels).toHaveLength(99)
    expect(html).toContain('window.print()')
  })
})
