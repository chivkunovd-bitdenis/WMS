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

function capturedWaybill(kind: ShipmentWaybillData['docKind'], count: number) {
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
    pickAllocations: [{ location_code: 'CELL-1-680', sku_code: variants[0]!.article, quantity: 12340 }],
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
    process.kill('SIGTERM')
    const pdf = await PDFDocument.load(readFileSync(output))
    const text = execFileSync('pdftotext', ['-bbox-layout', output, '-'], { encoding: 'utf8' })
    return { pdf, text }
  } finally {
    process.kill('SIGTERM')
    rmSync(dir, { recursive: true, force: true })
  }
}

function compact(text: string) {
  return text.replace(/\s+/g, '').toUpperCase()
}

function assertRealPdfGeometry(xml: string, expectedName: string) {
  const pages = [...xml.matchAll(/<page\b[^>]*width="([\d.]+)"[^>]*height="([\d.]+)"[^>]*>([\s\S]*?)<\/page>/g)]
  expect(pages.length, 'pdftotext должен вернуть страницы реального PDF').toBeGreaterThan(0)
  const words = [...xml.matchAll(/<word\b[^>]*xMin="([\d.]+)"[^>]*yMin="([\d.]+)"[^>]*xMax="([\d.]+)"[^>]*yMax="([\d.]+)"[^>]*>([\s\S]*?)<\/word>/g)]
  expect(words.length, 'pdftotext должен вернуть реальные координаты PDF').toBeGreaterThan(0)
  expect(compact(xml)).toContain(compact(expectedName))
  for (const token of ['АРТИКУЛ', 'ЦВЕТ', 'РАЗМЕР']) expect(compact(xml)).toContain(token)
  const headerX = (token: string) => {
    const match = words.find((word) => compact(word[5]!) === token)
    expect(match, `PDF должен физически разместить заголовок «${token}»`).toBeTruthy()
    return Number(match![1])
  }
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

const forms = [
  ['приёмка/возврат', inbound],
  ['FBO WB/Ozon/самостоятельная упаковка', packaging],
  ['общая marketplace_unload', (count: number) => capturedWaybill('marketplace_unload', count)],
  ['общая operational_outbound', (count: number) => capturedWaybill('operational_outbound', count)],
  ['общая inbound_intake', (count: number) => capturedWaybill('inbound_intake', count)],
  ['FBS одиночный/групповой', fbs],
] as const

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
})
