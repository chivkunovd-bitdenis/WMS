import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'

const base = new URL('.', import.meta.url).pathname
const run = process.env.WMS666_EVIDENCE_RUN || 'run-b6d23148/qr-only-continuity'
const out = `${base}${run}`
const backend = process.env.WMS666_BACKEND || 'http://127.0.0.1:16709'
const origin = process.env.WMS666_ORIGIN || 'http://127.0.0.1:16706'
const handler = process.env.WMS666_PRINT_ORIGIN || 'http://127.0.0.1:17843'
const cdpPort = Number(process.env.WMS666_CDP_PORT || 16707)
const productSha = process.env.WMS666_PRODUCT_SHA
const runtimeSha = process.env.WMS666_RUNTIME_SHA
assert.equal(productSha, 'b6d23148f1571d08d13d83c6179c385e2f6a1efc')
assert.equal(runtimeSha, productSha)
const seed = JSON.parse(await readFile(`${out}/seed-public.json`, 'utf8'))
await mkdir(`${out}/native/chrome-profile`, { recursive: true })
const chrome = spawn(process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--mute-audio', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--disable-background-networking', '--disable-extensions', '--disable-cache',
  '--disable-crash-reporter', '--disable-breakpad', '--disk-cache-size=1', '--media-cache-size=1',
  `--user-data-dir=${out}/native/chrome-profile`, `--remote-debugging-port=${cdpPort}`, 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] })
let chromeLog = ''
chrome.stderr.on('data', chunk => { chromeLog += chunk.toString() })

class CDP {
  constructor(url) {
    this.ws = new WebSocket(url)
    this.id = 0
    this.pending = new Map()
    this.handlers = new Map()
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject })
    this.ws.onmessage = event => {
      const message = JSON.parse(event.data)
      if (!message.id) {
        for (const callback of this.handlers.get(message.method) ?? []) Promise.resolve(callback(message.params)).catch(error => this.errors.push(String(error)))
        return
      }
      const pending = this.pending.get(message.id)
      if (!pending) return
      this.pending.delete(message.id)
      message.error ? pending.reject(Error(JSON.stringify(message.error))) : pending.resolve(message.result)
    }
    this.errors = []
  }
  async send(method, params = {}) {
    await this.ready
    const id = ++this.id
    this.ws.send(JSON.stringify({ id, method, params }))
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }))
  }
  on(method, callback) { this.handlers.set(method, [...(this.handlers.get(method) ?? []), callback]) }
  async eval(expression) {
    const value = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (value.exceptionDetails) throw Error(JSON.stringify(value.exceptionDetails))
    return value.result.value
  }
}
const wait = async (predicate, timeout = 30000) => {
  const until = Date.now() + timeout
  while (Date.now() < until) { if (await predicate()) return; await delay(100) }
  throw Error('Timed out waiting for UI/API state')
}
const readJson = async url => { const response = await fetch(url); if (!response.ok) throw Error(`${url} ${response.status}`); return response.json() }
const postJson = async url => { const response = await fetch(url, { method: 'POST' }); if (!response.ok) throw Error(`${url} ${response.status}`); return response.json() }
const apiRows = []
const printEvents = []
let assetCaptureCount = 0
let cdp
try {
  const idleBefore = await readJson(`${backend}/idle`)
  assert.equal(idleBefore.active, 0, 'no concurrent API mutations before the run')
  await wait(async () => { try { return (await fetch(`http://127.0.0.1:${cdpPort}/json/version`)).ok } catch { return false } }, 25000)
  const tabs = await readJson(`http://127.0.0.1:${cdpPort}/json/list`)
  cdp = new CDP(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl)
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
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
      const contentType = upstream.headers.get('Content-Type') || 'application/json'
      let body
      try { body = contentType.includes('json') ? JSON.parse(bytes.toString()) : null } catch { body = null }
      const row = { at: new Date().toISOString(), method: request.method, path, status: upstream.status, ...(request.postData ? { request: JSON.parse(request.postData) } : {}), ...(body === null ? {} : { response: body }) }
      if (contentType.includes('image/png') && upstream.status === 200) {
        const file = `provider-asset-${++assetCaptureCount}.png`
        await writeFile(`${out}/native/${file}`, bytes)
        row.asset = { file, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') }
      }
      apiRows.push(row)
      await writeFile(`${out}/native/api-requests.json`, `${JSON.stringify(apiRows, null, 2)}\n`)
      await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: upstream.status, responseHeaders: [
        { name: 'Content-Type', value: contentType },
        { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' },
      ], body: bytes.toString('base64') })
      return
    }
    if (url.pathname === '/print' && request.method === 'POST' && request.postData) {
      const body = JSON.parse(request.postData)
      const match = /^data:image\/png;base64,(.*)$/.exec(body.imageDataUrl || '')
      const png = match ? Buffer.from(match[1], 'base64') : Buffer.alloc(0)
      printEvents.push({ at: new Date().toISOString(), key: body.idempotencyKey, widthMm: body.widthMm, pngBytes: png.length, pngSha256: createHash('sha256').update(png).digest('hex') })
      await writeFile(`${out}/native/http-events.json`, `${JSON.stringify(printEvents, null, 2)}\n`)
    }
    // Keep the native route live. The actual WMS Print Direct Handler owns validation and receipts.
    await cdp.send('Fetch.continueRequest', { requestId })
  })
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.clear();sessionStorage.clear();
    localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',${JSON.stringify(JSON.stringify({ printQr: true, printChz: false, reprintChz: false, printChzCopies: 2, reprintChzCopies: 1 }))});
    localStorage.setItem('wms.print.labelSizeId','60x80');
    sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');
    sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing');
  ` })
  await cdp.send('Page.navigate', { url: `${origin}/app/ff/fbs?supply_id=${seed.supply_id}` })
  await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)') && document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input') && document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input'))`))
  const beforeDb = await readJson(`${backend}/snapshot`)
  const orderA = beforeDb.orders.find(row => row.id === seed.order_ids[0])
  const orderB = beforeDb.orders.find(row => row.id === seed.order_ids[1])
  assert(orderA?.sticker_barcode, 'A has its actual persisted sticker_barcode')
  assert.equal(orderA.sticker_barcode, seed.order_sticker_barcodes[0])
  const actualStickerA = orderA.sticker_barcode
  const availableCode = beforeDb.codes.find(row => row.status === 'available')
  assert(availableCode, 'seed has an actual pool CIS')
  const prefs = await cdp.eval(`({qr:document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input').checked,chz:document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input').checked,reprint:document.querySelector('[data-testid="fbs-scan-reprint-chz-toggle"] input')?.checked??false})`)
  assert.deepEqual(prefs, { qr: true, chz: false, reprint: false })
  const nativeBefore = await postJson(`${handler}/_proof/status`)
  assert.equal(nativeBefore.accepted_png_count, 0)
  await writeFile(`${out}/native/source-and-seed.json`, JSON.stringify({ product_sha: productSha, runtime_checkout_sha: runtimeSha, seed, target_A: { order_id: orderA.id, sticker_barcode: actualStickerA, sticker_code: orderA.sticker_code }, target_B: { order_id: orderB.id, sticker_barcode: orderB.sticker_barcode, product_barcode: orderB.product?.barcode ?? seed.barcode }, synthetic_QR_source: seed.synthetic_order_stickers?.[0] ?? null, actual_source_identity: JSON.parse(await readFile(`${out}/native/source-identity.json`, 'utf8')) }, null, 2) + '\n')
  await writeFile(`${out}/native/db-before.json`, JSON.stringify(beforeDb, null, 2) + '\n')
  const screenshot = async name => writeFile(`${out}/native/${name}.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  const ui = async () => cdp.eval(`({url:location.href,alert:document.querySelector('[role="alert"]')?.textContent||'',scannerValue:document.querySelector('[data-packing-scan]')?.value||'',scannerDisabled:document.querySelector('[data-packing-scan]')?.disabled??null,activeRow:document.querySelector('[data-testid="fbs-kiz-row-active"]')?.getAttribute('data-order-id')||null,body:document.body.innerText.slice(-1600)})`)
  const scan = async (value, label) => {
    await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)'))`))
    const at = new Date().toISOString()
    await cdp.eval(`document.querySelector('[data-packing-scan]').focus()`)
    await cdp.send('Input.insertText', { text: value })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    const entry = { label, value, at }
    const path = `${out}/native/physical-inputs.json`
    let inputs = []
    try { inputs = JSON.parse(await readFile(path, 'utf8')) } catch {}
    inputs.push(entry)
    await writeFile(path, JSON.stringify(inputs, null, 2) + '\n')
    return entry
  }
  await screenshot('before-inputs')
  const firstInput = await scan(actualStickerA, 'physical-output-QR-A')
  await wait(() => apiRows.some(row => row.method === 'POST' && row.path.endsWith('/scan-auto-print') && row.request?.barcode === actualStickerA))
  const aClaim = apiRows.filter(row => row.method === 'POST' && row.path.endsWith('/scan-auto-print') && row.response?.order_id === orderA.id)
  await wait(async () => (await postJson(`${handler}/_proof/status`)).accepted_png_count >= 1 || await cdp.eval(`Boolean(document.querySelector('[data-testid="fbs-kiz-row-input"]') || document.querySelector('[data-packing-scan]')?.value)`))
  await delay(300)
  const afterInputA = await ui()
  await screenshot('after-qr-input-A')
  const aKizInput = await cdp.eval(`(() => [...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].find(e=>e.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(orderA.id)})?.outerHTML||null)()`)
  if (aKizInput && aClaim.at(-1)?.response?.binding_target?.current_kiz == null) {
    const input = await cdp.eval(`(() => {const e=[...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].find(x=>x.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(orderA.id)}); if(!e)return false;e.focus();return document.activeElement===e})()`)
    assert(input, 'A requires and exposes an operator KIZ input')
    await cdp.send('Input.insertText', { text: availableCode.cis })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await writeFile(`${out}/native/operator-kiz-input.json`, JSON.stringify({ order_id: orderA.id, cis: availableCode.cis, code_id: availableCode.id, input_kind: 'actual row KIZ field', at: new Date().toISOString() }, null, 2) + '\n')
  }
  await wait(async () => (await postJson(`${handler}/_proof/status`)).accepted_png_count >= 1, 45000)
  await wait(async () => (await readJson(`${backend}/idle`)).active === 0, 45000)
  const afterA = await readJson(`${backend}/snapshot`)
  const aUiAfter = await ui()
  await writeFile(`${out}/native/after-A.json`, JSON.stringify({ firstInput, orderScan: aClaim.at(-1) ?? null, ui: aUiAfter, db: afterA, native: await postJson(`${handler}/_proof/status`) }, null, 2) + '\n')
  await screenshot('after-A-idle')

  // Retry the printed sticker's real QR value only after A has gone idle. A completed QR intent must not dispatch a duplicate.
  const receiptsBeforeRescan = await readFile(`${out}/native/sink-receipts.jsonl`, 'utf8').then(s => s.trim() ? s.trim().split('\n').map(JSON.parse) : [])
  const rescanInput = await scan(actualStickerA, 'physical-rescan-output-QR-A-after-idle')
  await delay(1800)
  const afterRescanUi = await ui()
  const afterRescanDb = await readJson(`${backend}/snapshot`)
  const afterRescanNative = await postJson(`${handler}/_proof/status`)
  const receiptsAfterRescan = await readFile(`${out}/native/sink-receipts.jsonl`, 'utf8').then(s => s.trim() ? s.trim().split('\n').map(JSON.parse) : [])
  await writeFile(`${out}/native/after-A-rescan.json`, JSON.stringify({ input: rescanInput, ui: afterRescanUi, db: afterRescanDb, native: afterRescanNative, receipts_before: receiptsBeforeRescan, receipts_after: receiptsAfterRescan }, null, 2) + '\n')
  await screenshot('after-A-rescan')

  const bScanInput = await scan(seed.barcode, 'physical-product-barcode-B')
  await wait(() => apiRows.some(row => row.method === 'POST' && row.path.endsWith('/scan-auto-print') && row.request?.barcode === seed.barcode && row.response?.order_id === orderB.id), 45000)
  const bSelection = apiRows.filter(row => row.method === 'POST' && row.path.endsWith('/scan-auto-print') && row.request?.barcode === seed.barcode)
  await wait(() => cdp.eval(`Boolean([...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].find(e=>e.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(orderB.id)}))`), 15000)
  const afterBProductUi = await ui()
  const afterBProductDb = await readJson(`${backend}/snapshot`)
  const bCode = afterBProductDb.codes.find(row => row.status === 'available')
  assert(bCode, 'B receives a real current pool CIS after the A intent completes')
  const bInputFocused = await cdp.eval(`(() => {const e=[...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].find(x=>x.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(orderB.id)});if(!e)return false;e.focus();return document.activeElement===e})()`)
  assert(bInputFocused, 'B KIZ is entered through the real operator field')
  await cdp.send('Input.insertText', { text: bCode.cis })
  const bCisInput = { value: bCode.cis, code_id: bCode.id, at: new Date().toISOString() }
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await writeFile(`${out}/native/B-product-and-kiz.json`, JSON.stringify({ product_input: bScanInput, product_scan_candidates: bSelection, ui_before_kiz: afterBProductUi, db_before_kiz: afterBProductDb, operator_kiz: bCisInput }, null, 2) + '\n')
  await wait(async () => (await postJson(`${handler}/_proof/status`)).accepted_png_count >= 2, 45000)
  await wait(async () => (await readJson(`${backend}/idle`)).active === 0, 45000)
  await delay(500)
  const afterFinal = await readJson(`${backend}/snapshot`)
  const finalUi = await ui()
  const finalNative = await postJson(`${handler}/_proof/status`)
  const receipts = await readFile(`${out}/native/sink-receipts.jsonl`, 'utf8').then(s => s.trim() ? s.trim().split('\n').map(JSON.parse) : [])
  await writeFile(`${out}/native/final.json`, JSON.stringify({ finalUi, finalNative, db: afterFinal, receipts, apiRows, printEvents, cdpErrors: cdp.errors, chromeLog }, null, 2) + '\n')
  await screenshot('final')
  process.stdout.write(JSON.stringify({ seed: { supply_id: seed.supply_id, orders: seed.order_ids }, A: { scan: aClaim.at(-1)?.response ?? null, rescanReceiptsBefore: receiptsBeforeRescan.length, rescanReceiptsAfter: receiptsAfterRescan.length }, B: { scan: bSelection.map(row => row.response), cis: bCode.cis }, receipts: receipts.length, ui: finalUi, dbOrders: afterFinal.orders.filter(row => seed.order_ids.includes(row.id)).map(row => ({ id: row.id, status: row.status })), idle: await readJson(`${backend}/idle`) }, null, 2) + '\n')
} catch (error) {
  const failure = { message: String(error), stack: error?.stack, api_event_count: apiRows.length, print_event_count: printEvents.length, last_api_event: apiRows.at(-1) ?? null, ui: cdp ? await cdp.eval(`({url:location.href,text:document.body.innerText.slice(-1000)})`).catch(String) : null, chromeLog }
  process.stderr.write(`${JSON.stringify(failure, null, 2)}\n`)
  await mkdir(`${out}/native`, { recursive: true })
  await writeFile(`${out}/native/runner-failure.json`, JSON.stringify(failure, null, 2) + '\n').catch(() => undefined)
  throw error
} finally {
  cdp?.ws.close()
  chrome.kill()
}
