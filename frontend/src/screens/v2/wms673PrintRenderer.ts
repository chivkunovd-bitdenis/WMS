// Offline PDF reader only: never starts a browser or installs dependencies.
// Supply externally rendered artifacts keyed by SHA256 of the exact production
// HTML. Missing artifacts are a resource/authorization block, never product RED.
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { PDFDocument } from 'pdf-lib'

type GeometryReport = {
  allCellContentFits: boolean
  columnBounds: Array<{ left: number; right: number }>
  headersAligned: boolean
  neighboringCellsDoNotOverlap: boolean
  rowCellCounts: number[]
  rowsDoNotOverlap: boolean
  tableBounds: { left: number; right: number }
  tableWithinPage: boolean
  sizeStyle: { width: string; fontSize: string } | null
  fixedWidths: Array<{ className: string; width: string }>
  colorCells: Array<{ text: string; linesWithinCell: boolean }>
  sizeCells: Array<{ lineCount: number; linesWithinCell: boolean; text: string }>
}

type PdfWord = {
  pageIndex: number
  text: string
  xMin: number
  yMin: number
  xMax: number
  yMax: number
}

type PdfPageText = {
  width: number
  height: number
  words: PdfWord[]
}

type PdfTextReport = { pages: PdfPageText[] }
type PdfColumn = { left: number; right: number; words: PdfWord[] }
type PdfTablePage = PdfPageText & { columns: PdfColumn[] }
type PdfTable = { pages: PdfTablePage[] }
type PdfTextMatch = { pageIndex: number; words: PdfWord[] }

function artifactPath(html: string, extension: string) {
  const dir = process.env.WMS673_RENDERED_ARTIFACTS_DIR
  if (!dir) throw new Error('BLOCKED: real PDF/geometry artifacts unavailable; browser execution prohibited in this run')
  const key = createHash('sha256').update(html).digest('hex')
  const prefix = join(dir, key)
  if (readFileSync(`${prefix}.html`, 'utf8') !== html) throw new Error('Rendered HTML does not match the production input')
  return `${prefix}.${extension}`
}
async function renderGeometry(html: string): Promise<GeometryReport> {
  return JSON.parse(readFileSync(artifactPath(html, 'geometry.json'), 'utf8')) as GeometryReport
}
function decodeXmlText(value: string) {
  const named: Record<string, string> = { amp: '&', apos: "'", gt: '>', lt: '<', quot: '"' }
  return value.replace(/&(#x[0-9a-f]+|#\d+|amp|apos|gt|lt|quot);/gi, (_match, entity: string) => {
    if (entity[0] !== '#') return named[entity.toLowerCase()] ?? _match
    const radix = entity[1]?.toLowerCase() === 'x' ? 16 : 10
    const digits = radix === 16 ? entity.slice(2) : entity.slice(1)
    return String.fromCodePoint(Number.parseInt(digits, radix))
  })
}

function parsePdfTextReport(xml: string): PdfTextReport {
  const pages: PdfPageText[] = []
  const pagePattern = /<page\b[^>]*width="([\d.]+)"[^>]*height="([\d.]+)"[^>]*>([\s\S]*?)<\/page>/g
  for (const [pageIndex, match] of [...xml.matchAll(pagePattern)].entries()) {
    const words: PdfWord[] = []
    const wordPattern = /<word\b[^>]*xMin="([\d.-]+)"[^>]*yMin="([\d.-]+)"[^>]*xMax="([\d.-]+)"[^>]*yMax="([\d.-]+)"[^>]*>([\s\S]*?)<\/word>/g
    for (const word of match[3]!.matchAll(wordPattern)) {
      words.push({
        pageIndex,
        text: decodeXmlText(word[5]!),
        xMin: Number(word[1]),
        yMin: Number(word[2]),
        xMax: Number(word[3]),
        yMax: Number(word[4]),
      })
    }
    pages.push({ width: Number(match[1]), height: Number(match[2]), words })
  }
  if (!pages.length) throw new Error('pdftotext не вернул страницы с координатами')
  return { pages }
}

// `pdftotext -layout` interleaves wrapped baselines from neighboring columns.
// Coordinates keep every fragment tied to its actual PDF column and row.
function pdfTable(report: PdfTextReport, geometry: GeometryReport): PdfTable {
  const geometryWidth = geometry.tableBounds.right - geometry.tableBounds.left
  if (geometryWidth <= 0 || geometry.columnBounds.length !== 11) {
    throw new Error('Браузер не вернул границы одиннадцати колонок таблицы')
  }
  const marginPoints = 10 * 72 / 25.4
  return {
    pages: report.pages.map((page) => {
      const printableWidth = page.width - marginPoints * 2
      const columns = geometry.columnBounds.map((bounds) => ({
        left: marginPoints + (bounds.left - geometry.tableBounds.left) / geometryWidth * printableWidth,
        right: marginPoints + (bounds.right - geometry.tableBounds.left) / geometryWidth * printableWidth,
        words: [] as PdfWord[],
      }))
      const header = page.words.find((word) => word.text === 'РАЗМЕР')
      if (!header) throw new Error(`На странице ${(page.words[0]?.pageIndex ?? 0) + 1} PDF нет заголовка «РАЗМЕР»`)
      const footerTop = page.words.find((word) => word.text === 'Сформировано')?.yMin ?? Number.POSITIVE_INFINITY
      // WMS-725 adds a summary outside the table. Identify its label at the
      // left page margin, so a product containing the same words still counts
      // as table content and remains subject to the existing bounds checks.
      const totalTop = page.words.find((word) => word.text === 'Общее'
        && Math.abs(word.xMin - marginPoints) < 2
        && word.yMin > header.yMax && word.yMax < footerTop
        && page.words.some((next) => next.text === 'количество:'
          && next.xMin > word.xMax && Math.abs(next.yMin - word.yMin) < 1))?.yMin
        ?? Number.POSITIVE_INFINITY
      const tableEnd = Math.min(footerTop, totalTop)
      for (const word of page.words) {
        const centerX = (word.xMin + word.xMax) / 2
        if (word.yMin <= header.yMax + 1 || word.yMax >= tableEnd - 1) continue
        const column = columns.find((bounds) => centerX >= bounds.left - 0.5 && centerX <= bounds.right + 0.5)
        if (column) column.words.push(word)
      }
      for (const column of columns) column.words.sort((a, b) => a.yMin - b.yMin || a.xMin - b.xMin)
      return { ...page, columns }
    }),
  }
}

function compactPdfText(value: string) {
  return value.replace(/\s+/g, '')
}

function pdfTextMatches(table: PdfTable, columnIndex: number, expected: string): PdfTextMatch[] {
  const target = compactPdfText(expected)
  const matches: PdfTextMatch[] = []
  for (const page of table.pages) {
    const words = page.columns[columnIndex]?.words ?? []
    for (let start = 0; start < words.length; start += 1) {
      let value = ''
      for (let end = start; end < words.length; end += 1) {
        value += compactPdfText(words[end]!.text)
        if (value === target) {
          matches.push({ pageIndex: words[start]!.pageIndex, words: words.slice(start, end + 1) })
          break
        }
        if (!target.startsWith(value)) break
      }
    }
  }
  return matches
}

function pdfText(table: PdfTable, columnIndex: number, expected: string, occurrence = 0) {
  const matches = pdfTextMatches(table, columnIndex, expected)
  if (matches.length <= occurrence) {
    throw new Error(`PDF потерял «${expected}» в колонке ${columnIndex + 1}: найдено ${matches.length}, ожидалось не меньше ${occurrence + 1}`)
  }
  return matches[occurrence]!
}

function pdfWord(table: PdfTable, columnIndex: number, expected: string, occurrence = 0) {
  const matches = table.pages.flatMap((page) => page.columns[columnIndex]!.words
    .filter((word) => compactPdfText(word.text) === compactPdfText(expected))
    .map((word) => ({ pageIndex: word.pageIndex, words: [word] })))
  if (matches.length <= occurrence) {
    throw new Error(`PDF потерял отдельное значение «${expected}» в колонке ${columnIndex + 1}`)
  }
  return matches[occurrence]!
}

function textBounds(matches: PdfTextMatch[]) {
  const words = matches.flatMap((match) => match.words)
  return {
    pageIndex: matches[0]!.pageIndex,
    yMin: Math.min(...words.map((word) => word.yMin)),
    yMax: Math.max(...words.map((word) => word.yMax)),
  }
}

function assertSamePdfRow(anchorParts: PdfTextMatch[], values: Array<{ label: string; match: PdfTextMatch }>) {
  const anchor = textBounds(anchorParts)
  const anchorCenter = (anchor.yMin + anchor.yMax) / 2
  for (const { label, match } of values) {
    const bounds = textBounds([match])
    if (bounds.pageIndex !== anchor.pageIndex) throw new Error(`${label} перешло на другую страницу PDF`)
    const center = (bounds.yMin + bounds.yMax) / 2
    if (Math.abs(center - anchorCenter) > 4) {
      throw new Error(`${label} смещено в другую строку PDF: центр ${center}, ожидаемый центр ${anchorCenter}`)
    }
  }
}

function assertPdfTableWithinColumns(table: PdfTable) {
  for (const page of table.pages) {
    for (const [columnIndex, column] of page.columns.entries()) {
      for (const word of column.words) {
        if (word.xMin < column.left - 1 || word.xMax > column.right + 1) {
          throw new Error(`«${word.text}» вышло за границу колонки ${columnIndex + 1} PDF`)
        }
        if (word.xMin < -1 || word.xMax > page.width + 1 || word.yMin < -1 || word.yMax > page.height + 1) {
          throw new Error(`«${word.text}» вышло за границу страницы PDF`)
        }
      }
    }
  }
}

async function renderPdf(html: string, _evidenceName = 'picking-list') {
  const output = artifactPath(html, 'pdf')
  // Copy Node Buffer bytes into this test realm's Uint8Array for pdf-lib/jsdom.
  const pdf = await PDFDocument.load(new Uint8Array(readFileSync(output)))
  const textReport = parsePdfTextReport(execFileSync('pdftotext', ['-bbox-layout', output, '-'], { encoding: 'utf8', timeout: 15_000, maxBuffer: 4 * 1024 * 1024 }))
  return { pdf, textReport }
}
export { renderGeometry, renderPdf, pdfTable, pdfText, pdfWord, assertSamePdfRow, assertPdfTableWithinColumns }
