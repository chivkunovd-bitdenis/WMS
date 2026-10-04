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
  headersAligned: boolean
  neighboringCellsDoNotOverlap: boolean
  rowCellCounts: number[]
  rowsDoNotOverlap: boolean
  tableWithinPage: boolean
  sizeCells: Array<{ lineCount: number; linesWithinCell: boolean; text: string }>
}

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
      if (processError) throw new Error(`Chrome spawn failed: ${processError.message}\n${stderr}`)
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
    const text = execFileSync('pdftotext', ['-layout', output, '-'], { encoding: 'utf8' })
    return { pdf, text }
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

describe('WMS-657 · перенос размера в листе подбора FBS', () => {
  it('C1: Универсальный остаётся в ячейке размера шириной 78 px и перенос разрешён', () => {
    const html = documentFor([row()])
    expect(html.match(/<td class="size">Универсальный<\/td>/g)).toHaveLength(1)
    const css = html.match(/<style>([\s\S]*?)<\/style>/)?.[1] ?? ''
    const sizeRule = cssRule(css, '.size')
    const sizeCellRule = cssRule(css, 'td.size')
    const generalCellRule = cssRule(css, 'th, td')
    expect(sizeRule).toMatch(/width\s*:\s*78px/)
    expect(`${sizeRule};${sizeCellRule}`).not.toMatch(/white-space\s*:\s*nowrap/)
    expect(`${sizeCellRule};${generalCellRule}`).toMatch(/(?:overflow-wrap\s*:\s*(?:anywhere|break-word)|word-break\s*:\s*(?:break-all|break-word)|white-space\s*:\s*(?:normal|pre-wrap|break-spaces))/)
    expect(html).toContain('<th class="size">Размер</th><th>Ячейка / тара</th>')
  })

  it('C2: десять колонок, контрольные данные и вход не меняются при повторной генерации', () => {
    const control = row({
      name: 'PRODUCT-CONTROL', size: 'SIZE-CONTROL', imageUrl: 'data:image/png;base64,AA==',
      identifiers: ['IDENTIFIER-A', 'IDENTIFIER-B'], locations: ['LOCATION-CONTROL'],
      required: 3, picked: 2, wbOrders: ['ORDER-CONTROL'], stickerCodes: ['S-1'],
      marking: 'MARKING-CONTROL',
    })
    const input: PickingInput = { ...baseInput, rows: [control] }
    const before = JSON.stringify(input)
    const first = buildFbsPickingListPrintHtml(input)
    const second = buildFbsPickingListPrintHtml(input)
    expect(second).toBe(first)
    expect(JSON.stringify(input)).toBe(before)
    expect(first).toContain('<thead><tr><th class="number">№</th><th class="image">Фото</th><th>Товар и идентификаторы</th><th class="size">Размер</th><th>Ячейка / тара</th><th>Заказы WB</th><th class="sticker">Стикер</th><th class="quantity">Взять</th><th class="quantity">Подобрано</th><th>Маркировка</th></tr></thead>')
    const bodyRow = onlyTableBodyRow(first)
    expect(tableCells(bodyRow)).toHaveLength(10)
    for (const value of ['PRODUCT-CONTROL', 'SIZE-CONTROL', 'IDENTIFIER-A', 'IDENTIFIER-B', 'LOCATION-CONTROL', '3', '2', 'ORDER-CONTROL', 'S-1', 'MARKING-CONTROL']) {
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
    expect(rows.map((item) => tableCells(item!).length)).toEqual([10, 10])
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
    expect(report.rowCellCounts).toEqual([10])
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
      identifiers: ['PDF-IDENTIFIER-WMS-657'],
      locations: ['PDF-LOCATION-LONG-WMS-657'],
      wbOrders: ['PDF-ORDER-657'],
      stickerCodes: ['S657'],
      marking: 'PDF-MARKING-WMS-657',
    })])
    const geometry = renderGeometry(html)
    expect(geometry.tableWithinPage).toBe(true)
    expect(geometry.allCellContentFits).toBe(true)
    expect(geometry.neighboringCellsDoNotOverlap).toBe(true)
    const { pdf, text } = await renderPdf(html)
    expect(pdf.getPageCount()).toBe(1)
    const { width, height } = pdf.getPage(0).getSize()
    expect(width).toBeGreaterThan(height)
    expect(width).toBeCloseTo(841.89, 0)
    expect(height).toBeCloseTo(595.28, 0)
    const compact = text.replace(/\s+/g, '')
    for (const value of ['Универсальный', 'PDF-PRODUCT-LONG-WMS-657', 'PDF-IDENTIFIER-WMS-657', 'PDF-LOCATION-LONG-WMS-657', 'PDF-ORDER-657', 'S657', 'PDF-MARKING-WMS-657']) {
      expect(compact).toContain(value)
    }
  }, 60_000)

  it('C6: многострочный HTML/PDF не смешивает строки и варианты размера', async () => {
    const rows = Array.from({ length: 34 }, (_, index) => row({
      name: `ROW-${String(index + 1).padStart(3, '0')}`,
      size: index === 1 ? '46' : index === 2 ? null : index === 0 || index === 16 || index === 33 ? 'Универсальный' : '48',
      identifiers: index === 16 ? ['ДЛИННЫЙ-ИДЕНТИФИКАТОР-СОСЕДНЕЙ-КОЛОНКИ-WMS-657-123456789'] : [`ID-${index + 1}`],
      locations: index === 16 ? ['ДЛИННЫЙ-ПУТЬ-ЯЧЕЙКИ-И-ТАРЫ-WMS-657-123456789: 1'] : [`A-${index + 1}: 1`],
      wbOrders: [657000 + index],
      stickerCodes: [`S${String(index).padStart(3, '0')}`],
    }))
    const html = documentFor(rows)
    const report = renderGeometry(html)
    expect(report.rowCellCounts).toEqual(Array(34).fill(10))
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

    const { pdf, text } = await renderPdf(html)
    expect(pdf.getPageCount()).toBeGreaterThan(1)
    const compact = text.replace(/\s+/g, '')
    for (const value of ['ROW-001', 'ROW-002', 'ROW-003', 'ROW-017', 'ROW-034', '46', '—', 'ДЛИННЫЙ-ИДЕНТИФИКАТОР-СОСЕДНЕЙ-КОЛОНКИ-WMS-657-123456789']) {
      expect(compact).toContain(value)
    }
    expect(compact.match(/Универсальный/g)).toHaveLength(3)
  }, 60_000)
})
