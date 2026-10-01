import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import * as bwipjs from 'bwip-js'
import { PDFDocument } from 'pdf-lib'
import { describe, expect, it } from 'vitest'
import { LABEL_SIZES } from './labelSize'
import { buildMarkingTapeDocument, buildWbOrderQrLabelHtml } from './printMarkingCodeLabel'
import { buildProductLabelSectionHtml } from './printProductThermalLabel'

// Opt-in real print renderer: WMS_PRINT_CHROMIUM=/path/to/chrome npm run test:unit --
// src/utils/printMarkingCodeLabel.pagination.test.ts. Requires Poppler pdfimages.
const chrome = process.env.WMS_PRINT_CHROMIUM
const cases = [
  ...LABEL_SIZES.map((size) => ({ name: size.id, size, paperHeight: size.heightMm })),
  ...[39, 38.6].map((paperHeight) => ({ name: `58x${paperHeight}-driver`, size: LABEL_SIZES[0]!, paperHeight })),
]

describe.skipIf(!chrome)('WMS-613 physical page pagination', () => {
  it.each(cases)('$name keeps 12 QR/barcode pairs on exactly 24 nonblank pages', async ({ size, paperHeight }) => {
    const dir = mkdtempSync(join(tmpdir(), 'wms613-print-test-'))
    try {
      const qr = 'data:image/png;base64,' + (await bwipjs.toBuffer({ bcid: 'qrcode', text: 'WMS-613', scale: 3 })).toString('base64')
      const barcode = 'data:image/png;base64,' + (await bwipjs.toBuffer({ bcid: 'code128', text: '2038400000123', scale: 3, height: 10 })).toString('base64')
      const product = {
        product_name: 'Куртка зимняя больших размеров с мехом и капюшоном',
        sku_code: 'ФА_МОД44а/202/42', barcode: '2038400000123', wb_size: '54', seller_name: 'ИП Фадин',
      }
      const sections = Array.from({ length: 12 }, (_, index) => [
        buildWbOrderQrLabelHtml(qr, index + 1),
        buildProductLabelSectionHtml(product, barcode, undefined, size),
      ]).flat()
      // Change only the driver page box; leave the selected label stock unchanged.
      const html = buildMarkingTapeDocument(sections, size).replace(
        `@page { size: ${size.widthMm}mm ${size.heightMm}mm;`,
        `@page { size: ${size.widthMm}mm ${paperHeight}mm;`,
      )
      const input = join(dir, 'tape.html')
      const output = join(dir, 'tape.pdf')
      writeFileSync(input, html)
      const printing = spawn(chrome!, [
        '--headless=new', '--disable-gpu', '--no-pdf-header-footer', '--no-first-run',
        `--user-data-dir=${join(dir, 'profile')}`, `--print-to-pdf=${output}`, `file://${input}`,
      ], { stdio: 'ignore' })
      try {
        // Some macOS Chrome builds stay alive after writing the PDF. Wait for the
        // completed file, then close only the isolated process started by this test.
        const deadline = Date.now() + 30_000
        while (!existsSync(output) || !readFileSync(output).subarray(-32).includes(Buffer.from('%%EOF'))) {
          if (Date.now() >= deadline) throw new Error('Chrome did not produce a complete PDF')
          await new Promise((resolve) => setTimeout(resolve, 100))
        }
      } finally {
        printing.kill('SIGTERM')
      }
      const pdf = await PDFDocument.load(readFileSync(output))
      expect(pdf.getPageCount()).toBe(24)
      // pdfimages lists images actually drawn on each page, not merely declared resources.
      const images = execFileSync('pdfimages', ['-list', output], { encoding: 'utf8' })
        .split('\n').map((line) => line.trim().split(/\s+/))
        .filter((columns) => columns[2] === 'image')
      for (let page = 1; page <= 24; page += 1) {
        const pageImages = images.filter((columns) => Number(columns[0]) === page)
        expect(pageImages.length, `page ${page} must contain a printed image`).toBeGreaterThan(0)
        expect(pageImages.some((columns) => page % 2 === 1
          ? Number(columns[3]) === Number(columns[4])
          : Number(columns[3]) > Number(columns[4]) * 2), `page ${page} must contain the expected QR/barcode`).toBe(true)
      }
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  }, 60_000)
})
