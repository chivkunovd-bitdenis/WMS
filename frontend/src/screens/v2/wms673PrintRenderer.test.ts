// Reader unit checks only; these synthetic coordinates do not prove real PDF layout.
import { describe, expect, it } from 'vitest'
import { pdfTable, assertPdfTableWithinColumns } from './wms673PrintRenderer'

const margin = 10 * 72 / 25.4
const geometry = {
  tableBounds: { left: 0, right: 550 },
  columnBounds: Array.from({ length: 11 }, (_, i) => ({ left: i * 50, right: (i + 1) * 50 })),
  allCellContentFits: true, headersAligned: true, neighboringCellsDoNotOverlap: true,
  rowCellCounts: [11], rowsDoNotOverlap: true, tableWithinPage: true,
  sizeStyle: null, fixedWidths: [], colorCells: [], sizeCells: [],
}
function word(text: string, x: number, y: number, width = 10) {
  return { pageIndex: 0, text, xMin: x, xMax: x + width, yMin: y, yMax: y + 8 }
}
function report(words: ReturnType<typeof word>[]) {
  return { pages: [{ width: 550 + margin * 2, height: 595.28,
    words: [word('РАЗМЕР', margin + 205, 20), ...words] }] }
}

describe('WMS-673 offline PDF table reader with WMS-725 layout', () => {
  it('requires eleven actual column bounds after removal of row numbering', () => {
    expect(pdfTable(report([]), geometry).pages[0].columns).toHaveLength(11)
    expect(() => pdfTable(report([]), { ...geometry,
      columnBounds: [...geometry.columnBounds, { left: 550, right: 600 }] })).toThrow('одиннадцати колонок')
  })

  it('excludes the separate total and footer while retaining every table word', () => {
    const table = pdfTable(report([
      word('ROW-000', margin + 55, 50), word('1', margin + 405, 50),
      word('Общее', margin, 100, 30), word('количество:', margin + 35, 100, 55),
      word('1', margin + 95, 100), word('шт.', margin + 110, 100),
      word('Сформировано', margin, 130, 65),
    ]), geometry)
    expect(table.pages[0].columns.flatMap((column) => column.words.map((w) => w.text))).toEqual(['ROW-000', '1'])
    expect(table.pages[0].columns[9].words).toEqual([])
    expect(() => assertPdfTableWithinColumns(table)).not.toThrow()
  })

  it('does not hide a product bearing the total label or content crossing a column', () => {
    const table = pdfTable(report([
      word('Общее', margin + 55, 50, 20), word('количество:', margin + 77, 50, 15),
      word('OVERFLOW', margin + 145, 70, 15),
    ]), geometry)
    expect(table.pages[0].columns.flatMap((column) => column.words.map((w) => w.text))).toEqual(['Общее', 'количество:', 'OVERFLOW'])
    expect(() => assertPdfTableWithinColumns(table)).toThrow('вышло за границу колонки')
  })
})
