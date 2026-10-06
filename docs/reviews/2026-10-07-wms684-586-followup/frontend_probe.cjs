// Review-only evidence: no live browser, network, physical print or mutations.
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
    naive: context.inboundReceiptDate('2026-09-28T21:30:00'),
    explicitOffset: context.inboundReceiptDate('2026-09-29T01:30:00+04:00'),
    invalid: context.inboundReceiptDate('not-a-date'), absent: context.inboundReceiptDate(null) })
}
const numberSource = fs.readFileSync(path.join(root, 'frontend/src/screens/ff/documentDisplay.ts'), 'utf8')
const number = load(numberSource).exports.formatHumanDocumentNumber
const numberUsesEstablishedFunction = view.includes('`Приёмка ${formatHumanDocumentNumber(detail) ?? \'—\'} от ${inboundReceiptDate(detail?.created_at)}`')
const numbers = [
  { display_number: null, document_number: 'INB-000684' },
  { display_number: ' ', document_number: 'INB-000684' },
  { display_number: null, document_number: 'broken' },
].map(detail => ({ detail, result: number(detail) ?? '—' }))
const sourcePath = 'frontend/src/utils/printBarcodeLabel.ts'
const original = execFileSync('git', ['show', '1943e0f18a51e83a45a647f51fb565f2fab6d074:' + sourcePath], { cwd: root, encoding: 'utf8' })
const previous = execFileSync('git', ['show', '371e18f97f8c92e9f6641e51250be8abbab95139:' + sourcePath], { cwd: root, encoding: 'utf8' })
const current = fs.readFileSync(path.join(root, sourcePath), 'utf8')
function capture(source, options) {
  const dom = new JSDOM('<!doctype html><body></body>')
  dom.window.__WMS_CAPTURE_PRINT_HTML__ = true
  load(source, { window: dom.window, document: dom.window.document, setTimeout: () => {} }).exports.printBarcodeLabels(options)
  const html = dom.window.__WMS_LAST_PRINT_HTML__
  dom.window.close()
  return html
}
const layouts = []
for (const [widthMm, heightMm] of [[58, 40], [60, 40], [60, 80], [70, 120]]) {
  const labelSize = { id: `${widthMm}x${heightMm}`, widthMm, heightMm }
  const options = ['Грузоместо № 1', 'Короб отгрузки'].map((title, i) => ({ title,
    barcode: `CODE-${i}`, barcodeDataUrl: 'data:image/png;base64,AA==', labelSize, layout: 'internalBox' }))
  const before = capture(original, options), after = capture(current, options)
  const receiptOptions = options.map(option => ({ ...option, metadata: ['Короб № 1', 'ИП Иванов', 'Приёмка №000684 от 29.09.2026'] }))
  layouts.push({ size: labelSize.id,
    otherStylesEqualFrozen: before.match(/<style>([\s\S]*?)<\/style>/)[1] === after.match(/<style>([\s\S]*?)<\/style>/)[1],
    otherHtmlEqualIgnoringWhitespace: before.replace(/\s+/g, ' ') === after.replace(/\s+/g, ' '),
    receiptHtmlEqualPreviousProduct: capture(previous, receiptOptions) === capture(current, receiptOptions) })
  if (labelSize.id === '58x40') {
    fs.writeFileSync(path.join(__dirname, 'other-labels-before.html'), before.replace(/^[ \t]+$/gm, ''))
    fs.writeFileSync(path.join(__dirname, 'other-labels-after.html'), after.replace(/^[ \t]+$/gm, ''))
  }
}
const results = { dates, numberUsesEstablishedFunction, numbers, layouts }
fs.writeFileSync(path.join(__dirname, 'frontend-results.json'), JSON.stringify(results, null, 2) + '\n')
console.log(JSON.stringify(results, null, 2))
