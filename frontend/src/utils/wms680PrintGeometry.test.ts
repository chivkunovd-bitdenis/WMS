import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { PDFDocument } from 'pdf-lib'
import { describe, expect, it } from 'vitest'
import { buildFbsPickingListPrintHtml } from '../screens/v2/fbsUx'
import { buildInboundReceivingSheetHtml } from './printInboundReceivingSheet'
import { buildShipmentPackagingSheetHtml } from './printShipmentPackagingSheet'
import {
  printInboundSupplyWaybill,
  printMarketplaceUnloadWaybill,
  printOperationalOutboundWaybill,
  type ShipmentWaybillData,
} from './printShipmentWaybill'

const chrome = [
  process.env.WMS_PRINT_CHROMIUM,
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
].find((candidate): candidate is string => Boolean(candidate && existsSync(candidate)))

const variants = [
  { article: 'ARTICLE-680-A', color: 'COLOR-RED-680', size: 'SIZE-S-680' },
  { article: 'ARTICLE-680-A', color: 'COLOR-BLUE-680', size: 'SIZE-M-680' },
  { article: 'ARTICLE-680-A', color: 'COLOR-GREEN-680', size: 'SIZE-L-680' },
  { article: 'ARTICLE-680-A', color: 'COLOR-BLACK-680', size: 'SIZE-XL-680' },
]

function headerNames(html: string) {
  return [...html.matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/g)]
    .map((match) => match[1]!.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim())
}

function expectColumnsBeforePdf(html: string) {
  const headers = headerNames(html)
  for (const name of ['Артикул', 'Цвет', 'Размер']) {
    expect(headers.filter((header) => header === name), `R8: в PDF должен уйти ровно один заголовок «${name}»`).toHaveLength(1)
  }
  expect(headers.some((header) => /товар|наименование/i.test(header))).toBe(true)
}

function capturedWaybill(
  kind: ShipmentWaybillData['docKind'],
  count: number,
  pickAllocations: NonNullable<ShipmentWaybillData['pickAllocations']> = [{ location_code: 'CELL-1-680', sku_code: variants[0]!.article, quantity: 12340 }],
) {
  const data: ShipmentWaybillData = {
    docKind: kind, documentId: 'DOC-680', documentNumber: 'DOC-680', waybillNumber: 'WB-680', documentTypeLabel: 'Поставка',
    statusLabel: 'draft', warehouseName: 'WMS', sellerName: 'Seller', wbWarehouseLabel: 'WB WH', plannedDate: '2026-10-07', createdAt: '2026-10-07',
    lines: Array.from({ length: count }, (_, index) => {
      const variant = variants[index % variants.length]!
      return {
        sku_code: variant.article, product_name: `WAYBILL-LONG-NAME-${String(index + 1).padStart(2, '0')}-680`,
        quantity: 12340 + index, shipped_qty: 12000 + index, received_qty: index, storage_location_code: `CELL-${index + 1}-680`,
        size: variant.size, color: variant.color,
      }
    }),
    pickAllocations,
  }
  const state = globalThis as { window?: unknown; document?: unknown }
  const previousWindow = state.window
  const previousDocument = state.document
  const capture = { __WMS_CAPTURE_PRINT_HTML__: true, __WMS_LAST_PRINT_HTML__: '' }
  state.window = capture
  state.document = { createElement: () => ({ setAttribute() {}, style: {}, onload: null }), body: { appendChild() {}, removeChild() {} } } as unknown as Document
  try {
    if (kind === 'marketplace_unload') printMarketplaceUnloadWaybill({ ...data, wbWarehouseLabel: data.wbWarehouseLabel ?? null })
    else if (kind === 'operational_outbound') printOperationalOutboundWaybill(data)
    else printInboundSupplyWaybill(data)
    return capture.__WMS_LAST_PRINT_HTML__
  } finally {
    state.window = previousWindow
    state.document = previousDocument
  }
}

function inbound(count: number) {
  return buildInboundReceivingSheetHtml({
    documentNumber: 'IN-680', sellerName: 'Seller', warehouseName: 'WMS', plannedDate: '2026-10-07',
    items: Array.from({ length: count }, (_, index) => {
      const variant = variants[index % variants.length]!
      return {
        product_name: `INBOUND-LONG-NAME-${String(index + 1).padStart(2, '0')}-680`, vendor_code: variant.article, sku_code: `SKU-${index + 1}-680`,
        barcode: `200000000${String(index + 1).padStart(4, '0')}`, wb_nm_id: 680 + index, photo_url: null,
        expected_qty: 12340 + index, size: variant.size, color: variant.color,
      }
    }),
  })
}

function packaging(count: number) {
  return buildShipmentPackagingSheetHtml({
    documentNumber: 'FBO-680', documentType: 'Отгрузка', sellerName: 'Seller', shipmentDate: '2026-10-07', warehouseName: 'WMS',
    items: Array.from({ length: count }, (_, index) => {
      const variant = variants[index % variants.length]!
      return {
        product_name: `PACKAGING-LONG-NAME-${String(index + 1).padStart(2, '0')}-680`, vendor_code: variant.article, sku_code: `SKU-${index + 1}-680`,
        barcode: `300000000${String(index + 1).padStart(4, '0')}`, wb_nm_id: 780 + index, photo_url: null,
        instructions: `LONG-INSTRUCTION-${index + 1}-680 with text that must stay in its own cell`, quantity: 12340 + index,
        size: variant.size, color: variant.color,
      }
    }),
  })
}

function fbs(count: number) {
  return buildFbsPickingListPrintHtml({
    supplyName: 'FBS-680', wbSupplyId: 'WB-680', marketplace: 'mixed', sellerName: 'Seller', wmsWarehouseName: 'WMS',
    routeLabel: 'Route', deadlineLabel: '2026-10-07', printedAtLabel: '2026-10-07',
    rows: Array.from({ length: count }, (_, index) => {
      const variant = variants[index % variants.length]!
      return {
        name: `FBS-LONG-NAME-${String(index + 1).padStart(2, '0')}-680`, size: variant.size, color: variant.color, imageUrl: null,
        identifiers: [variant.article, `BARCODE-${index + 1}-680`], locations: [`CELL-${index + 1}-680`],
        required: 12340 + index, picked: 12000 + index, wbOrders: [6800 + index], stickerCodes: [null], marking: `MARK-${index + 1}-680`,
      }
    }),
  })
}

function withoutAutomaticPrint(html: string) {
  return html.replace(/\s*<script>[\s\S]*?<\/script>\s*(?=<\/body>)/, '')
}

function fixtureFileName(label: string) {
  const slug = label
    .normalize('NFKD')
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '')
  return slug || 'wms680-pdf-fixture'
}

function pause(milliseconds: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, milliseconds))
}

async function stopOwnedChrome(process: ReturnType<typeof spawn>) {
  if (process.exitCode !== null) return
  const exited = new Promise<void>((resolve) => process.once('exit', () => resolve()))
  process.kill('SIGTERM')
  await Promise.race([exited, pause(5_000)])
  if (process.exitCode === null) {
    process.kill('SIGKILL')
    await exited
  }
}

async function removeOwnedFixtureDirectory(dir: string) {
  let lastError: unknown
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      rmSync(dir, { recursive: true, force: true })
      return
    } catch (error) {
      lastError = error
      await pause(100)
    }
  }
  throw lastError
}

async function renderPdf(html: string, label: string) {
  expect(chrome, 'C680-18 требует уже установленный Chrome/Chromium; зависимости не устанавливаются').toBeTruthy()
  const dir = mkdtempSync(join(tmpdir(), 'wms680-pdf-'))
  const fileName = fixtureFileName(label)
  const input = join(dir, `${fileName}.html`)
  const output = join(dir, `${fileName}.pdf`)
  writeFileSync(input, withoutAutomaticPrint(html))
  const process = spawn(chrome!, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage', '--no-pdf-header-footer', '--no-first-run',
    '--disable-background-networking', '--disable-component-update', '--disable-sync', '--disable-default-apps',
    `--user-data-dir=${join(dir, 'profile')}`, `--print-to-pdf=${output}`, `file://${input}`,
  ], { stdio: 'ignore' })
  try {
    const deadline = Date.now() + 30_000
    while (!existsSync(output) || !readFileSync(output).subarray(-32).includes(Buffer.from('%%EOF'))) {
      if (Date.now() >= deadline) throw new Error(`Chrome не записал PDF ${label} за 30 секунд`)
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    const pdf = await PDFDocument.load(readFileSync(output))
    const text = execFileSync('pdftotext', ['-bbox-layout', output, '-'], { encoding: 'utf8' })
    return { pdf, text }
  } finally {
    await stopOwnedChrome(process)
    await removeOwnedFixtureDirectory(dir)
  }
}

type PickTableDomReport = {
  headers: string[]
  rows: string[][]
  columns: Array<{ left: number; right: number; width: number }>
  table: { left: number; right: number; width: number }
}

function withPickTableDomProbe(html: string) {
  return `${withoutAutomaticPrint(html).replace('</body>', '')}
    <script>
      (() => {
        const heading = [...document.querySelectorAll('h2')].find((node) => node.textContent.trim() === 'Подбор по ячейкам')
        const table = heading && heading.nextElementSibling
        if (!table || table.tagName !== 'TABLE') throw new Error('Не найдена таблица подбора по ячейкам')
        const rect = (node) => node.getBoundingClientRect()
        const report = {
          headers: [...table.querySelectorAll('thead th')].map((cell) => cell.textContent.trim()),
          rows: [...table.querySelectorAll('tbody tr')].map((row) => [...row.children].map((cell) => cell.textContent.trim())),
          columns: [...table.querySelectorAll('thead th')].map((cell) => {
            const bounds = rect(cell)
            return { left: bounds.left, right: bounds.right, width: bounds.width }
          }),
          table: (() => {
            const bounds = rect(table)
            return { left: bounds.left, right: bounds.right, width: bounds.width }
          })(),
        }
        const marker = document.createElement('pre')
        marker.id = 'wms680-pick-table-dom-report'
        marker.textContent = JSON.stringify(report)
        document.body.append(marker)
      })()
    </script>
  </body>`
}

function renderPickTableDom(html: string, label: string): PickTableDomReport {
  expect(chrome, 'C680-18 требует уже установленный Chrome/Chromium; зависимости не устанавливаются').toBeTruthy()
  const dir = mkdtempSync(join(tmpdir(), 'wms680-pick-dom-'))
  try {
    const input = join(dir, `${fixtureFileName(label)}.html`)
    writeFileSync(input, withPickTableDomProbe(html))
    const dom = execFileSync(chrome!, [
      '--headless=new', '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage', '--no-first-run',
      '--disable-background-networking', '--disable-component-update', '--disable-sync', '--disable-default-apps',
      `--user-data-dir=${join(dir, 'profile')}`, '--dump-dom', `file://${input}`,
    ], { encoding: 'utf8', timeout: 30_000 })
    const serialized = dom.match(/<pre id="wms680-pick-table-dom-report">([\s\S]*?)<\/pre>/)?.[1]
    expect(serialized, 'Chrome должен вернуть измерения именно второй таблицы подбора').toBeTruthy()
    return JSON.parse(serialized!) as PickTableDomReport
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

function compact(text: string) {
  return text.replace(/\s+/g, '').toUpperCase()
}

type PdfWord = { left: number; top: number; right: number; bottom: number; text: string; page: number; block: number; line: number }

function pdfWords(xml: string): PdfWord[] {
  const words: PdfWord[] = []
  const pages = [...xml.matchAll(/<page\b[^>]*>([\s\S]*?)<\/page>/g)]
  for (const [page, pageMatch] of pages.entries()) {
    const blocks = [...pageMatch[1]!.matchAll(/<block\b[^>]*>([\s\S]*?)<\/block>/g)]
    for (const [block, blockMatch] of blocks.entries()) {
      const lines = [...blockMatch[1]!.matchAll(/<line\b[^>]*>([\s\S]*?)<\/line>/g)]
      for (const [line, lineMatch] of lines.entries()) {
        for (const word of lineMatch[1]!.matchAll(/<word\b[^>]*xMin="([\d.]+)"[^>]*yMin="([\d.]+)"[^>]*xMax="([\d.]+)"[^>]*yMax="([\d.]+)"[^>]*>([\s\S]*?)<\/word>/g)) {
          words.push({ left: Number(word[1]), top: Number(word[2]), right: Number(word[3]), bottom: Number(word[4]), text: word[5]!, page, block, line })
        }
      }
    }
  }
  return words
}

function pdfTextFragments(words: PdfWord[], expected: string) {
  const target = compact(expected)
  for (let firstIndex = 0; firstIndex < words.length; firstIndex += 1) {
    const fragments: PdfWord[] = []
    let joined = ''
    for (let index = firstIndex; index < Math.min(words.length, firstIndex + 12); index += 1) {
      const word = words[index]!
      if (fragments.length) {
        const first = fragments[0]!
        const previous = fragments.at(-1)!
        // A common X-coordinate is insufficient: distinct table rows can share it.
        // Keep the PDF page/text-block identity and require adjacent wrapped lines.
        if (word.page !== first.page || word.block !== first.block || word.line !== previous.line + 1) break
        if (Math.abs(word.left - first.left) > 1 || word.top < previous.top - 1) break
        const lineHeight = Math.max(previous.bottom - previous.top, word.bottom - word.top)
        if (word.top - previous.top > lineHeight * 1.5) break
      }
      const next = `${joined}${compact(word.text)}`
      if (!target.startsWith(next)) break
      fragments.push(word)
      joined = next
      if (joined === target) return fragments
    }
  }
  return undefined
}

function expectPdfTextFragments(words: PdfWord[], expected: string) {
  const fragments = pdfTextFragments(words, expected)
  expect(fragments, `реальный PDF должен содержать полный текст «${expected}» в одной ячейке, а не только его обрезок`).toBeTruthy()
  return fragments!
}

function assertRealPdfGeometry(xml: string, expectedName: string) {
  const pages = [...xml.matchAll(/<page\b[^>]*width="([\d.]+)"[^>]*height="([\d.]+)"[^>]*>([\s\S]*?)<\/page>/g)]
  expect(pages.length, 'pdftotext должен вернуть страницы реального PDF').toBeGreaterThan(0)
  const words = pdfWords(xml)
  expect(words.length, 'pdftotext должен вернуть реальные координаты PDF').toBeGreaterThan(0)
  const nameFragments = expectPdfTextFragments(words, expectedName)
  for (const token of ['АРТИКУЛ', 'ЦВЕТ', 'РАЗМЕР']) expect(words.some((word) => compact(word.text) === token), `PDF должен содержать заголовок «${token}»`).toBe(true)
  const headerX = (token: string) => {
    const match = words.find((word) => compact(word.text) === token)
    expect(match, `PDF должен физически разместить заголовок «${token}»`).toBeTruthy()
    return match!.left
  }
  const articleX = headerX('АРТИКУЛ')
  expect(Math.max(...nameFragments.map((word) => word.right)), 'название товара не выходит в отдельную колонку Артикул').toBeLessThanOrEqual(articleX)
  expect(headerX('АРТИКУЛ')).toBeLessThan(headerX('ЦВЕТ'))
  expect(headerX('ЦВЕТ')).toBeLessThan(headerX('РАЗМЕР'))
  for (const page of pages) {
    const width = Number(page[1])
    const height = Number(page[2])
    for (const word of page[3]!.matchAll(/<word\b[^>]*xMin="([\d.]+)"[^>]*yMin="([\d.]+)"[^>]*xMax="([\d.]+)"[^>]*yMax="([\d.]+)"[^>]*>/g)) {
      expect(Number(word[1])).toBeGreaterThanOrEqual(0)
      expect(Number(word[2])).toBeGreaterThanOrEqual(0)
      expect(Number(word[3])).toBeLessThanOrEqual(width)
      expect(Number(word[4])).toBeLessThanOrEqual(height)
    }
  }
}

function assertPickTablePdf(xml: string, allocations: ShipmentWaybillData['pickAllocations']) {
  const words = pdfWords(xml)
  const quantityHeaders = words.filter((word) => compact(word.text) === 'КОЛ-ВО')
  const quantity = quantityHeaders.sort((left, right) => right.top - left.top)[0]
  expect(quantity, 'в PDF должна быть числовая колонка именно таблицы подбора').toBeTruthy()
  const sameRow = (name: string) => words.find((word) => compact(word.text) === name && Math.abs(word.top - quantity!.top) < 1)
  const location = sameRow('ЯЧЕЙКА')
  const sku = sameRow('SKU')
  expect(location, 'PDF сохраняет колонку Ячейка подбора').toBeTruthy()
  expect(sku, 'PDF сохраняет колонку SKU подбора').toBeTruthy()
  expect(location!.left).toBeLessThan(sku!.left)
  expect(sku!.left).toBeLessThan(quantity!.left)
  for (const allocation of allocations ?? []) {
    expectPdfTextFragments(words, allocation.location_code)
    expectPdfTextFragments(words, allocation.sku_code)
    expectPdfTextFragments(words, String(allocation.quantity))
  }
}

const forms = [
  ['приёмка/возврат', inbound],
  ['FBO WB/Ozon/самостоятельная упаковка', packaging],
  ['общая marketplace_unload', (count: number) => capturedWaybill('marketplace_unload', count)],
  ['общая operational_outbound', (count: number) => capturedWaybill('operational_outbound', count)],
  ['общая inbound_intake', (count: number) => capturedWaybill('inbound_intake', count)],
  ['FBS одиночный/групповой', fbs],
] as const

function cellOwnershipFixture(rows: string) {
  return `<!doctype html><meta charset="utf-8"><style>@page{size:A4 landscape;margin:10mm}table{border-collapse:collapse;width:100%;table-layout:fixed;font:14px Arial}th,td{text-align:left;padding:4px;vertical-align:top}td{height:170px}th:first-child{width:40%}</style><table><thead><tr><th>Товар</th><th>АРТИКУЛ</th><th>ЦВЕТ</th><th>РАЗМЕР</th></tr></thead><tbody>${rows}</tbody></table>`
}

describe('WMS-680 · C680-18 реальная PDF-геометрия', () => {
  it.each(forms)('%s: нормальная и длинная формы сохраняют отдельные колонки внутри реального PDF', async (label, build) => {
    const normal = build(4)
    const long = build(28)
    expectColumnsBeforePdf(normal)
    expectColumnsBeforePdf(long)
    const normalPdf = await renderPdf(normal, `${label}-normal`)
    const longPdf = await renderPdf(long, `${label}-long`)
    expect(normalPdf.pdf.getPageCount()).toBeGreaterThanOrEqual(1)
    expect(longPdf.pdf.getPageCount()).toBeGreaterThanOrEqual(1)
    assertRealPdfGeometry(normalPdf.text, label.includes('FBS') ? 'FBS-LONG-NAME-01-680' : label.includes('FBO') ? 'PACKAGING-LONG-NAME-01-680' : label.includes('приёмка') ? 'INBOUND-LONG-NAME-01-680' : 'WAYBILL-LONG-NAME-01-680')
    assertRealPdfGeometry(longPdf.text, label.includes('FBS') ? 'FBS-LONG-NAME-28-680' : label.includes('FBO') ? 'PACKAGING-LONG-NAME-28-680' : label.includes('приёмка') ? 'INBOUND-LONG-NAME-28-680' : 'WAYBILL-LONG-NAME-28-680')
  }, 120_000)

  it.each(['marketplace_unload', 'operational_outbound', 'inbound_intake'] as const)('C680-18: %s сохраняет компактное Кол-во в реальной DOM/PDF-таблице подбора', async (kind) => {
    const pickAllocations = [
      { location_code: 'PICK-CELL-A-680', sku_code: 'PICK-SKU-A-680', quantity: 12340 },
      { location_code: 'PICK-CELL-B-680', sku_code: 'PICK-SKU-B-680', quantity: 7 },
    ]
    const html = capturedWaybill(kind, 4, pickAllocations)
    const dom = renderPickTableDom(html, `${kind}-pick-dom`)
    const pdf = await renderPdf(html, `${kind}-pick-pdf`)
    assertPickTablePdf(pdf.text, pickAllocations)
    expect(dom.headers).toEqual(['Ячейка', 'SKU', 'Кол-во'])
    expect(dom.rows).toEqual(pickAllocations.map((allocation) => [allocation.location_code, allocation.sku_code, String(allocation.quantity)]))
    expect(dom.columns).toHaveLength(3)
    expect(dom.columns[2]!.width, 'R9: Кол-во уже текстовой Ячейки').toBeLessThan(dom.columns[0]!.width)
    expect(dom.columns[2]!.width, 'R9: Кол-во уже текстового SKU').toBeLessThan(dom.columns[1]!.width)
    expect(dom.table.left).toBeGreaterThanOrEqual(0)
    expect(dom.table.right).toBeGreaterThan(dom.table.left)
  }, 120_000)

  it('C680-18: канарейка не принимает обрезанное название, даже если остальные слова PDF сохранены', async () => {
    const expectedName = 'PACKAGING-LONG-NAME-01-680'
    const pdf = await renderPdf(packaging(4), 'fbo-complete-name-canary')
    const words = pdfWords(pdf.text)
    const fragments = expectPdfTextFragments(words, expectedName)
    expect(pdfTextFragments(words.filter((word) => word !== fragments.at(-1)), expectedName)).toBeUndefined()
  }, 120_000)

  it('C680-18: реальный PDF не склеивает название из разных строк под одинаковой X-координатой', async () => {
    const pdf = await renderPdf(cellOwnershipFixture('<tr><td>PACKAGING-LONG-</td><td></td><td></td><td></td></tr><tr><td>NAME-01-680</td><td></td><td></td><td></td></tr>'), 'cross-row')
    const words = pdfWords(pdf.text)
    const first = words.find((word) => word.text === 'PACKAGING-LONG-')!
    const second = words.find((word) => word.text === 'NAME-01-680')!
    expect(second.top - first.bottom).toBeGreaterThan(100)
    expect(() => assertRealPdfGeometry(pdf.text, 'PACKAGING-LONG-NAME-01-680')).toThrow(/полный текст/)
  }, 120_000)

  it('C680-18: реальный PDF не склеивает название из соседних колонок одной строки', async () => {
    const pdf = await renderPdf(cellOwnershipFixture('<tr><td>PACKAGING-LONG-</td><td>NAME-01-680</td><td></td><td></td></tr>'), 'cross-column')
    const words = pdfWords(pdf.text)
    expect(words.find((word) => word.text === 'NAME-01-680')!.left).toBeGreaterThan(words.find((word) => word.text === 'PACKAGING-LONG-')!.right)
    expect(() => assertRealPdfGeometry(pdf.text, 'PACKAGING-LONG-NAME-01-680')).toThrow(/полный текст/)
  }, 120_000)

  it('C680-18: реальный PDF принимает полный перенос названия внутри одной ячейки', async () => {
    const pdf = await renderPdf(cellOwnershipFixture('<tr><td>PACKAGING-LONG-<br>NAME-01-680</td><td></td><td></td><td></td></tr>'), 'wrapped-cell')
    expect(pdfWords(pdf.text).filter((word) => /PACKAGING-LONG-|NAME-01-680/.test(word.text))).toHaveLength(2)
    assertRealPdfGeometry(pdf.text, 'PACKAGING-LONG-NAME-01-680')
  }, 120_000)
})
