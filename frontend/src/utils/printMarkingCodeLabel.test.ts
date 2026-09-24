import { readFileSync } from 'node:fs'

import {
  BarcodeFormat,
  BinaryBitmap,
  DecodeHintType,
  HybridBinarizer,
  MultiFormatReader,
  RGBLuminanceSource,
} from '@zxing/library'
import * as bwipjs from 'bwip-js'
import { PNG } from 'pngjs'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LABEL_SIZES, resolvePrintPageSize } from './labelSize'
import { formatGtinDisplay, maskCisTail, parseGs1Cis } from './parseGs1Cis'
import {
  buildDataMatrixRenderOptions,
  buildCzArtifactLabelHtml,
  buildCzLabelHtml,
  buildMarkingTapeDocument,
  buildWbOrderQrLabelHtml,
  printHtmlInIframe,
  resolveCzArtifactTapeCodeIds,
} from './printMarkingCodeLabel'
import type { MarkingTapeUnitInput } from './printMarkingCodeLabel'

const SAMPLE_CIS = `01${'04600000000001'}21${'A'.repeat(20)}0001`
const LONG_GS1_CIS = `0104630321689835215TVsOggEdo6!!\u001d91ABCD\u001d92${'x'.repeat(44)}`
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

type RasterGeometry = {
  width: number
  height: number
  modulePitchX: number
  modulePitchY: number
  quietZone: [number, number, number, number]
  decodedText: string | null
}

function measureDataMatrixRaster(buffer: Uint8Array, decode = true): RasterGeometry {
  const png = PNG.sync.read(Buffer.from(buffer))
  const isBlack = (x: number, y: number) => {
    const offset = (y * png.width + x) * 4
    return png.data[offset + 3]! > 128 && png.data[offset]! < 128
  }

  let minX = png.width
  let minY = png.height
  let maxX = -1
  let maxY = -1
  for (let y = 0; y < png.height; y += 1) {
    for (let x = 0; x < png.width; x += 1) {
      if (!isBlack(x, y)) continue
      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x)
      maxY = Math.max(maxY, y)
    }
  }

  const transitionRuns = (horizontal: boolean): number[] => {
    const start = horizontal ? minX : minY
    const end = horizontal ? maxX : maxY
    const fixed = horizontal ? minY : maxX
    const valueAt = (position: number) =>
      horizontal ? isBlack(position, fixed) : isBlack(fixed, position)
    const runs: number[] = []
    let previous = valueAt(start)
    let runStart = start
    for (let position = start + 1; position <= end; position += 1) {
      const value = valueAt(position)
      if (value === previous) continue
      runs.push(position - runStart)
      previous = value
      runStart = position
    }
    runs.push(end + 1 - runStart)
    return runs
  }

  const pixels = new Int32Array(png.width * png.height)
  for (let index = 0; index < pixels.length; index += 1) {
    const offset = index * 4
    pixels[index] =
      (png.data[offset]! << 16) |
      (png.data[offset + 1]! << 8) |
      png.data[offset + 2]!
  }
  let decodedText: string | null = null
  if (decode) {
    const reader = new MultiFormatReader()
    const hints = new Map<DecodeHintType, unknown>()
    hints.set(DecodeHintType.POSSIBLE_FORMATS, [BarcodeFormat.DATA_MATRIX])
    hints.set(DecodeHintType.TRY_HARDER, true)
    reader.setHints(hints)
    decodedText = reader.decode(
      new BinaryBitmap(
        new HybridBinarizer(new RGBLuminanceSource(pixels, png.width, png.height)),
      ),
    ).getText()
  }

  return {
    width: png.width,
    height: png.height,
    modulePitchX: Math.min(...transitionRuns(true)),
    modulePitchY: Math.min(...transitionRuns(false)),
    quietZone: [minX, minY, png.width - maxX - 1, png.height - maxY - 1],
    decodedText,
  }
}

describe('WMS-519 Data Matrix raster geometry', () => {
  it.each([
    ['short', SAMPLE_CIS],
    ['long GS1 with separators and crypto tail', LONG_GS1_CIS],
  ])('keeps square modules and a two-module quiet zone for %s KIZ', async (_name, cis) => {
    const options = buildDataMatrixRenderOptions(cis)
    const geometry = measureDataMatrixRaster(await bwipjs.toBuffer(options))

    expect(options).not.toHaveProperty('height')
    expect(geometry.width).toBe(geometry.height)
    expect(geometry.modulePitchX).toBe(geometry.modulePitchY)
    expect(geometry.quietZone).toEqual([
      geometry.modulePitchX * 2,
      geometry.modulePitchY * 2,
      geometry.modulePitchX * 2,
      geometry.modulePitchY * 2,
    ])
    expect(geometry.decodedText).toBe(cis)
  })

  it('guards the exact bwip-js option that caused the production distortion', async () => {
    const distorted = measureDataMatrixRaster(
      await bwipjs.toBuffer({
        bcid: 'datamatrix',
        text: LONG_GS1_CIS,
        scale: 4,
        height: 12,
        includetext: false,
      }),
      false,
    )
    const corrected = measureDataMatrixRaster(
      await bwipjs.toBuffer(buildDataMatrixRenderOptions(LONG_GS1_CIS)),
    )

    expect(distorted.modulePitchX).toBe(8)
    expect(distorted.modulePitchY).toBe(4)
    expect(corrected.modulePitchX).toBe(corrected.modulePitchY)
  })
})

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

describe('WMS-519 print page contract', () => {
  it.each(LABEL_SIZES.flatMap((size) => [
    [size.id, resolvePrintPageSize(size, 'portrait')],
    [`${size.id}-landscape`, resolvePrintPageSize(size, 'landscape')],
  ]))('keeps one label section inside the existing %s page', (_name, size) => {
    const document = buildMarkingTapeDocument(
      [buildCzLabelHtml(LONG_GS1_CIS, MATRIX_STUB)],
      size,
    )

    expect(document).toContain(`@page { size: ${size.widthMm}mm ${size.heightMm}mm; margin: 0; }`)
    expect(document).toContain(`width: ${size.widthMm}mm`)
    expect(document).toContain(`height: ${size.heightMm}mm`)
    expect(document.match(/data-testid="marking-thermal-label"/g)).toHaveLength(1)
    expect(document).toContain('.label:last-child { page-break-after: auto; break-after: auto; }')
    expect(document).toContain('object-fit: contain')
  })
})

describe('WMS-519 shared renderer call paths', () => {
  const source = (relativePath: string) =>
    readFileSync(new URL(relativePath, import.meta.url), 'utf8')

  it('routes Honest Sign and inbound scan/row/all reprints through one dialog', () => {
    const reprintDialog = source('../components/KizReprintDialog.tsx')
    expect(reprintDialog).toContain("import { printMarkingCodeLabels } from '../utils/printMarkingCodeLabel'")
    expect(reprintDialog.match(/printMarkingCodeLabels\(/g)).toHaveLength(2)
    expect(reprintDialog).not.toContain("import('bwip-js')")

    for (const screen of [
      source('../screens/shared/HonestSignScreen.tsx'),
      source('../screens/ff/FfInboundRequestView.tsx'),
    ]) {
      expect(screen).toContain('KizReprintDialog')
    }
  })

  it('routes catalog, packaging and FBS reprints through MarkingPrintDialog', () => {
    const hook = source('./useMarkingCodePrint.tsx')
    expect(hook).toContain("from '../components/MarkingPrintDialog'")
    expect(hook).toContain('<MarkingPrintDialog')

    for (const screen of [
      source('../screens/shared/HonestSignScreen.tsx'),
      source('../screens/ff/FfPackagingPage.tsx'),
      source('../screens/v2/FfFbsSupplyWorkspace.tsx'),
    ]) {
      expect(screen).toContain('useMarkingCodePrint')
      expect(screen).toContain('markingPrintDialog')
    }

    const printDialog = source('../components/MarkingPrintDialog.tsx')
    expect(printDialog).toContain('printCzArtifactTape(')
    expect(printDialog).toContain('buildMarkingTapeSections(')
    expect(printDialog).not.toContain("import('bwip-js')")
  })

  it('keeps the public exact-KIZ entry point on the shared tape renderer', () => {
    const renderer = source('./printMarkingCodeLabel.ts')
    expect(renderer).toContain('export async function printMarkingCodeLabels(')
    expect(renderer).toContain('await printMarkingCodeTape(units, layout, options.productLabel')
    expect(renderer).toContain('matrixByCis.set(cis, await renderDataMatrixDataUrl(cis))')
  })
})
