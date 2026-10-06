import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { PDFDocument } from 'pdf-lib'
import { describe, expect, it } from 'vitest'
import { buildFbsPickingListPrintHtml } from './fbsUx'

type PickingInput = Parameters<typeof buildFbsPickingListPrintHtml>[0]
type PickingRow = PickingInput['rows'][number]

const baseInput: Omit<PickingInput, 'rows'> = {
  supplyName: 'FBS WMS-657',
  wbSupplyId: 'WB-WMS-657',
  marketplace: 'wb',
  sellerName: 'Контрольный селлер',
  wmsWarehouseName: 'Основной склад',
  routeLabel: 'Склад / СЦ',
  deadlineLabel: '05.10.2026, 18:00',
  printedAtLabel: '05.10.2026, 12:00',
}

function row(overrides: Partial<PickingRow> = {}): PickingRow {
  return {
    name: 'Контрольный товар',
    size: 'Универсальный',
    imageUrl: null,
    identifiers: ['ART-WMS-657', 'WB 123456789'],
    locations: ['A-01 · Короб длинного маршрута: 1'],
    required: 1,
    picked: 0,
    wbOrders: [5524537174],
    stickerCodes: ['56672606304'],
    marking: 'КИЗ',
    ...overrides,
  }
}

function documentFor(rows: PickingRow[]) {
  return buildFbsPickingListPrintHtml({ ...baseInput, rows })
}

function onlyTableBodyRow(html: string) {
  const body = html.match(/<tbody>([\s\S]*?)<\/tbody>/)?.[1]
  expect(body, 'tbody листа подбора должен существовать').toBeTruthy()
  const rows = [...body!.matchAll(/<tr>([\s\S]*?)<\/tr>/g)]
  expect(rows).toHaveLength(1)
  return rows[0]![1]
}

function tableCells(rowHtml: string) {
  return [...rowHtml.matchAll(/<td(?:\s[^>]*)?>([\s\S]*?)<\/td>/g)].map((match) => match[0])
}

function tableHeaders(html: string) {
  return [...html.matchAll(/<th(?:\s[^>]*)?>([\s\S]*?)<\/th>/g)]
    .map((match) => match[1]!.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim())
}

function cssRule(css: string, selector: string) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return css.match(new RegExp(`(?:^|})\\s*${escaped}\\s*\\{([^}]*)\\}`))?.[1] ?? ''
}

function withoutAutomaticPrint(html: string, replacement = '') {
  const result = html.replace(/\s*<script>[\s\S]*?<\/script>\s*(?=<\/body>)/, replacement)
  expect(result).not.toContain('window.print()')
  return result
}

function chromeExecutable() {
  return [
    process.env.WMS_PRINT_CHROMIUM,
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ].find((candidate): candidate is string => Boolean(candidate && existsSync(candidate)))
}

type GeometryReport = {
  allCellContentFits: boolean
  columnBounds: Array<{ left: number; right: number }>
  headersAligned: boolean
  neighboringCellsDoNotOverlap: boolean
  rowCellCounts: number[]
  rowsDoNotOverlap: boolean
  tableBounds: { left: number; right: number }
  tableWithinPage: boolean
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

const geometryProbe = String.raw`<script>
  (() => {
    const rect = (element) => element.getBoundingClientRect();
    const within = (inner, outer) => inner.left >= outer.left - 1 && inner.right <= outer.right + 1 && inner.top >= outer.top - 1 && inner.bottom <= outer.bottom + 1;
    const rows = Array.from(document.querySelectorAll('tbody tr'));
    const headers = Array.from(document.querySelectorAll('thead th'));
    const firstCells = rows[0] ? Array.from(rows[0].children) : [];
    const tableRect = rect(document.querySelector('table'));
    const bodyRect = rect(document.body);
    const sizeCells = Array.from(document.querySelectorAll('td.size')).map((cell) => {
      const range = document.createRange();
      range.selectNodeContents(cell);
      const lineRects = Array.from(range.getClientRects()).filter((item) => item.width > 0 && item.height > 0);
      const tops = [];
      for (const item of lineRects) if (!tops.some((top) => Math.abs(top - item.top) < 1)) tops.push(item.top);
      return {
        text: cell.textContent,
        lineCount: tops.length,
        linesWithinCell: lineRects.every((item) => within(item, rect(cell))),
      };
    });
    const report = {
      tableWithinPage: tableRect.left >= bodyRect.left - 1 && tableRect.right <= bodyRect.right + 1 && document.body.scrollWidth <= document.body.clientWidth + 1,
      tableBounds: { left: tableRect.left, right: tableRect.right },
      columnBounds: headers.map((header) => ({ left: rect(header).left, right: rect(header).right })),
      rowCellCounts: rows.map((item) => item.children.length),
      allCellContentFits: rows.every((item) => Array.from(item.children).every((cell) => cell.scrollWidth <= cell.clientWidth + 1)),
      neighboringCellsDoNotOverlap: rows.every((item) => Array.from(item.children).every((cell, index, cells) => !cells[index + 1] || rect(cell).right <= rect(cells[index + 1]).left + 1)),
      headersAligned: headers.length === firstCells.length && headers.every((header, index) => Math.abs(rect(header).left - rect(firstCells[index]).left) <= 1 && Math.abs(rect(header).right - rect(firstCells[index]).right) <= 1),
      rowsDoNotOverlap: rows.every((item, index) => !rows[index + 1] || rect(item).bottom <= rect(rows[index + 1]).top + 1),
      sizeCells,
    };
    document.documentElement.setAttribute('data-wms657-geometry', btoa(unescape(encodeURIComponent(JSON.stringify(report)))));
  })();
</script>`

function renderGeometry(html: string): GeometryReport {
  const chrome = chromeExecutable()
  expect(chrome, 'C4/C6 требуют установленный Chromium или Chrome (WMS_PRINT_CHROMIUM)').toBeTruthy()
  const dir = mkdtempSync(join(tmpdir(), 'wms657-geometry-'))
  try {
    const input = join(dir, 'picking-list.html')
    writeFileSync(input, withoutAutomaticPrint(html, geometryProbe))
    const dumped = execFileSync(chrome!, [
      '--headless=new', '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage',
      '--no-first-run', '--disable-background-networking', '--disable-component-update',
      '--disable-sync', '--disable-default-apps', `--user-data-dir=${join(dir, 'profile')}`,
      '--window-size=1047,2000', '--dump-dom', `file://${input}`,
    ], { encoding: 'utf8', timeout: 30_000 })
    const encoded = dumped.match(/data-wms657-geometry="([A-Za-z0-9+/=]+)"/)?.[1]
    expect(encoded, 'Chromium должен выполнить геометрическую проверку документа').toBeTruthy()
    return JSON.parse(Buffer.from(encoded!, 'base64').toString('utf8')) as GeometryReport
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

function commandAvailable(command: string) {
  try {
    execFileSync(command, ['-v'], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
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
  if (geometryWidth <= 0 || geometry.columnBounds.length !== 12) {
    throw new Error('Браузер не вернул границы двенадцати колонок таблицы после R8 WMS-680')
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
      for (const word of page.words) {
        const centerX = (word.xMin + word.xMax) / 2
        if (word.yMin <= header.yMax + 1 || word.yMax >= footerTop - 1) continue
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

async function waitForPdf(chrome: string, input: string, output: string, profile: string) {
  const printing = spawn(chrome, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage',
    '--no-pdf-header-footer', '--no-first-run', '--disable-background-networking',
    '--disable-component-update', '--disable-sync', '--disable-default-apps',
    `--user-data-dir=${profile}`, `--print-to-pdf=${output}`, `file://${input}`,
  ], { stdio: ['ignore', 'pipe', 'pipe'] })
  let stderr = ''
  let stdout = ''
  let processError: Error | null = null
  let exited: { code: number | null; signal: NodeJS.Signals | null } | null = null
  printing.stderr?.on('data', (chunk: Buffer) => { stderr += chunk.toString('utf8') })
  printing.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString('utf8') })
  printing.on('error', (error) => { processError = error })
  printing.on('exit', (code, signal) => { exited = { code, signal } })
  try {
    const deadline = Date.now() + 30_000
    while (!existsSync(output) || !readFileSync(output).subarray(-32).includes(Buffer.from('%%EOF'))) {
      const chromeError = processError as Error | null
      if (chromeError) throw new Error(`Chrome spawn failed: ${chromeError.message}\n${stderr}`)
      if (exited && !existsSync(output)) throw new Error(`Chrome exited without PDF: ${JSON.stringify(exited)}\n${stderr}\n${stdout}`)
      if (Date.now() >= deadline) throw new Error(`Chrome did not produce a complete PDF in 30s\n${stderr}\n${stdout}`)
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
  } finally {
    if (!exited) {
      printing.kill('SIGTERM')
      const deadline = Date.now() + 2_000
      while (!exited && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 50))
      if (!exited) {
        printing.kill('SIGKILL')
        const hardDeadline = Date.now() + 2_000
        while (!exited && Date.now() < hardDeadline) await new Promise((resolve) => setTimeout(resolve, 50))
      }
    }
  }
}

async function renderPdf(html: string) {
  const chrome = chromeExecutable()
  expect(chrome, 'C5/C6 требуют установленный Chromium или Chrome (WMS_PRINT_CHROMIUM)').toBeTruthy()
  expect(commandAvailable('pdftotext'), 'C5/C6 требуют Poppler pdftotext для чтения фактического PDF').toBe(true)
  const dir = mkdtempSync(join(tmpdir(), 'wms657-pdf-'))
  try {
    const input = join(dir, 'picking-list.html')
    const output = join(dir, 'picking-list.pdf')
    writeFileSync(input, withoutAutomaticPrint(html))
    await waitForPdf(chrome!, input, output, join(dir, 'profile'))
    const bytes = readFileSync(output)
    const pdf = await PDFDocument.load(bytes)
    const textReport = parsePdfTextReport(execFileSync('pdftotext', ['-bbox-layout', output, '-'], { encoding: 'utf8' }))
    return { pdf, textReport }
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

describe('WMS-657 · перенос размера в листе подбора FBS', () => {
  it('C1: R8 добавляет отдельные Артикул/Цвет, а размер остаётся в своей компактной ячейке с переносом', () => {
    const html = documentFor([row()])
    expect(html.match(/<td class="size">Универсальный<\/td>/g)).toHaveLength(1)
    const css = html.match(/<style>([\s\S]*?)<\/style>/)?.[1] ?? ''
    const sizeRule = cssRule(css, '.size')
    const sizeCellRule = cssRule(css, 'td.size')
    const generalCellRule = cssRule(css, 'th, td')
    expect(`${sizeRule};${sizeCellRule}`).not.toMatch(/white-space\s*:\s*nowrap/)
    expect(`${sizeCellRule};${generalCellRule}`).toMatch(/(?:overflow-wrap\s*:\s*(?:anywhere|break-word)|word-break\s*:\s*(?:break-all|break-word)|white-space\s*:\s*(?:normal|pre-wrap|break-spaces))/)
    expect(tableHeaders(html)).toEqual(['№', 'Фото', 'Товар', 'Артикул', 'Цвет', 'Размер', 'Ячейка / тара', 'Заказы WB', 'Стикер', 'Взять', 'Подобрано', 'Маркировка'])
  })

  it('C2: двенадцать колонок, контрольные данные и вход не меняются при повторной генерации', () => {
    const control = row({
      name: 'PRODUCT-CONTROL', size: 'SIZE-CONTROL', imageUrl: 'data:image/png;base64,AA==',
      color: 'COLOR-CONTROL', identifiers: ['IDENTIFIER-A', 'IDENTIFIER-B'], locations: ['LOCATION-CONTROL'],
      required: 3, picked: 2, wbOrders: ['ORDER-CONTROL'], stickerCodes: ['S-1'],
      marking: 'MARKING-CONTROL',
    })
    const input: PickingInput = { ...baseInput, rows: [control] }
    const before = JSON.stringify(input)
    const first = buildFbsPickingListPrintHtml(input)
    const second = buildFbsPickingListPrintHtml(input)
    expect(second).toBe(first)
    expect(JSON.stringify(input)).toBe(before)
    expect(tableHeaders(first)).toEqual(['№', 'Фото', 'Товар', 'Артикул', 'Цвет', 'Размер', 'Ячейка / тара', 'Заказы WB', 'Стикер', 'Взять', 'Подобрано', 'Маркировка'])
    const bodyRow = onlyTableBodyRow(first)
    expect(tableCells(bodyRow)).toHaveLength(12)
    for (const value of ['PRODUCT-CONTROL', 'SIZE-CONTROL', 'COLOR-CONTROL', 'IDENTIFIER-A', 'IDENTIFIER-B', 'LOCATION-CONTROL', '3', '2', 'ORDER-CONTROL', 'S-1', 'MARKING-CONTROL']) {
      expect(bodyRow).toContain(value)
    }
    expect(bodyRow).toContain('src="data:image/png;base64,AA=="')
  })

  it('C3: короткий размер остаётся одной строкой, отсутствие размера — прочерком', () => {
    const html = documentFor([row({ name: 'SHORT-SIZE', size: '46' }), row({ name: 'NO-SIZE', size: null })])
    expect(html).toContain('<td class="size">46</td>')
    expect(html).toContain('<td class="size">—</td>')
    expect(html).not.toMatch(/<td class="size">46(?:<br\s*\/?>|\s*\n)/)
    const body = html.match(/<tbody>([\s\S]*?)<\/tbody>/)?.[1] ?? ''
    const rows = [...body.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map((match) => match[1])
    expect(rows).toHaveLength(2)
    expect(rows.map((item) => tableCells(item!).length)).toEqual([12, 12])
  })

  it('C4: Chromium держит длинный размер и соседние данные в границах колонок', () => {
    const html = documentFor([row({
      name: 'Очень длинное настоящее название товара WMS-657 для проверки печатной строки',
      identifiers: ['АРТИКУЛ-С-ОЧЕНЬ-ДЛИННЫМ-ЗНАЧЕНИЕМ-WMS-657', 'WB 12345678901234567890'],
      locations: ['Склад · Ряд-очень-длинный · Секция-очень-длинная · Короб-123456789: 17'],
      wbOrders: [5524537174, 5524537175, 5524537176],
      stickerCodes: ['56672606304', '56672606305'],
      marking: 'КИЗ, УИН, IMEI, GTIN',
    })])
    const report = renderGeometry(html)
    expect(report.tableWithinPage).toBe(true)
    expect(report.rowCellCounts).toEqual([12])
    expect(report.allCellContentFits).toBe(true)
    expect(report.neighboringCellsDoNotOverlap).toBe(true)
    expect(report.headersAligned).toBe(true)
    expect(report.sizeCells).toHaveLength(1)
    expect(report.sizeCells[0]).toMatchObject({ text: 'Универсальный', linesWithinCell: true })
    expect(report.sizeCells[0]!.lineCount).toBeGreaterThanOrEqual(2)
  }, 45_000)

  it('C5: PDF A4 landscape сохраняет таблицу и полный текст всех колонок', async () => {
    const html = documentFor([row({
      name: 'PDF-PRODUCT-LONG-WMS-657',
      color: 'PDF-COLOR-WMS-657', identifiers: ['PDF-ARTICLE-WMS-657', 'PDF-IDENTIFIER-WMS-657'],
      locations: ['PDF-LOCATION-LONG-WMS-657'],
      wbOrders: ['PDF-ORDER-657'],
      stickerCodes: ['S657'],
      marking: 'PDF-MARKING-WMS-657',
    })])
    const geometry = renderGeometry(html)
    expect(geometry.tableWithinPage).toBe(true)
    expect(geometry.allCellContentFits).toBe(true)
    expect(geometry.neighboringCellsDoNotOverlap).toBe(true)
    const { pdf, textReport } = await renderPdf(html)
    expect(pdf.getPageCount()).toBe(1)
    const { width, height } = pdf.getPage(0).getSize()
    expect(width).toBeGreaterThan(height)
    expect(width).toBeCloseTo(841.89, 0)
    expect(height).toBeCloseTo(595.28, 0)
    const table = pdfTable(textReport, geometry)
    assertPdfTableWithinColumns(table)
    const name = pdfText(table, 2, 'PDF-PRODUCT-LONG-WMS-657')
    const article = pdfText(table, 3, 'PDF-ARTICLE-WMS-657')
    const color = pdfText(table, 4, 'PDF-COLOR-WMS-657')
    const size = pdfText(table, 5, 'Универсальный')
    const cells = [
      { label: 'номер позиции', match: pdfWord(table, 0, '1') },
      { label: 'фото', match: pdfText(table, 1, '—') },
      { label: 'артикул', match: article },
      { label: 'цвет', match: color },
      { label: 'размер', match: size },
      { label: 'ячейка / тара', match: pdfText(table, 6, 'PDF-LOCATION-LONG-WMS-657') },
      { label: 'заказ', match: pdfText(table, 7, '№PDF-ORDER-657') },
      { label: 'стикер', match: pdfText(table, 8, 'S657') },
      { label: 'взять', match: pdfText(table, 9, '1') },
      { label: 'подобрано', match: pdfText(table, 10, '0/1') },
      { label: 'маркировка', match: pdfText(table, 11, 'PDF-MARKING-WMS-657') },
    ]
    assertSamePdfRow([name], cells)

    const lostFragment = size.words.at(-1)!
    const textLossCopy: PdfTextReport = {
      pages: textReport.pages.map((page) => ({ ...page, words: page.words.filter((word) => word !== lostFragment) })),
    }
    expect(() => pdfText(pdfTable(textLossCopy, geometry), 5, 'Универсальный'), 'координатная проверка должна ловить потерю части размера').toThrow(/PDF потерял/)

    const sizeColumn = table.pages[size.pageIndex]!.columns[5]!
    const overflowingWord = size.words[0]!
    const overflowCopy: PdfTextReport = {
      pages: textReport.pages.map((page) => ({
        ...page,
        words: page.words.map((word) => word === overflowingWord ? { ...word, xMax: sizeColumn.right + 2 } : word),
      })),
    }
    expect(() => assertPdfTableWithinColumns(pdfTable(overflowCopy, geometry)), 'координатная проверка должна ловить выход текста за колонку').toThrow(/вышло за границу колонки/)
  }, 60_000)

  it('C6: многострочный HTML/PDF не смешивает строки и варианты размера', async () => {
    const rows = Array.from({ length: 34 }, (_, index) => row({
      name: `ROW-${String(index + 1).padStart(3, '0')}`,
      size: index === 1 ? '46' : index === 2 ? null : index === 0 || index === 16 || index === 33 ? 'Универсальный' : `S${String(index + 1).padStart(2, '0')}`,
      color: `COLOR-${String(index + 1).padStart(3, '0')}`,
      identifiers: index === 16
        ? [`ARTICLE-${index + 1}`, 'ДЛИННЫЙ-ИДЕНТИФИКАТОР-СОСЕДНЕЙ-КОЛОНКИ-WMS-657-123456789']
        : [`ARTICLE-${index + 1}`, `ID-${index + 1}`],
      locations: index === 16 ? ['ДЛИННЫЙ-ПУТЬ-ЯЧЕЙКИ-И-ТАРЫ-WMS-657-123456789: 1'] : [`A-${index + 1}: 1`],
      wbOrders: [657000 + index],
      stickerCodes: [`S${String(index).padStart(3, '0')}`],
      marking: `MARK-${String(index + 1).padStart(3, '0')}`,
    }))
    const html = documentFor(rows)
    const report = renderGeometry(html)
    expect(report.rowCellCounts).toEqual(Array(34).fill(12))
    expect(report.tableWithinPage).toBe(true)
    expect(report.allCellContentFits).toBe(true)
    expect(report.rowsDoNotOverlap).toBe(true)
    expect(report.neighboringCellsDoNotOverlap).toBe(true)
    expect(report.headersAligned).toBe(true)
    expect(report.sizeCells[0]).toMatchObject({ text: 'Универсальный', linesWithinCell: true })
    expect(report.sizeCells[0]!.lineCount).toBeGreaterThanOrEqual(2)
    expect(report.sizeCells[1]).toEqual({ text: '46', lineCount: 1, linesWithinCell: true })
    expect(report.sizeCells[2]).toEqual({ text: '—', lineCount: 1, linesWithinCell: true })
    expect(report.sizeCells[16]).toMatchObject({ text: 'Универсальный', linesWithinCell: true })
    expect(report.sizeCells[16]!.lineCount).toBeGreaterThanOrEqual(2)
    expect(report.sizeCells[33]).toMatchObject({ text: 'Универсальный', linesWithinCell: true })
    expect(report.sizeCells[33]!.lineCount).toBeGreaterThanOrEqual(2)

    const { pdf, textReport } = await renderPdf(html)
    expect(pdf.getPageCount()).toBeGreaterThan(1)
    for (const page of pdf.getPages()) {
      const { width, height } = page.getSize()
      expect(width).toBeGreaterThan(height)
      expect(width).toBeCloseTo(841.89, 0)
      expect(height).toBeCloseTo(595.28, 0)
    }
    const table = pdfTable(textReport, report)
    assertPdfTableWithinColumns(table)
    expect(pdfTextMatches(table, 5, 'Универсальный')).toHaveLength(3)
    let longSizeOccurrence = 0
    for (const [index] of rows.entries()) {
      const rowNumber = index + 1
      const name = pdfText(table, 2, `ROW-${String(rowNumber).padStart(3, '0')}`)
      const article = pdfText(table, 3, `ARTICLE-${rowNumber}`)
      const color = pdfText(table, 4, `COLOR-${String(rowNumber).padStart(3, '0')}`)
      const expectedSize = index === 1 ? '46' : index === 2 ? '—' : index === 0 || index === 16 || index === 33 ? 'Универсальный' : `S${String(rowNumber).padStart(2, '0')}`
      const sizeOccurrence = expectedSize === 'Универсальный' ? longSizeOccurrence++ : 0
      const location = index === 16
        ? 'ДЛИННЫЙ-ПУТЬ-ЯЧЕЙКИ-И-ТАРЫ-WMS-657-123456789: 1'
        : `A-${rowNumber}: 1`
      assertSamePdfRow([name], [
        { label: `номер позиции строки ${rowNumber}`, match: pdfWord(table, 0, String(rowNumber)) },
        { label: `фото строки ${rowNumber}`, match: pdfText(table, 1, '—', index) },
        { label: `артикул строки ${rowNumber}`, match: article },
        { label: `цвет строки ${rowNumber}`, match: color },
        { label: `размер строки ${rowNumber}`, match: pdfText(table, 5, expectedSize, sizeOccurrence) },
        { label: `ячейка строки ${rowNumber}`, match: pdfText(table, 6, location) },
        { label: `заказ строки ${rowNumber}`, match: pdfText(table, 7, `№${657000 + index}`) },
        { label: `стикер строки ${rowNumber}`, match: pdfText(table, 8, `S${String(index).padStart(3, '0')}`) },
        { label: `взять строки ${rowNumber}`, match: pdfText(table, 9, '1', index) },
        { label: `подобрано строки ${rowNumber}`, match: pdfText(table, 10, '0/1', index) },
        { label: `маркировка строки ${rowNumber}`, match: pdfText(table, 11, `MARK-${String(rowNumber).padStart(3, '0')}`) },
      ])
    }
  }, 60_000)
})
