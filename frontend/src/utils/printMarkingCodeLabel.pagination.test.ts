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

// Real-renderer test for WMS-613. Local opt-in via WMS_PRINT_CHROMIUM.
// CI must set WMS_REQUIRE_PRINT_PAGINATION=1 together with Chrome + Poppler so a
// missing dependency fails loudly instead of green-skipping.
const chrome = process.env.WMS_PRINT_CHROMIUM
const requirePagination = process.env.WMS_REQUIRE_PRINT_PAGINATION === '1'
const cases = [
  ...LABEL_SIZES.map((size) => ({ name: size.id, size, paperHeight: size.heightMm })),
  ...[39, 38.6].map((paperHeight) => ({ name: `58x${paperHeight}-driver`, size: LABEL_SIZES[0]!, paperHeight })),
]

function pdfimagesAvailable(): boolean {
  try {
    execFileSync('pdfimages', ['-v'], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

// Hard CI gate: never silently green-skip when the pipeline promised a real check.
describe('WMS-613 CI gate · WMS_REQUIRE_PRINT_PAGINATION', () => {
  it('requires an executable Chrome and Poppler pdfimages when the gate flag is set', () => {
    if (!requirePagination) return
    expect(chrome, 'WMS_PRINT_CHROMIUM must point to a Chromium/Chrome binary when WMS_REQUIRE_PRINT_PAGINATION=1').toBeTruthy()
    expect(existsSync(chrome!), `WMS_PRINT_CHROMIUM path does not exist: ${chrome}`).toBe(true)
    expect(pdfimagesAvailable(), 'poppler-utils (pdfimages) must be installed and on PATH when WMS_REQUIRE_PRINT_PAGINATION=1').toBe(true)
  })
})

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
      // WMS-652: run the isolated local HTML renderer without Chrome background
      // networking, component updates, account sync or default-app installation.
      // CI 37142284424 timed out with background-network warnings; their causal
      // role is unproven. These standard automation flags are an experiment to
      // verify in Linux CI. PDF content, page assertions and deadlines stay unchanged.
      // --no-sandbox is limited to this synthetic HTML and disposable test profile.
      const printing = spawn(chrome!, [
        '--headless=new', '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage',
        '--no-pdf-header-footer', '--no-first-run',
        '--disable-background-networking', '--disable-component-update',
        '--disable-sync', '--disable-default-apps',
        `--user-data-dir=${join(dir, 'profile')}`, `--print-to-pdf=${output}`, `file://${input}`,
      ], { stdio: ['ignore', 'pipe', 'pipe'] })
      type ExitInfo = { code: number | null; signal: NodeJS.Signals | null }
      const io: { stderr: string; stdout: string; error: Error | null; exit: ExitInfo | null } = {
        stderr: '', stdout: '', error: null, exit: null,
      }
      printing.on('error', (error) => { io.error = error })
      printing.stderr?.on('data', (chunk: Buffer) => { io.stderr += chunk.toString('utf8') })
      printing.stdout?.on('data', (chunk: Buffer) => { io.stdout += chunk.toString('utf8') })
      printing.on('exit', (code, signal) => { io.exit = { code, signal } })
      try {
        // Some macOS Chrome builds stay alive after writing the PDF. Wait for the
        // completed file; also fail fast if Chrome exited early without a PDF.
        const deadline = Date.now() + 30_000
        while (!existsSync(output) || !readFileSync(output).subarray(-32).includes(Buffer.from('%%EOF'))) {
          if (io.error) throw new Error(`Chrome spawn failed: ${io.error.message}\nstderr: ${io.stderr || '(empty)'}`)
          if (io.exit && !existsSync(output)) {
            throw new Error(
              `Chrome exited early (code=${io.exit.code}, signal=${io.exit.signal}) without producing the PDF.\n` +
              `binary: ${chrome}\nstderr: ${io.stderr || '(empty)'}\nstdout: ${io.stdout || '(empty)'}`,
            )
          }
          if (Date.now() >= deadline) {
            throw new Error(
              `Chrome did not produce a complete PDF in 30s.\nbinary: ${chrome}\n` +
              `exited: ${io.exit ? JSON.stringify(io.exit) : 'still running'}\n` +
              `stderr: ${io.stderr || '(empty)'}\nstdout: ${io.stdout || '(empty)'}`,
            )
          }
          await new Promise((resolve) => setTimeout(resolve, 100))
        }
      } finally {
        // Close only the isolated process this test started; wait briefly for exit
        // so that an active Chrome does not keep writing into the dir we are about
        // to rmSync.
        if (!io.exit) {
          printing.kill('SIGTERM')
          const forceKill = Date.now() + 2_000
          while (!io.exit && Date.now() < forceKill) {
            await new Promise((resolve) => setTimeout(resolve, 50))
          }
          if (!io.exit) {
            printing.kill('SIGKILL')
            const hardDeadline = Date.now() + 2_000
            while (!io.exit && Date.now() < hardDeadline) {
              await new Promise((resolve) => setTimeout(resolve, 50))
            }
          }
        }
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
