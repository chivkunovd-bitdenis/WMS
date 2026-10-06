// Review-only probe. No browser, network, printing, or product mutations.
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { execFileSync } = require('node:child_process')
const { createRequire } = require('node:module')
const root = path.resolve(__dirname, '../../..')
const requireFrontend = createRequire(path.join(root, 'frontend/package.json'))
const ts = requireFrontend('typescript')
const { JSDOM } = requireFrontend('jsdom')
const view = fs.readFileSync(path.join(root, 'frontend/src/screens/ff/FfInboundRequestView.tsx'), 'utf8')
const dateSource = view.slice(view.indexOf('function inboundReceiptDate('), view.indexOf('\nfunction isGeneratedInboundBoxBarcode'))
const numberSource = fs.readFileSync(path.join(root, 'frontend/src/screens/ff/documentDisplay.ts'), 'utf8')
function load(source, extra = {}) {
  const context = { exports: {}, ...extra }
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, context)
  return context
}
const dates = []
for (const timezone of ['UTC', 'Europe/Moscow', 'Asia/Tbilisi']) {
  process.env.TZ = timezone
  const context = load(dateSource)
  dates.push({ timezone, zoned: context.inboundReceiptDate('2026-09-28T21:30:00Z'),
    naive: context.inboundReceiptDate('2026-09-28T21:30:00') })
}
const canonicalNumber = load(numberSource).exports.formatHumanDocumentNumber
const directNumber = view.match(/\$\{\(detail\?\.display_number \|\| detail\?\.document_number[^}]+\}/)[0]
const numbers = [
  { display_number: null, document_number: 'INB-000684' },
  { display_number: ' ', document_number: 'INB-000684' },
  { display_number: null, document_number: 'broken' },
].map(detail => ({ detail, canonical: canonicalNumber(detail),
  sticker: (detail.display_number || detail.document_number || '—').trim() || '—' }))
const sourcePath = 'frontend/src/utils/printBarcodeLabel.ts'
function capture(source) {
  const dom = new JSDOM('<!doctype html><body></body>')
  dom.window.__WMS_CAPTURE_PRINT_HTML__ = true
  const context = load(source, { window: dom.window, document: dom.window.document, setTimeout: () => {} })
  context.exports.printBarcodeLabel({ title: 'Грузоместо № 1', barcode: 'CARGO-1',
    barcodeDataUrl: 'data:image/png;base64,AA==', labelSize: { id: '58x40', widthMm: 58, heightMm: 40 }, layout: 'internalBox' })
  const html = dom.window.__WMS_LAST_PRINT_HTML__
  dom.window.close()
  return html
}
const before = capture(execFileSync('git', ['show', '1943e0f18a51e83a45a647f51fb565f2fab6d074:' + sourcePath], { cwd: root, encoding: 'utf8' }))
const after = capture(fs.readFileSync(path.join(root, sourcePath), 'utf8'))
// Remove whitespace-only lines for Git hygiene; retain all content and CSS.
fs.writeFileSync(path.join(__dirname, 'cargo-before.html'), before.replace(/^[ \t]+$/gm, ''))
fs.writeFileSync(path.join(__dirname, 'cargo-after.html'), after.replace(/^[ \t]+$/gm, ''))
const results = { dates, numbers, directNumber, cargoHtmlEqual: before === after,
  cargoCssBefore: before.match(/\.wrap \{ width: 100%; height: 100%;[^}]+\}/)[0],
  cargoCssAfter: after.match(/\.wrap \{ width: 100%; height: 100%;[^}]+\}/)[0] }
fs.writeFileSync(path.join(__dirname, 'frontend-probe.json'), JSON.stringify(results, null, 2) + '\n')
console.log(JSON.stringify(results, null, 2))
