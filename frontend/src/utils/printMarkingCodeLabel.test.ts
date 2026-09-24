import { afterEach, describe, expect, it, vi } from 'vitest'

import { formatGtinDisplay, maskCisTail, parseGs1Cis } from './parseGs1Cis'
import {
  buildCzArtifactLabelHtml,
  buildCzLabelHtml,
  buildMarkingTapeDocument,
  buildWbOrderQrLabelHtml,
  printHtmlInIframe,
  resolveCzArtifactTapeCodeIds,
} from './printMarkingCodeLabel'
import type { MarkingTapeUnitInput } from './printMarkingCodeLabel'

const SAMPLE_CIS = `01${'04600000000001'}21${'A'.repeat(20)}0001`
const MATRIX_STUB = 'data:image/png;base64,stub'

afterEach(() => {
  vi.unstubAllGlobals()
})

function stubIframePrint(print: () => void): void {
  const iframe: {
    onload: (() => void) | null
    onerror: (() => void) | null
    contentWindow: { focus: () => void; print: () => void }
    contentDocument: { querySelectorAll: () => [] }
    style: Record<string, string>
    setAttribute: () => void
    srcdoc: string
  } = {
    onload: null,
    onerror: null,
    contentWindow: { focus: () => undefined, print },
    contentDocument: { querySelectorAll: () => [] },
    style: {},
    setAttribute: () => undefined,
    get srcdoc() { return '' },
    set srcdoc(_html: string) { queueMicrotask(() => this.onload?.()) },
  }
  vi.stubGlobal('window', {
    setTimeout: (callback: () => void, delay?: number) => {
      if ((delay ?? 0) < 20_000) queueMicrotask(callback)
      return 1
    },
    clearTimeout: () => undefined,
  })
  vi.stubGlobal('document', {
    createElement: () => iframe,
    body: { appendChild: () => iframe, removeChild: () => undefined },
  })
}

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

describe('printHtmlInIframe launch acknowledgement', () => {
  it('resolves only after the browser print form is invoked', async () => {
    const print = vi.fn()
    stubIframePrint(print)
    await printHtmlInIframe('<html></html>')
    expect(print).toHaveBeenCalledOnce()
  })

  it('rejects when the browser cannot launch the print form', async () => {
    stubIframePrint(() => { throw new Error('print blocked') })
    await expect(printHtmlInIframe('<html></html>')).rejects.toThrow('Не удалось запустить печать КИЗ.')
  })

  it('never invokes a late iframe load after the launch timeout', async () => {
    const callbacks: Array<() => void> = []
    const print = vi.fn()
    const iframe = {
      onload: null as (() => void) | null,
      onerror: null as (() => void) | null,
      contentWindow: { focus: () => undefined, print },
      contentDocument: { querySelectorAll: () => [] },
      style: {} as Record<string, string>,
      setAttribute: () => undefined,
      srcdoc: '',
    }
    vi.stubGlobal('window', {
      setTimeout: (callback: () => void) => {
        callbacks.push(callback)
        return callbacks.length
      },
      clearTimeout: () => undefined,
    })
    vi.stubGlobal('document', {
      createElement: () => iframe,
      body: { appendChild: () => iframe, removeChild: () => undefined },
    })

    const printing = printHtmlInIframe('<html></html>')
    callbacks[0]?.()
    await expect(printing).rejects.toThrow('таймаут')
    iframe.onload?.()
    for (const callback of callbacks.slice(1)) callback()
    expect(print).not.toHaveBeenCalled()
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
    expect(section).not.toContain('cz-brand')
    expect(section).not.toContain('cz-field--gtin')
    expect(section).not.toContain('cz-field--serial')
  })

  it('artifact tape CSS scales image to full label box', () => {
    const doc = buildMarkingTapeDocument([buildCzArtifactLabelHtml('data:image/png;base64,abc')])
    expect(doc).toContain('.cz-artifact-img {')
    expect(doc).toContain('width: 100%')
    expect(doc).toContain('height: 100%')
    expect(doc).toContain('object-fit: contain')
    expect(doc).not.toContain('rotate(90deg)')
    expect(doc).toContain('cz-label-artifact-img')
  })

  // TC-NEW-CZ-NATIVE-PDF-01 — лента только из PDF-артефактов → native PDF path.
  it('resolves artifact code ids for cz-only tape with duplicates', () => {
    const units: MarkingTapeUnitInput[] = [
      { cis: 'A', codeId: 'id-a', hasLabelArtifact: true },
      { cis: 'B', codeId: 'id-b', hasLabelArtifact: true },
    ]
    const ids = resolveCzArtifactTapeCodeIds(units, {
      units: [{ block: 'cz', copies: 2 }],
    })
    expect(ids).toEqual(['id-a', 'id-a', 'id-b', 'id-b'])
  })

  it('returns null for mixed cz+label tape', () => {
    const units: MarkingTapeUnitInput[] = [
      { cis: 'A', codeId: 'id-a', hasLabelArtifact: true, productLabel: { barcode: '1', sku_code: 's', product_name: 'n' } },
    ]
    const ids = resolveCzArtifactTapeCodeIds(units, {
      units: [
        { block: 'cz', copies: 1 },
        { block: 'label', copies: 1 },
      ],
    })
    expect(ids).toBeNull()
  })

  it('returns null when cz block lacks artifact', () => {
    const units: MarkingTapeUnitInput[] = [{ cis: 'A', codeId: 'id-a', hasLabelArtifact: false }]
    const ids = resolveCzArtifactTapeCodeIds(units, { units: [{ block: 'cz', copies: 1 }] })
    expect(ids).toBeNull()
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

describe('buildWbOrderQrLabelHtml', () => {
  it('prints the same one-based position used by the picking list', () => {
    const section = buildWbOrderQrLabelHtml(MATRIX_STUB, 7)
    expect(section).toContain('data-testid="fbs-order-qr-position"')
    expect(section).toContain('№7')
  })
})
