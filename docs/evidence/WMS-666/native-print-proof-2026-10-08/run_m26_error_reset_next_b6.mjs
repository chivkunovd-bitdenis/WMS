import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'

const here = new URL('.', import.meta.url).pathname
const run = 'run-b6d23148/m26-error-reset-next'
const out = `${here}${run}`
const backend = process.env.WMS666_BACKEND || 'http://127.0.0.1:16692'
const origin = process.env.WMS666_ORIGIN || 'http://127.0.0.1:16696'
const printOrigin = process.env.WMS666_PRINT_ORIGIN || 'http://127.0.0.1:17843'
const cdpPort = Number(process.env.WMS666_CDP_PORT || 16697)
const productSha = 'b6d23148f1571d08d13d83c6179c385e2f6a1efc'
assert.equal(process.env.WMS666_PRODUCT_SHA, productSha)
assert.equal(process.env.WMS666_RUNTIME_SHA, productSha)
const seed = JSON.parse(await readFile(`${out}/seed-public.json`, 'utf8'))
await mkdir(`${out}/native`, { recursive: true })

const chrome = spawn(process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--mute-audio', '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--disable-extensions', '--disable-cache', '--disable-crash-reporter', '--disable-breakpad',
  '--disk-cache-size=1', '--media-cache-size=1', `--user-data-dir=${out}/native/chrome-profile`, `--remote-debugging-port=${cdpPort}`, 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] })
let chromeLog = ''
chrome.stderr.on('data', chunk => { chromeLog += chunk.toString() })

class CDP {
  constructor(url) {
    this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.listeners = new Map(); this.errors = []
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject })
    this.ws.onmessage = event => {
      const msg = JSON.parse(event.data)
      if (!msg.id) { for (const fn of this.listeners.get(msg.method) || []) Promise.resolve(fn(msg.params)).catch(e => this.errors.push(String(e))); return }
      const item = this.pending.get(msg.id); if (!item) return
      this.pending.delete(msg.id); msg.error ? item.reject(Error(JSON.stringify(msg.error))) : item.resolve(msg.result)
    }
  }
  async send(method, params = {}) {
    await this.ready; const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params }))
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }))
  }
  on(method, fn) { this.listeners.set(method, [...(this.listeners.get(method) || []), fn]) }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails))
    return r.result.value
  }
}
const wait = async (predicate, timeout = 30000) => {
  const until = Date.now() + timeout
  while (Date.now() < until) { if (await predicate()) return; await delay(100) }
  throw Error('timed out waiting for UI/API predicate')
}
const get = async path => {
  const response = await fetch(`${backend}${path}`)
  if (!response.ok) throw Error(`${path} returned HTTP ${response.status}`)
  return response.json()
}
const post = async path => {
  const response = await fetch(`${printOrigin}${path}`, { method: 'POST' })
  if (!response.ok) throw Error(`${path} returned HTTP ${response.status}`)
  return response.json()
}
const apiEvents = []; const printInputs = []; let cdp
const saveJson = (name, value) => writeFile(`${out}/native/${name.endsWith('.json') ? name : `${name}.json`}`, JSON.stringify(value, null, 2) + '\n')
try {
  assert.equal((await get('/idle')).active, 0, 'isolated API has no active mutations')
  const beforeDb = await get('/snapshot')
  const initialNative = await post('/_proof/status')
  const initialReceiptCount = initialNative.accepted_png_count
  const orderA = beforeDb.orders.find(row => row.id === seed.order_ids[0])
  const orderB = beforeDb.orders.find(row => row.id === seed.order_ids[1])
  assert.equal(orderA.sticker_barcode, seed.order_sticker_barcodes[0])
  assert.equal(orderB.sticker_barcode, seed.order_sticker_barcodes[1])
  await saveJson('db-before.json', beforeDb)
  await saveJson('native-before.json', initialNative)

  await wait(async () => { try { return (await fetch(`http://127.0.0.1:${cdpPort}/json/version`)).ok } catch { return false } }, 25000)
  const tabs = await (await fetch(`http://127.0.0.1:${cdpPort}/json/list`)).json()
  cdp = new CDP(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl)
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  cdp.on('Fetch.requestPaused', async ({ requestId, request }) => {
    const url = new URL(request.url)
    if (url.origin === origin && url.pathname.startsWith('/api/')) {
      if (request.method === 'OPTIONS') {
        await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [
          { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: '*' },
        ] })
        return
      }
      const path = `/proxy${url.pathname.slice(4)}${url.search}`
      const upstream = await fetch(`${backend}${path}`, {
        method: request.method,
        headers: { 'Content-Type': request.headers['content-type'] || 'application/json' },
        ...(request.postData ? { body: request.postData } : {}),
      })
      const bytes = Buffer.from(await upstream.arrayBuffer())
      const type = upstream.headers.get('Content-Type') || 'application/json'
      let body = null
      try { if (type.includes('json')) body = JSON.parse(bytes.toString()) } catch {}
      const event = { at: new Date().toISOString(), method: request.method, path, status: upstream.status,
        ...(request.postData ? { request: JSON.parse(request.postData) } : {}), ...(body === null ? {} : { response: body }) }
      apiEvents.push(event); await saveJson('api-events', apiEvents)
      await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: upstream.status, responseHeaders: [
        { name: 'Content-Type', value: type }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' },
      ], body: bytes.toString('base64') })
      return
    }
    if (url.origin === printOrigin && url.pathname === '/print' && request.method === 'POST' && request.postData) {
      const body = JSON.parse(request.postData)
      printInputs.push({ at: new Date().toISOString(), idempotencyKey: body.idempotencyKey })
      await saveJson('print-inputs', printInputs)
    }
    await cdp.send('Fetch.continueRequest', { requestId })
  })
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.clear();sessionStorage.clear();
    localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',${JSON.stringify(JSON.stringify({ printQr: true, printChz: false, reprintChz: false, printChzCopies: 1, reprintChzCopies: 1 }))});
    localStorage.setItem('wms.print.labelSizeId','60x80');
    sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');
    sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing');
  ` })
  await cdp.send('Page.navigate', { url: `${origin}/app/ff/fbs?supply_id=${seed.supply_id}` })
  await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)'))`))

  const ui = () => cdp.eval(`(()=>{const visibleText=(node)=>{if(!node)return '';const style=getComputedStyle(node);const rect=node.getBoundingClientRect();return style.display!=='none'&&style.visibility!=='hidden'&&style.opacity!=='0'&&(rect.width>0||rect.height>0)?node.textContent?.trim()||'':''};const activeRow=document.querySelector('[data-testid="fbs-kiz-row-active"]');const visibleError=visibleText(document.querySelector('[data-testid="fbs-unified-scan"] [role="alert"]'))||visibleText(activeRow?.querySelector('[data-testid="fbs-kiz-scan-error"]'));return {url:location.href,alert:visibleText(document.querySelector('[role="alert"]')),error:visibleError,message:document.querySelector('[data-testid="fbs-kiz-scan-message"]')?.textContent||'',active:document.querySelector('[data-testid="fbs-kiz-scan-active"]')?.innerText||null,activeRow:activeRow?.getAttribute('data-order-id')||null,kizInput:document.querySelector('[data-testid="fbs-kiz-scan-input"]')?.outerHTML||null,rowInput:activeRow?.querySelector('[data-testid="fbs-kiz-row-input"]')?.outerHTML||null,scanner:{value:document.querySelector('[data-packing-scan]')?.value||'',placeholder:document.querySelector('[data-packing-scan]')?.placeholder||'',disabled:document.querySelector('[data-packing-scan]')?.disabled??true},reset:{exists:Boolean(document.querySelector('[data-testid="fbs-kiz-scan-reset"]')),disabled:document.querySelector('[data-testid="fbs-kiz-scan-reset"]')?.disabled??null},body:document.body.innerText.slice(-2000)}})()`)
  const screenshot = async name => writeFile(`${out}/native/${name}.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  const physicalScan = async (value, label) => {
    await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)'))`))
    await cdp.eval(`document.querySelector('[data-packing-scan]').focus()`)
    await cdp.send('Input.insertText', { text: value })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await saveJson(`physical-${label}`, { at: new Date().toISOString(), value })
  }
  await saveJson('ui-before.json', await ui()); await screenshot('ui-before')

  await physicalScan(orderA.sticker_barcode, 'sticker-A')
  await wait(() => apiEvents.some(row => row.path.includes('/fbs-orders/kiz/lookup') && row.status === 200 && row.response?.order_id === orderA.id))
  await wait(() => apiEvents.some(row => row.path.endsWith('/scan-auto-print') && row.status === 200 && row.response?.order_id === orderA.id))
  await wait(async () => { const current = await ui(); return current.activeRow === orderA.id && Boolean(current.rowInput) })
  const selectedA = await ui(); await saveJson('ui-A-selected', selectedA); await screenshot('ui-A-selected')
  const aLookup = apiEvents.findLast(row => row.path.includes('/fbs-orders/kiz/lookup') && row.status === 200)
  assert.equal(aLookup.response.order_id, orderA.id, 'the actual persisted A sticker selects A')
  assert.equal(selectedA.activeRow, orderA.id, 'the visible row active marker identifies A after scanning its persisted sticker barcode')

  const invalidKiz = 'NOT-A-VALID-CIS-WMS666'
  await cdp.eval(`document.querySelector('[data-testid="fbs-kiz-row-active"] [data-testid="fbs-kiz-row-input"]').focus()`)
  await cdp.send('Input.insertText', { text: invalidKiz })
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await wait(() => apiEvents.some(row => row.path.endsWith('/fbs-orders/kiz/validate') && row.status >= 400))
  const validationRequests = apiEvents.filter(row => row.path.endsWith('/fbs-orders/kiz/validate'))
  assert.equal(validationRequests.length, 1, 'one row Enter produces exactly one KIZ validation request')
  assert.equal(validationRequests[0].method, 'POST')
  assert.deepEqual(validationRequests[0].request, { order_id: orderA.id, value: invalidKiz }, 'the active A row and exact scanned KIZ are validated')
  assert.equal(apiEvents.filter(row => row.path.endsWith('/fbs-orders/kiz/commit')).length, 0, 'validation rejection is not committed')
  assert.equal(printInputs.length, 0, 'invalid KIZ dispatches no native print request')
  const rejectedNative = await post('/_proof/status')
  assert.equal(rejectedNative.accepted_png_count, initialReceiptCount, 'invalid KIZ creates no native receipt')
  await wait(async () => Boolean((await ui()).error), 15000)
  const failedUi = await ui(); const failedDb = await get('/snapshot'); const failedNative = await post('/_proof/status')
  await saveJson('after-invalid-kiz.json', { invalidKiz, ui: failedUi, db: failedDb, native: failedNative })
  await screenshot('after-invalid-kiz')
  const validation = apiEvents.findLast(row => row.path.endsWith('/fbs-orders/kiz/validate'))
  assert(validation && validation.status >= 400, 'invalid KIZ was rejected by the real test API')
  assert.match(failedUi.error, /Честного знака|КИЗ|не похоже/i, 'validation failure is visible in the unified KIZ error field')
  assert.equal(failedUi.activeRow, orderA.id, 'validation failure retains the exact active row until the operator cancels')
  assert.deepEqual(failedDb.codes, beforeDb.codes, 'invalid KIZ did not change pool records')
  assert.deepEqual(failedDb.markings, beforeDb.markings, 'invalid KIZ did not create or replace a marking')
  assert.deepEqual(failedDb.stock, beforeDb.stock, 'invalid KIZ did not change stock')
  assert.equal(failedNative.accepted_png_count, initialReceiptCount, 'invalid KIZ created no native print job')

  // Exercise the actual Escape key handler on the active KIZ scan field.
  await cdp.eval(`document.querySelector('[data-testid="fbs-kiz-row-active"] [data-testid="fbs-kiz-row-input"]').focus()`)
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
  await wait(async () => {
    const current = await ui()
    const cancellations = apiEvents.filter(row => /scan-undo|scan-auto-print.*cancel|cancel-selection/.test(row.path))
    return !current.active && current.activeRow == null && !current.error
      && current.scanner.disabled === false && current.scanner.placeholder.includes('штрихкод товара')
      && cancellations.some(row => row.status >= 200 && row.status < 300)
  }, 30000)
  const afterEscape = await ui(); const afterEscapeDb = await get('/snapshot'); const afterEscapeNative = await post('/_proof/status')
  await saveJson('after-escape.json', { ui: afterEscape, db: afterEscapeDb, native: afterEscapeNative })
  await screenshot('after-escape')
  assert.equal(afterEscape.activeRow, null, 'Escape removes the active unified row on the same page')
  assert.equal(afterEscape.error, '', 'Escape clears the validation error on the same page')
  assert.equal(afterEscape.reset.exists, false, 'Escape removes the active-target reset action')
  assert.equal(afterEscape.scanner.disabled, false, 'Escape leaves product barcode scanner enabled')
  assert.match(afterEscape.scanner.placeholder, /штрихкод товара/, 'Escape returns the scanner to product barcode mode')
  assert.deepEqual(afterEscapeDb.codes, beforeDb.codes)
  assert.deepEqual(afterEscapeDb.markings, beforeDb.markings)
  assert.deepEqual(afterEscapeDb.stock, beforeDb.stock)
  assert.equal(afterEscapeNative.accepted_png_count, initialReceiptCount)

  await physicalScan(orderB.sticker_barcode, 'sticker-B')
  await wait(() => apiEvents.some(row => row.path.includes('/fbs-orders/kiz/lookup') && row.status === 200 && row.response?.order_id === orderB.id))
  await wait(async () => {
    const current = await ui()
    const bLookup = apiEvents.findLast(row => row.path.includes('/fbs-orders/kiz/lookup') && row.status === 200 && row.response?.order_id === orderB.id)
    return current.activeRow === orderB.id && bLookup?.response?.order_id === orderB.id
  }, 20000)
  const selectedB = await ui(); const afterBDb = await get('/snapshot'); const afterBNative = await post('/_proof/status')
  await saveJson('after-next-valid-B.json', { ui: selectedB, db: afterBDb, native: afterBNative })
  await screenshot('after-next-valid-B')
  assert.equal(selectedB.activeRow, orderB.id, 'next valid order sticker selects B in the active row marker')
  const bLookup = apiEvents.findLast(row => row.path.includes('/fbs-orders/kiz/lookup') && row.status === 200 && row.response?.order_id === orderB.id)
  assert.equal(bLookup.response.order_id, orderB.id, 'next valid barcode selected B, not stale A')
  assert.equal(selectedB.error, '', 'A validation error did not carry into B')
  assert.equal(selectedB.scanner.disabled, false)
  assert.deepEqual(afterBDb.codes, beforeDb.codes)
  assert.deepEqual(afterBDb.markings, beforeDb.markings)
  assert.deepEqual(afterBDb.stock, beforeDb.stock)
  assert.equal(afterBNative.accepted_png_count, initialReceiptCount, 'B selection after reset dispatches no unintended print job while waiting for its KIZ')

  const result = {
    product_sha: productSha, runtime_sha: productSha,
    case: 'M26 invalid KIZ → Escape reset → next valid order QR',
    synthetic_only: true,
    actions: [
      { input: orderA.sticker_barcode, selected_order_id: orderA.id, result: 'A active before invalid KIZ' },
      { input: invalidKiz, request_status: validation.status, result: 'real API rejection; pool, markings and stock unchanged; zero native print jobs' },
      { action: 'Escape key while KIZ scanner field focused', cancellation_requests: apiEvents.filter(row => /scan-undo|scan-auto-print.*cancel|cancel-selection/.test(row.path)).map(row => ({ path: row.path, status: row.status })), result: 'awaited cancellation; same-page target/error cleared; product scanner enabled' },
      { input: orderB.sticker_barcode, selected_order_id: bLookup.response.order_id, result: 'B selected without stale A error/target; no print job with flags off' },
    ],
    invariants: { pool_unchanged: true, markings_unchanged: true, stock_unchanged: true, handler_receipt_count_before: initialReceiptCount, handler_receipt_count_after: afterBNative.accepted_png_count, print_requests_in_case: printInputs.length },
    api_events: apiEvents,
  }
  await saveJson('result', result)
  await writeFile(`${out}/native/chrome.log`, chromeLog)
  console.log(JSON.stringify({ case: result.case, api_statuses: apiEvents.map(row => [row.path.split('?')[0], row.status]), selected_A: orderA.id, selected_B: bLookup.response.order_id, native_receipts: afterBNative.accepted_png_count, invariants: result.invariants }, null, 2))
} catch (error) {
  const debugUi = cdp ? await cdp.eval(`({body:document.body.innerText.slice(-2000),active:document.querySelector('[data-testid="fbs-kiz-scan-active"]')?.innerText||null,activeRow:document.querySelector('[data-testid="fbs-kiz-row-active"]')?.getAttribute('data-order-id')||null,alert:document.querySelector('[role="alert"]')?.textContent||'',error:document.querySelector('[data-testid="fbs-kiz-scan-error"]')?.textContent?.trim()||'',scan:document.querySelector('[data-packing-scan]')?.outerHTML||null,kiz:document.querySelector('[data-testid="fbs-kiz-scan-input"]')?.outerHTML||null,rowKiz:document.querySelector('[data-testid="fbs-kiz-row-active"] [data-testid="fbs-kiz-row-input"]')?.outerHTML||null})`).catch(String) : null
  await saveJson('failure', { error: String(error), debug_ui: debugUi, api_events: apiEvents, print_inputs: printInputs, chrome_log: chromeLog }).catch(() => undefined)
  console.error(error)
  process.exitCode = 1
} finally {
  try { cdp?.ws.close() } catch {}
  chrome.kill('SIGTERM')
  await Promise.race([new Promise(resolve => chrome.once('exit', resolve)), delay(5000)])
  await writeFile(`${out}/native/chrome.log`, chromeLog).catch(() => undefined)
  // Chrome's WebSocket can keep Node alive after its own child is stopped.
  setTimeout(() => process.exit(process.exitCode ?? 0), 250).unref()
}
