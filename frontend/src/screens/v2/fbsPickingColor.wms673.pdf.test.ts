// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { buildFbsPickingListPrintHtml, fbsBuildPickingRows } from './fbsUx'
import { wms673Order, wms673PrintMeta } from './wms673PrintFixtures'
import { renderGeometry, renderPdf, pdfTable, pdfText, pdfWord, assertSamePdfRow, assertPdfTableWithinColumns } from './wms673PrintRenderer'

const LONG_COLOR = 'Красный & синий, шоколадный трюфель, тёмный бордовый с серебристым рисунком'
function htmlFor(count: number) {
  const orders = Array.from({ length: count }, (_, i) => {
    const one = wms673Order(`order-${i}`, `product-${i}`, i === 2 ? null : `${LONG_COLOR} ЦВЕТ${String(i).padStart(3, '0')}`, i)
    one.product.name = `ROW-${String(i).padStart(3, '0')} Очень длинное название товара с несколькими словами`
    one.product.size = i === 1 ? '46' : i === 2 ? null : 'Универсальный'
    one.product.seller_article = `LONG-IDENTIFIER-${i}-WMS673-ABCDEFGHIJKLMNOPQRST`
    one.inventory.locations[0].code = `Длинная-ячейка-673-${i} · Палета P-673 › Короб B-673`
    return one
  })
  return buildFbsPickingListPrintHtml({ ...wms673PrintMeta, rows: fbsBuildPickingRows(orders, false).rows })
}

describe.skipIf(!process.env.WMS673_RENDERED_ARTIFACTS_DIR)('WMS-673 digital print controls', () => {
  it('C7 control: externally rendered actual PDF is as A4 landscape before color implementation', async () => {
    const { pdf, textReport } = await renderPdf(htmlFor(1), 'baseline-control')
    expect(pdf.getPageCount()).toBe(1)
    expect(pdf.getPage(0).getWidth()).toBeCloseTo(841.89, 0)
    expect(pdf.getPage(0).getHeight()).toBeCloseTo(595.28, 0)
    expect(textReport.pages[0].words.map((w) => w.text).join(' ')).toContain('ROW-000')
  }, 120_000)
})

describe.skipIf(!process.env.WMS673_RENDERED_ARTIFACTS_DIR)('WMS-673 business RED PDF contract', () => {
  it('C7: real renderer keeps size657 fixed geometry and complete color within eleven columns', async () => {
    const html = htmlFor(1)
    const geometry = await renderGeometry(html)
    // Render the actual PDF before asserting the missing business column, so a
    // renderer failure cannot be misreported as a product RED.
    const { pdf, textReport } = await renderPdf(html, 'baseline-long-row')
    expect(geometry.rowCellCounts, 'missing separate color column').toEqual([11])
    expect(geometry.tableWithinPage).toBe(true)
    expect(geometry.headersAligned).toBe(true)
    expect(geometry.allCellContentFits).toBe(true)
    expect(geometry.neighboringCellsDoNotOverlap).toBe(true)
    expect(geometry.sizeStyle).toEqual({ width: '78px', fontSize: '20px' })
    expect(geometry.fixedWidths).toEqual([
      { className: 'number', width: '28px' }, { className: 'image', width: '54px' },
      { className: 'sticker', width: '116px' }, { className: 'quantity', width: '62px' }, { className: 'quantity', width: '62px' },
    ])
    expect(geometry.sizeCells[0]).toMatchObject({ text: 'Универсальный', linesWithinCell: true })
    expect(geometry.sizeCells[0].lineCount).toBeGreaterThanOrEqual(2)
    expect(geometry.colorCells[0]).toEqual({ text: `${LONG_COLOR} ЦВЕТ000`, linesWithinCell: true })
    expect(pdf.getPage(0).getWidth()).toBeCloseTo(841.89, 0)
    expect(pdf.getPage(0).getHeight()).toBeCloseTo(595.28, 0)
    const table = pdfTable(textReport, geometry); assertPdfTableWithinColumns(table)
    const anchor = pdfText(table, 2, 'ROW-000 Очень длинное название товара с несколькими словами')
    const identifier = pdfText(table, 2, 'LONG-IDENTIFIER-0-WMS673-ABCDEFGHIJKLMNOPQRST · WB 1673 · WB-CODE-product-0')
    assertSamePdfRow([anchor, identifier], [
      { label: 'размер', match: pdfText(table, 3, 'Универсальный') },
      { label: 'цвет', match: pdfText(table, 4, `${LONG_COLOR} ЦВЕТ000`) },
      { label: 'тара', match: pdfText(table, 5, 'Длинная-ячейка-673-0 · Палета P-673 › Короб B-673: 9') },
      { label: 'заказ', match: pdfText(table, 6, '№673000') },
      { label: 'стикер', match: pdfText(table, 7, 'S6730000') },
      { label: 'план', match: pdfWord(table, 8, '1') },
      { label: 'факт', match: pdfText(table, 9, '0/1') },
    ])
  }, 120_000)
  it('C7/C11: multipage PDF repeats headers, preserves every row/color/size and page boundary', async () => {
    const html = htmlFor(34), geometry = await renderGeometry(html)
    const { pdf, textReport } = await renderPdf(html, 'baseline-multipage')
    expect(pdf.getPageCount()).toBeGreaterThan(1)
    expect(geometry.rowCellCounts, 'all rows require eleven cells').toEqual(Array(34).fill(11))
    expect(geometry.rowsDoNotOverlap).toBe(true)
    expect(geometry.allCellContentFits).toBe(true)
    const table = pdfTable(textReport, geometry); assertPdfTableWithinColumns(table)
    for (const page of pdf.getPages()) {
      expect(page.getWidth()).toBeCloseTo(841.89, 0); expect(page.getHeight()).toBeCloseTo(595.28, 0)
    }
    for (let i = 0; i < 34; i++) {
      const anchor = pdfText(table, 2, `ROW-${String(i).padStart(3, '0')} Очень длинное название товара с несколькими словами`)
      const identifier = pdfText(table, 2, `LONG-IDENTIFIER-${i}-WMS673-ABCDEFGHIJKLMNOPQRST · WB 1673 · WB-CODE-product-${i}`)
      assertSamePdfRow([anchor, identifier], [
        { label: `цвет ${i}`, match: pdfText(table, 4, i === 2 ? '—' : `${LONG_COLOR} ЦВЕТ${String(i).padStart(3, '0')}`) },
        { label: `размер ${i}`, match: pdfText(table, 3, i === 1 ? '46' : i === 2 ? '—' : 'Универсальный', i < 3 ? 0 : i - 2) },
        { label: `заказ ${i}`, match: pdfText(table, 6, `№${673000 + i}`) },
        { label: `стикер ${i}`, match: pdfText(table, 7, `S673${String(i).padStart(4, '0')}`) },
      ])
    }
  }, 120_000)
})

// jsdom checks the actual print input/CSS, not layout or actual PDF pages.
// Physical geometry assertions above remain unchanged and explicitly deferred.
describe('WMS-673 PDF input contract without browser execution', () => {
  it('C7 print input preserves A4 landscape, 10mm margins, fixed size657 widths/font', () => {
    const document = new DOMParser().parseFromString(htmlFor(1), 'text/html')
    const css = document.querySelector('style')!.textContent!
    expect(css).toMatch(/@page\s*\{\s*size:\s*A4 landscape;\s*margin:\s*10mm;/)
    expect(css).toMatch(/\.size\s*\{[^}]*width:\s*78px;/)
    expect(css).toMatch(/td\.size\s*\{[^}]*font-size:\s*20px;/)
    expect(document.querySelector('td.size')!.textContent).toBe('Универсальный')
  })
  it('C7/C11 long color survives the real API-to-print builder, next to size; size wrapping remains required', () => {
    const document = new DOMParser().parseFromString(htmlFor(1), 'text/html')
    const headers = [...document.querySelectorAll('thead th')].map(th => th.textContent)
    expect(headers.slice(3, 6)).toEqual(['Размер', 'Цвет', 'Ячейка / тара'])
    expect(document.querySelector('tbody tr')!.children[4].textContent).toBe(`${LONG_COLOR} ЦВЕТ000`)
    expect(document.querySelector('style')!.textContent).not.toMatch(/\.size\s*\{[^}]*white-space:\s*nowrap/)
  })
})
