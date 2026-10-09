const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const { JSDOM, VirtualConsole } = require('/Users/deniscivkunov/Projects/WMS/frontend/node_modules/jsdom')
const root = path.resolve(__dirname, '..')
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const errors = [], results = []
async function open(name) {
  const vc = new VirtualConsole()
  vc.on('jsdomError', error => errors.push(error.message))
  const dom = new JSDOM(fs.readFileSync(path.join(root, name), 'utf8'), { runScripts: 'outside-only', pretendToBeVisual: true, url: `file://${root}/${name}`, virtualConsole: vc })
  dom.window.Blob = Blob
  dom.window.TextEncoder = TextEncoder
  dom.window.URL.createObjectURL = blob => { dom.window.lastBlob = blob; return 'blob:demo' }
  dom.window.URL.revokeObjectURL = () => {}
  dom.window.HTMLAnchorElement.prototype.click = function() { dom.window.lastFilename = this.download }
  dom.window.HTMLCanvasElement.prototype.getContext = () => ({ measureText: text => ({ width: text.length * 7 }) })
  dom.window.eval(fs.readFileSync(path.join(root, 'assets/app.js'), 'utf8'))
  await delay(100)
  return dom
}
function click(dom, selector) { const el = dom.window.document.querySelector(selector); assert(el, selector); el.click() }
function button(dom, text) { const el = [...dom.window.document.querySelectorAll('button')].find(el => el.textContent === text); assert(el, text); el.click() }
function change(dom, input, value) {
  Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value)
  input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
}
async function chooseScenario(dom, label) {
  dom.window.document.querySelector('[data-testid="scenario"] [role="combobox"]').dispatchEvent(new dom.window.MouseEvent('mousedown', { bubbles: true, button: 0 })); await delay(25)
  const option = [...dom.window.document.querySelectorAll('[role="option"]')].find(el => el.textContent === label)
  assert(option, label); option.click(); await delay(60)
}
function snapshot(dom) { return JSON.parse(dom.window.document.querySelector('[data-testid="last-snapshot"]').textContent) }
async function exportClick(dom, variant) {
  if (variant === 2) { click(dom, '[data-testid="doc-actions"]'); await delay(20) }
  click(dom, '[data-testid="export"]'); await delay(30)
}
async function run() {
  const gallery = await open('index.html')
  assert.equal(gallery.window.document.querySelectorAll('a[href^="./variant-"]').length, 2)
  results.push('Gallery links open both variants'); gallery.window.close()
  for (const variant of [1, 2]) {
    const dom = await open(`variant-${variant}.html`), doc = dom.window.document
    assert.equal(doc.querySelectorAll('[data-testid^="box-code-"]').length, 3)
    await exportClick(dom, variant)
    const exported = snapshot(dom)
    assert.equal(exported.rows.reduce((n, r) => n + r.quantity, 0), 90)
    assert.equal(exported.seller, 'ООО «Демо Текстиль»')
    assert.equal(exported.supply, '56000126')
    const bytes = Buffer.from(await dom.window.lastBlob.arrayBuffer())
    assert.equal(bytes.readUInt32LE(0), 0x04034b50)
    fs.writeFileSync(path.join(root, 'verification', `variant-${variant}-demo.xlsx`), bytes)
    click(dom, '[data-testid="transmit"]'); await delay(600)
    assert.deepEqual(snapshot(dom), exported)
    assert.match(doc.querySelector('[data-testid="notice"]').textContent, /Макет: состав передан/)
    // One unique code is used for its card and its actual Code128 label.
    click(dom, '[aria-label="Печать ШК короба 1"]'); await delay(30)
    assert.match(doc.querySelector('[role="dialog"]').textContent, /WHB-7K2M8N4P6R9T3V/)
    click(dom, '[data-testid="box-label-print-dialog-confirm"]'); await delay(60)
    assert(doc.querySelector('svg[aria-label="Штрихкод WHB-7K2M8N4P6R9T3V"]'))
    button(dom, 'Скачать этикетки'); await delay(20)
    assert.match(await dom.window.lastBlob.text(), /@page\{size:58mm 40mm/)
    assert.match(await dom.window.lastBlob.text(), /WHB-7K2M8N4P6R9T3V/)
    const close = [...doc.querySelectorAll('[role="dialog"] button')].find(el => el.textContent === 'Закрыть'); close.click(); await delay(30)
    // Packing progress does not block either transmission method.
    await chooseScenario(dom, 'Осталось разложить 5 шт.')
    assert.equal(doc.querySelector('[data-testid="transmit"]').disabled, false)
    await exportClick(dom, variant)
    assert.equal(snapshot(dom).rows.reduce((n, r) => n + r.quantity, 0), 85)
    click(dom, '[data-testid="fill-3"]'); await delay(40)
    const input = doc.querySelector('[aria-label="Количество DEMO-SOCK-03"]')
    change(dom, input, '5'); await delay(20)
    const row = input.closest('tr'); [...row.querySelectorAll('button')].find(el => el.textContent === 'Добавить').click(); await delay(40)
    const finish = [...doc.querySelectorAll('[role="dialog"] button')].find(el => el.textContent === 'Закрыть'); finish.click(); await delay(40)
    await exportClick(dom, variant)
    assert.equal(snapshot(dom).rows.reduce((n, r) => n + r.quantity, 0), 90)
    // The error state never claims delivery.
    await chooseScenario(dom, 'WB отклонил состав')
    click(dom, '[data-testid="transmit"]'); await delay(600)
    assert.match(doc.querySelector('[data-testid="notice"]').textContent, /WB отклонил/)
    // Unknown response checks the previous operation before retransmitting.
    await chooseScenario(dom, 'Ответ WB не получен')
    click(dom, '[data-testid="transmit"]'); await delay(600)
    assert.equal(doc.querySelector('[data-testid="transmit"]').textContent, 'Проверить результат в WB')
    doc.querySelector('[aria-label="Убрать из короба"]').click(); await delay(40)
    await exportClick(dom, variant)
    click(dom, '[data-testid="transmit"]'); await delay(600)
    assert.match(doc.querySelector('[data-testid="notice"]').textContent, /Текущая раскладка в WMS изменена/)
    results.push(`Variant ${variant}: export, same payload, print Code128, incomplete packing, quantity edits, error, unknown outcome and changed layout passed`)
    dom.window.close()
  }
  assert.deepEqual(errors, [])
  const report = { result: 'passed', method: 'JSDOM functional smoke, not browser visual verification', checks: results, browser: 'Not verified: Chrome launch denied by environment', productChanged: false }
  fs.writeFileSync(path.join(root, 'verification', 'checks.json'), JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify(report, null, 2))
}
fs.mkdirSync(path.join(root, 'verification'), { recursive: true })
run().catch(error => { console.error(error); process.exit(1) })
