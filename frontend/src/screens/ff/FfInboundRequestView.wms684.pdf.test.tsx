// @vitest-environment jsdom
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { execFileSync, spawn } from 'node:child_process'
import { resolve } from 'node:path'
import { BinaryBitmap, DecodeHintType, HybridBinarizer, MultiFormatReader, RGBLuminanceSource, BarcodeFormat } from '@zxing/library'
import { PNG } from 'pngjs'
import { expect, it } from 'vitest'
import { act } from 'react'
import { PDFDocument } from 'pdf-lib'
import { harness } from '../../test-contracts/inbound684586Harness'
import { LABEL_SIZES } from '../../utils/labelSize'


async function chromePdf(chrome: string, html: string, output: string, profile: string) {
  rmSync(output, { force: true })
  const child = spawn(chrome, ['--headless=new', '--no-sandbox', '--disable-gpu', '--disable-extensions',
    '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
    '--disable-component-update', '--disable-gpu-shader-disk-cache', '--disk-cache-size=1', '--media-cache-size=1',
    '--no-pdf-header-footer', '--virtual-time-budget=1000', `--user-data-dir=${profile}`,
    `--print-to-pdf=${output}`, `file://${html}`], { detached: true, stdio: 'ignore' })
  let launchError: Error | undefined
  child.on('error', error => { launchError = error })
  const stop = (signal: NodeJS.Signals) => {
    if (child.pid) try { process.kill(-child.pid, signal) } catch { /* process already exited */ }
  }
  const interrupted = () => { stop('SIGTERM'); stop('SIGKILL') }
  process.once('SIGINT', interrupted)
  process.once('SIGTERM', interrupted)
  const closed = new Promise<void>(resolve => child.once('close', () => resolve()))
  try {
    // Chrome 154 on this macOS writes a complete PDF but can remain alive after
    // printing. Wait for an actual complete output, then terminate only this
    // test's isolated process group. No existing browser session is touched.
    const deadline = Date.now() + 20000
    while (Date.now() < deadline) {
      if (launchError) throw launchError
      if (existsSync(output) && readFileSync(output).subarray(-64).toString().includes('%%EOF')) return
      if (child.exitCode !== null && child.exitCode !== 0) throw new Error(`Chromium exited ${child.exitCode}`)
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    throw new Error('Chromium did not produce a complete PDF within 20 seconds')
  } finally {
    stop('SIGTERM')
    await Promise.race([closed, new Promise(resolve => setTimeout(resolve, 150))])
    stop('SIGKILL')
    await Promise.race([closed, new Promise(resolve => setTimeout(resolve, 1000))])
    process.removeListener('SIGINT', interrupted)
    process.removeListener('SIGTERM', interrupted)
  }
}

// K6 uses existing Chromium, pdf-lib and Poppler (already installed by frontend CI). No dependency install,
// screenshots, real printers, or changed shared node_modules are involved.

async function readPdf(output: string, scratch: string) {
  const doc = await PDFDocument.load(readFileSync(output).toString('base64'))
  return doc.getPages().map((page, index) => {
    const ordinal = String(index + 1)
    const text = execFileSync('pdftotext', ['-f', ordinal, '-l', ordinal, '-layout', output, '-'], { timeout: 15000 }).toString()
    execFileSync('pdftoppm', ['-r', '288', '-f', ordinal, '-l', ordinal, '-singlefile', '-png', output, resolve(scratch, 'page')], { timeout: 15000, stdio: 'ignore' })
    return { width: page.getWidth(), height: page.getHeight(), text,
      png: readFileSync(resolve(scratch, 'page.png')).toString('base64') }
  })
}

function decode(base64: string) {
  const png = PNG.sync.read(Buffer.from(base64, 'base64'))
  const gray = new Uint8ClampedArray(png.width * png.height)
  for (let i = 0; i < gray.length; i++) gray[i] = png.data[i * 4]!
  const reader = new MultiFormatReader()
  reader.setHints(new Map([[DecodeHintType.POSSIBLE_FORMATS, [BarcodeFormat.CODE_128]]]))
  return reader.decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(gray, png.width, png.height)))).getText()
}

it('K6 Chromium PDF pages match every selected stock and decode original barcodes in both paths', async () => {
  const chrome = process.env.WMS_TEST_CHROME ?? process.env.WMS_PRINT_CHROMIUM ?? [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium',
  ].find(existsSync)
  expect(chrome, 'K6 needs local Chromium; do not silently skip this contract').toBeTruthy()
  mkdirSync(resolve('../.agent-runs'), { recursive: true })
  const scratch = mkdtempSync(resolve('../.agent-runs/label-pdf-contract-'))
  const h = harness()
  try {
    for (const seller of ['ИП Иванов', 'ИП Очень длинное кириллическое имя и фамилия «Торговая компания зимней коллекции» & партнёры']) {
      h.current.seller_name = seller
      await h.remount()
      for (const size of LABEL_SIZES) for (const all of [false, true]) {
        const doc = await h.print(all, 2, size.id)
        const sections = [...doc.querySelectorAll('section.label')]
        for (const section of sections) expect(section.textContent).toContain(seller)
        const html = resolve(scratch, 'label.html'), output = resolve(scratch, 'label.pdf')
        writeFileSync(html, '<!doctype html>' + doc.documentElement.outerHTML)
      await act(async () => { await chromePdf(chrome!, html, output, `${scratch}/profile`) })
        expect(readFileSync(output).subarray(0, 5).toString()).toBe('%PDF-')
        const pages = await readPdf(output, scratch)
        const boxes = all ? h.current.boxes : [h.current.boxes[1]!]
        expect(pages).toHaveLength(boxes.length)
        for (let i = 0; i < pages.length; i++) {
          const page = pages[i]!
          expect(Math.abs(page.width * 25.4 / 72 - size.widthMm)).toBeLessThan(0.5)
          expect(Math.abs(page.height * 25.4 / 72 - size.heightMm)).toBeLessThan(0.5)
          expect(page.text.trim()).not.toBe('')
          expect(page.text).toContain('000684')
          expect(page.text).toContain('28.09.2026')
          expect(page.text.replace(/\s+/g, '')).toContain(seller.replace(/\s+/g, ''))
          expect(decode(page.png)).toBe(boxes[i]!.internal_barcode)
        }
        // Keep bounded digital evidence only when explicitly requested by runner.
        if (process.env.WMS_TEST_KEEP_LABEL_PDF) {
          writeFileSync(resolve('../.agent-runs', `K6-${size.id}-${all ? 'bulk' : 'single'}-${seller === 'ИП Иванов' ? 'short' : 'long'}.pdf`), readFileSync(output))
        }
      }
    }
  } finally {
    await h.dispose()
    rmSync(scratch, { recursive: true, force: true })
  }
}, 240000)

it('K6 preserved browser PDF keeps dimensions and original code128 on every stock', async () => {
  const chrome = process.env.WMS_TEST_CHROME ?? process.env.WMS_PRINT_CHROMIUM ?? ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium'].find(existsSync)
  expect(chrome).toBeTruthy()
  mkdirSync(resolve('../.agent-runs'), { recursive: true })
  const scratch = mkdtempSync(resolve('../.agent-runs/label-pdf-preserved-'))
  const h = harness()
  try {
    await h.render()
    for (const size of LABEL_SIZES) for (const all of [false, true]) {
      const doc = await h.print(all, 2, size.id)
      const html = resolve(scratch, 'label.html'), output = resolve(scratch, 'label.pdf')
      writeFileSync(html, '<!doctype html>' + doc.documentElement.outerHTML)
      await act(async () => { await chromePdf(chrome!, html, output, `${scratch}/profile`) })
      expect(readFileSync(output).subarray(0, 5).toString()).toBe('%PDF-')
      const pages = await readPdf(output, scratch)
      const boxes = all ? h.current.boxes : [h.current.boxes[1]!]
      expect(pages).toHaveLength(boxes.length)
      for (let i = 0; i < pages.length; i++) {
        expect(Math.abs(pages[i]!.width * 25.4 / 72 - size.widthMm)).toBeLessThan(0.5)
        expect(Math.abs(pages[i]!.height * 25.4 / 72 - size.heightMm)).toBeLessThan(0.5)
        expect(pages[i]!.text.trim()).not.toBe('')
        expect(decode(pages[i]!.png)).toBe(boxes[i]!.internal_barcode)
      }
    }
  } finally { await h.dispose(); rmSync(scratch, { recursive: true, force: true }) }
}, 180000)
