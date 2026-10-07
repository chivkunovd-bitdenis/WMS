import { execFileSync, spawn } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import { PDFDocument } from 'pdf-lib'
import { describe, expect, it } from 'vitest'
import { LABEL_SIZES } from './labelSize'
import { buildMarkingTapeDocument } from './printMarkingCodeLabel'
import type { ProductThermalLabelData } from './printProductThermalLabel'

const chrome = [process.env.WMS_PRINT_CHROMIUM, process.env.WMS672_CHROMIUM, '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
  .find((candidate): candidate is string => Boolean(candidate && existsSync(candidate)))
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const fixtureRoot = resolve(frontend, '../var/wms702-print-tests')
const product: ProductThermalLabelData = {
  product_name: 'Кардиган классический', sku_code: '1755834805', wb_vendor_code: '1755834805', barcode: '2057623103586',
  seller_name: 'ИП Савкина В.А.', wb_size: 'S (42-44)', wb_color: 'Коричневый', wb_brand: 'ASVOYA',
  wb_composition: 'Вискоза — 50%, полиэстер — 30%, нейлон — 20%',
}
const products = [
  { name: 'seven-fields', data: product },
  { name: 'long-name-size', data: { ...product, product_name: 'Широкий шерстяной кардиган классический женский оверсайз с пуговицами и длинными рукавами', wb_size: 'Универсальный (42-56)' } },
  { name: 'wide-glyph-name', data: { ...product, product_name: 'ШЩШЩШЩШЩШЩШЩШЩШЩШЩШЩШЩШЩШЩШЩШЩШЩШЩШЩШЩ' } },
  { name: 'uppercase-cyrillic-name', data: { ...product, product_name: 'ДЦОДЦОДЦОДЦОДЦОДЦОДЦОДЦОДЦОДЦОДЦОДЦО' } },
  { name: 'two-line-name-no-brand', data: { ...product, wb_brand: null, product_name: 'Кардиган классический женский шерстяной с пуговицами и длинными рукавами' } },
  { name: 'composition-not-selected', data: { ...product, wb_composition: null } },
]
const chromeFlags = ['--headless=new', '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage', '--no-first-run', '--disable-background-networking', '--disable-component-update', '--disable-sync', '--disable-default-apps']
const evidenceOnly = process.env.WMS702_EVIDENCE_ONLY === '1'
type Row = { text: string; top: number; bottom: number; font: number }
type LabelReport = { bodyBottom: number; footerTop: number; rows: Row[]; barcodeWidth: number; barcodeHeight: number; imageComplete: boolean; naturalWidth: number; naturalHeight: number }

async function stopOwnedChrome(printing: ReturnType<typeof spawn>) {
  if (printing.exitCode !== null) return
  const exited = new Promise<void>((resolveExit) => printing.once('exit', () => resolveExit()))
  printing.kill('SIGTERM')
  await Promise.race([exited, new Promise((resolveWait) => setTimeout(resolveWait, 2000))])
  if (printing.exitCode === null) { printing.kill('SIGKILL'); await exited }
}

async function dump(html: string, dir: string): Promise<string> {
  expect(chrome, 'WMS-702 geometry requires installed Chrome; missing renderer must fail').toBeTruthy()
  const input = join(dir, 'probe.html')
  writeFileSync(input, html)
  const printing = spawn(chrome!, [...chromeFlags, `--user-data-dir=${join(dir, 'profile')}`, '--dump-dom', `file://${input}`], { stdio: ['ignore', 'pipe', 'pipe'] })
  let output = ''
  let stderr = ''
  let error: Error | undefined
  printing.stdout.on('data', (chunk: Buffer) => { output += chunk.toString() })
  printing.stderr.on('data', (chunk: Buffer) => { stderr += chunk.toString() })
  printing.on('error', (cause) => { error = cause })
  try {
    const deadline = Date.now() + 60_000
    // macOS Chrome can keep running after it has delivered --dump-dom output.
    while (!output.includes('</html>')) {
      if (error) throw error
      if (Date.now() > deadline || printing.exitCode !== null) throw new Error(`Chrome did not deliver DOM: ${stderr}`)
      await new Promise((resolveWait) => setTimeout(resolveWait, 100))
    }
    return output
  } finally { await stopOwnedChrome(printing) }
}

type ActualDocuments = { fixtures: Array<{ ordinary: string; section: string }>; onlyRequired: string }

async function actualDocuments(dir: string): Promise<ActualDocuments> {
  const jsbarcode = readFileSync(join(frontend, 'node_modules/jsbarcode/dist/JsBarcode.all.min.js'), 'utf8')
  const source = ['labelSize.ts', 'productLabelText.ts', 'renderBarcodeDataUrl.ts', 'printProductThermalLabel.ts'].map(name =>
    readFileSync(join(frontend, 'src/utils', name), 'utf8').replace(/^import[\s\S]*?from\s+['"][^'"]+['"]\s*$/gm, '').replace(/^export /gm, ''),
  ).join('\n')
  const renderer = ts.transpileModule(`const JsBarcode=window.JsBarcode;\n${source}`, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } }).outputText
  const script = `${renderer}\nconst samples=${JSON.stringify(products)};const barcode=renderBarcodeDataUrl('${product.barcode}',{variant:'thermal58'});
    const fixtures=LABEL_SIZES.flatMap(size=>samples.map(sample=>({ordinary:buildProductThermalLabelDocument(sample.data,2,barcode,undefined,size),section:buildProductLabelSectionHtml(sample.data,barcode,undefined,size)})));
    const onlyRequired=buildProductThermalLabelDocument(samples[0].data,1,barcode,{includeSize:false,includeColor:false,includeBrand:false,includeComposition:false},LABEL_SIZES[0]);
    document.getElementById('documents-result').textContent=JSON.stringify({fixtures,onlyRequired});`
  const dom = await dump(`<!doctype html><body><pre id="documents-result"></pre><script>${jsbarcode}</script><script>${script}</script></body>`, dir)
  const serialized = dom.match(/<pre id="documents-result">([\s\S]*?)<\/pre>/)?.[1]
  expect(serialized, 'Use actual browser generators with real canvas text metrics and barcode pixels').toBeTruthy()
  return JSON.parse(serialized!.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&')) as ActualDocuments
}

async function geometry(html: string, dir: string): Promise<LabelReport[]> {
  const probe = `<script>window.addEventListener('load',()=>{
    const rect=node=>node.getBoundingClientRect();
    const report=[...document.querySelectorAll('.label')].map(label=>({
      bodyBottom:rect(label.querySelector('.body')).bottom,
      footerTop:rect(label.querySelector('.footer')).top,
      rows:[...label.querySelectorAll('.body>p')].map(node=>({text:node.textContent,top:rect(node).top,bottom:rect(node).bottom,font:parseFloat(getComputedStyle(node).fontSize)*72/96})),
      barcodeWidth:rect(label.querySelector('img')).width,barcodeHeight:rect(label.querySelector('img')).height,
      imageComplete:label.querySelector('img').complete,naturalWidth:label.querySelector('img').naturalWidth,naturalHeight:label.querySelector('img').naturalHeight
    }));const pre=document.createElement('pre');pre.id='geometry-result';pre.textContent=JSON.stringify(report);document.body.append(pre);
  })</script>`
  const dom = await dump(html.replace('</body>', `${probe}</body>`), dir)
  const serialized = dom.match(/<pre id="geometry-result">([^<]+)<\/pre>/)?.[1]
  expect(serialized, 'The actual browser must return every label row').toBeTruthy()
  return JSON.parse(serialized!) as LabelReport[]
}

async function pdf(html: string, dir: string, caseIndex: number, context: string) {
  const input = join(dir, 'labels.html')
  const output = join(dir, `labels-${caseIndex}.pdf`)
  writeFileSync(input, html)
  const printing = spawn(chrome!, [...chromeFlags, '--no-pdf-header-footer', `--user-data-dir=${join(dir, 'profile')}`, `--print-to-pdf=${output}`, `file://${input}`], { stdio: 'ignore' })
  try {
    const deadline = Date.now() + 60_000
    while (!existsSync(output) || !readFileSync(output).subarray(-32).includes(Buffer.from('%%EOF'))) {
      if (Date.now() > deadline) throw new Error('Chrome did not produce a complete PDF in 60s')
      await new Promise((resolveWait) => setTimeout(resolveWait, 100))
    }
    if (process.env.WMS702_EVIDENCE_DIR && (context.startsWith('58x40/') || context.startsWith('60x40/seven-fields/'))) {
      const evidence = resolve(process.env.WMS702_EVIDENCE_DIR)
      mkdirSync(evidence, { recursive: true })
      const stem = join(evidence, context.replaceAll('/', '-'))
      copyFileSync(output, `${stem}.pdf`)
      writeFileSync(`${stem}.html`, html)
      execFileSync('pdftoppm', ['-f', '1', '-singlefile', '-png', '-r', '203', output, stem], { stdio: 'ignore' })
    }
    return { document: await PDFDocument.load(readFileSync(output)), text: execFileSync('pdftotext', ['-bbox-layout', output, '-'], { encoding: 'utf8' }) }
  } finally {
    await stopOwnedChrome(printing)
  }
}

describe('WMS-702 real ordinary WB label geometry', () => {
  it('keeps every selected field visible, separated and readable in every stock size and both print documents', async () => {
    expect(evidenceOnly && process.env.GITHUB_ACTIONS === 'true', 'CI must always execute the complete matrix').toBe(false)
    // Owned fixtures stay inside this WMS checkout. No external project is accessed.
    mkdirSync(fixtureRoot, { recursive: true })
    const dir = mkdtempSync(join(fixtureRoot, 'run-'))
    try {
      const documents = await actualDocuments(dir)
      let caseIndex = 0
      for (const [sizeIndex, size] of LABEL_SIZES.entries()) for (const [sampleIndex, sample] of products.entries()) for (const tape of [false, true]) {
        if (evidenceOnly && !(size.id === '58x40' && (!tape || sampleIndex === 0) || size.id === '60x40' && sampleIndex === 0 && !tape)) continue
        const fixture = documents.fixtures[sizeIndex * products.length + sampleIndex]!
        const html = tape ? buildMarkingTapeDocument([fixture.section, fixture.section], size) : fixture.ordinary
        const report = await geometry(html, dir)
        const context = `${size.id}/${sample.name}/${tape ? 'shared-tape' : 'ordinary'}`
        if (process.env.WMS702_EVIDENCE_DIR) {
          const evidence = resolve(process.env.WMS702_EVIDENCE_DIR)
          mkdirSync(evidence, { recursive: true })
          writeFileSync(join(evidence, context.replaceAll('/', '-') + '.json'), JSON.stringify({ context, sourceBlob: execFileSync('git', ['hash-object', join(frontend, 'src/utils/printProductThermalLabel.ts')], { encoding: 'utf8' }).trim(), report }, null, 2))
        }
        expect(report, context).toHaveLength(2)
        for (const label of report) {
          expect(label.rows, context).toHaveLength(sample.data.wb_brand && sample.data.wb_composition ? 7 : 6)
          if (sample.data.wb_brand) expect(label.rows.map(row => row.text).join(' '), context).toContain('Бренд: ASVOYA')
          if (sample.data.wb_composition) expect(label.rows.map(row => row.text).join(' '), context).toContain('Состав:')
          for (const [index, row] of label.rows.entries()) {
            expect(row.bottom, `${context}: ${row.text} must fit inside body`).toBeLessThanOrEqual(label.bodyBottom + 0.1)
            expect(row.bottom, `${context}: ${row.text} must not touch footer`).toBeLessThan(label.footerTop)
            expect(row.font, `${context}: readable compact text`).toBeGreaterThanOrEqual(5.7)
            if (index > 0) expect(row.top, `${context}: lines must never overlap`).toBeGreaterThan(label.rows[index - 1]!.bottom)
          }
          expect(label.barcodeWidth, context).toBeCloseTo(52 * Math.min(size.widthMm / 58, size.heightMm / 40) * 96 / 25.4, 0)
          expect(label.imageComplete, context).toBe(true)
          expect(label.naturalWidth, context).toBeGreaterThan(0)
          expect(label.naturalHeight, context).toBeGreaterThan(0)
          expect(label.barcodeHeight, context).toBeGreaterThan(0)
        }
        const rendered = await pdf(html, dir, caseIndex++, context)
        expect(rendered.document.getPageCount(), context).toBe(2)
        for (const page of rendered.document.getPages()) {
          expect(page.getWidth()).toBeCloseTo(size.widthMm * 72 / 25.4, 0)
          expect(page.getHeight()).toBeCloseTo(size.heightMm * 72 / 25.4, 0)
        }
        const pdfPages = [...rendered.text.matchAll(/<page\b[^>]*>([\s\S]*?)<\/page>/g)]
        expect(pdfPages, context).toHaveLength(2)
        for (const page of pdfPages) {
          // Poppler on macOS can split a Cyrillic glyph across font subsets;
          // stable numeric values prove PDF presence, while DOM proves field text.
          const values = ['2057623103586', '1755834805', sample.data.wb_size!.includes('56') ? '(42-56)' : '(42-44)']
          if (sample.data.wb_brand) values.push('ASVOYA')
          if (sample.data.wb_composition) values.push('50%,')
          for (const value of values) expect(page[1], `${context}: PDF keeps ${value}`).toContain(value)
          const lines = [...page[1]!.matchAll(/<line\b([^>]*)>([\s\S]*?)<\/line>/g)].map(match => {
            const coordinate = (name: string) => Number(match[1]!.match(new RegExp(`${name}="([0-9.]+)"`))?.[1])
            return { top: coordinate('yMin'), bottom: coordinate('yMax'), left: coordinate('xMin'), right: coordinate('xMax') }
          })
          expect(lines.length, context).toBeGreaterThanOrEqual(8)
          for (const [index, line] of lines.entries()) {
            expect(line.left, context).toBeGreaterThanOrEqual(0)
            expect(line.right, context).toBeLessThanOrEqual(size.widthMm * 72 / 25.4 + 0.5)
            expect(line.top, context).toBeGreaterThanOrEqual(0)
            expect(line.bottom, context).toBeLessThanOrEqual(size.heightMm * 72 / 25.4)
            if (index > 0) expect(line.top, `${context}: PDF text lines do not overlap`).toBeGreaterThanOrEqual(lines[index - 1]!.bottom)
          }
        }
      }
      const onlyRequired = (await geometry(documents.onlyRequired, dir))[0]!
      expect(onlyRequired.rows).toHaveLength(3)
      expect(onlyRequired.rows.every(row => row.font >= 7.5)).toBe(true)
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  }, 240_000)
})
