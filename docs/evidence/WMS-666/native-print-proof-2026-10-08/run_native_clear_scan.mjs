import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { setTimeout as delay } from 'node:timers/promises'

const root = new URL('.', import.meta.url).pathname
const runDir = process.env.WMS666_EVIDENCE_RUN || 'run-final/order-sticker-scan'
const out = `${root}${runDir}`
const chromeProfile = process.env.WMS666_CHROME_PROFILE || `${root}run-0c44ed45/chrome-profile`
const productSha = process.env.WMS666_PRODUCT_SHA
const runtimeSha = process.env.WMS666_RUNTIME_SHA
assert.match(productSha ?? '', /^[0-9a-f]{40}$/, 'WMS666_PRODUCT_SHA must pin the approved product commit')
assert.match(runtimeSha ?? '', /^[0-9a-f]{40}$/, 'WMS666_RUNTIME_SHA must pin the exact serving checkout')
const seed = JSON.parse(await readFile(`${root}${process.env.WMS666_SEED_FILE || `${runDir}/seed-public.json`}`, 'utf8'))
await mkdir(out, { recursive: true })
const chrome = spawn(process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--mute-audio', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--disable-background-networking', '--disable-extensions',
  `--user-data-dir=${chromeProfile}`, '--remote-debugging-port=16697', 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] })
let chromeLog = ''
chrome.stderr.on('data', chunk => { chromeLog += chunk.toString() })

class CDP {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl)
    this.id = 0
    this.pending = new Map()
    this.handlers = new Map()
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject })
    this.ws.onmessage = event => {
      const message = JSON.parse(event.data)
      if (!message.id) {
        for (const handler of this.handlers.get(message.method) ?? []) Promise.resolve(handler(message.params)).catch(error => this.eventErrors.push(String(error)))
        return
      }
      const pending = this.pending.get(message.id)
      if (!pending) return
      this.pending.delete(message.id)
      message.error ? pending.reject(Error(JSON.stringify(message.error))) : pending.resolve(message.result)
    }
    this.eventErrors = []
  }
  async send(method, params = {}) {
    await this.ready
    const id = ++this.id
    this.ws.send(JSON.stringify({ id, method, params }))
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }))
  }
  async evaluate(expression) {
    const response = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (response.exceptionDetails) throw Error(JSON.stringify(response.exceptionDetails))
    return response.result.value
  }
  on(method, handler) { this.handlers.set(method, [...(this.handlers.get(method) ?? []), handler]) }
}

const waitFor = async (test, timeout = 30000) => {
  const end = Date.now() + timeout
  while (Date.now() < end) { if (await test()) return; await delay(200) }
  throw Error('Timed out waiting for UI condition')
}
const fetchJson = async url => { const r = await fetch(url); if (!r.ok) throw Error(`${url}: ${r.status}`); return r.json() }
const postJson = async url => { const r = await fetch(url, { method: 'POST' }); if (!r.ok) throw Error(`${url}: ${r.status}`); return r.json() }
let cdp
try {
  await waitFor(async () => { try { return (await fetch('http://127.0.0.1:16697/json/version')).ok } catch { return false } })
  const tabs = await fetchJson('http://127.0.0.1:16697/json/list')
  const page = tabs.find(tab => tab.type === 'page')
  assert(page?.webSocketDebuggerUrl, 'one dedicated Chrome page is available')
  cdp = new CDP(page.webSocketDebuggerUrl)
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  const apiRequests = []
  cdp.on('Fetch.requestPaused', async ({ requestId, request }) => {
    const url = new URL(request.url)
    if (url.origin === 'http://127.0.0.1:16696' && url.pathname.startsWith('/api/')) {
      if (request.method === 'OPTIONS') {
        await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: '*' }] })
        return
      }
      const path = `/proxy${url.pathname.slice('/api'.length)}${url.search}`
      const upstream = await fetch(`http://127.0.0.1:16692${path}`, {
        method: request.method,
        headers: { 'Content-Type': request.headers['content-type'] || 'application/json' },
        ...(request.postData ? { body: request.postData } : {}),
      })
      const bytes = Buffer.from(await upstream.arrayBuffer())
      const contentType = upstream.headers.get('content-type') || 'application/json'
      let responseBody
      try { responseBody = JSON.parse(bytes.toString()) } catch { responseBody = null }
      apiRequests.push({
        method: request.method, path, status: upstream.status, contentType, responseBytes: bytes.length,
        ...(request.postData ? { request: JSON.parse(request.postData) } : {}),
        ...(responseBody === null ? {} : { response: responseBody }),
      })
      await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: upstream.status, responseHeaders: [
        { name: 'Content-Type', value: contentType }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' },
      ], body: bytes.toString('base64') })
      return
    }
    // The native print endpoint remains a real HTTP request to WMS Print Direct.
    await cdp.send('Fetch.continueRequest', { requestId })
  })
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.clear(); sessionStorage.clear();
    localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user', JSON.stringify({printQr:true,printChz:false,reprintChz:false,printChzCopies:2,reprintChzCopies:1}));
    localStorage.setItem('wms.print.labelSizeId','60x80');
    sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');
    sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing');
  ` })
  await cdp.send('Page.navigate', { url: `http://127.0.0.1:16696/app/ff/fbs?supply_id=${seed.supply_id}` })
  try {
    await waitFor(() => cdp.evaluate(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)') && document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input') && document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input'))`))
  } catch (error) {
    const debug = await cdp.evaluate(`({url:location.href,title:document.title,text:document.body.innerText.slice(-5000),html:document.body.innerHTML.slice(-5000)})`)
    await writeFile(`${out}/startup-debug.json`, JSON.stringify({ debug, chromeLog }, null, 2))
    throw error
  }
  const setFlag = async (testId, wanted) => cdp.evaluate(`(() => {const input=document.querySelector(${JSON.stringify(`[data-testid="${testId}"] input[type="checkbox"]`)});if(!input)return false;if(input.checked!==${Boolean(wanted)})input.click();return true})()`)
  assert(await setFlag('fbs-scan-print-qr-toggle', true))
  assert(await setFlag('fbs-scan-print-chz-toggle', false))
  await waitFor(() => cdp.evaluate(`document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input')?.checked===true && document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input')?.checked===false`))
  const initialUi = await cdp.evaluate(`({url:location.href,scanner:document.querySelector('[data-packing-scan]')?.outerHTML,qr:document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input')?.checked,chz:document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input')?.checked,copies:document.querySelector('[data-testid="fbs-scan-print-chz-copies-value"]')?.textContent,orders:[...document.querySelectorAll('[data-order-id]')].map(x=>x.getAttribute('data-order-id'))})`)
  await writeFile(`${out}/ui-before-scan.json`, JSON.stringify(initialUi, null, 2))
  await writeFile(`${out}/ui-before-scan.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  assert.equal(initialUi.qr, true)
  assert.equal(initialUi.chz, false)
  assert(initialUi.orders.includes(seed.order_ids[0]))
  const beforeNative = await postJson('http://127.0.0.1:17843/_proof/status')
  const nativeIdentityPath = process.env.WMS666_NATIVE_IDENTITY_FILE || `${runDir}/native/source-identity.json`
  const nativeIdentity = JSON.parse(await readFile(`${root}${nativeIdentityPath}`, 'utf8'))
  assert.equal(nativeIdentity.product_sha, productSha)
  assert.equal(nativeIdentity.runtime_checkout_sha, runtimeSha)
  assert.equal(nativeIdentity.product_tree_matches, true)
  const beforeDb = await fetchJson('http://127.0.0.1:16692/snapshot')
  const scanText = async (text) => {
    const scanner = await cdp.evaluate(`(() => {const e=document.querySelector('[data-packing-scan]');e.focus();return !!document.activeElement})()`)
    assert(scanner)
    await cdp.send('Input.insertText', { text })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  }
  const orderStickerBarcode = seed.sticker_codes?.[0]
  assert.equal(orderStickerBarcode, seed.synthetic_order_stickers?.[0]?.text, 'scanned synthetic order-sticker QR equals its source image payload')
  assert.equal(seed.order_sticker_barcodes?.[0], orderStickerBarcode, 'the synthetic order sticker scan value equals the DB sticker barcode')
  assert.equal(beforeDb.orders.find(row => row.id === seed.order_ids[0])?.sticker_code, orderStickerBarcode, 'the source QR payload equals the persisted FbsOrder.sticker_code')
  await scanText(orderStickerBarcode)
  await waitFor(() => apiRequests.some(row => row.path.includes('/operations/fbs-orders/kiz/lookup') && row.status === 200))
  const selection = apiRequests.find(row => row.path.endsWith('/scan-auto-print') && row.method === 'POST' && row.status === 200)
  assert(selection, 'order sticker created a real explicit scan intent before any print dispatch')
  assert.equal(selection.response?.order_id, seed.order_ids[0])
  try {
    await waitFor(() => cdp.evaluate(`Boolean(document.querySelector('[data-testid="fbs-scan-undo"]:not(:disabled)'))`))
  } catch (error) {
    const debug = await cdp.evaluate(`({bodyText:document.body.innerText.slice(-2200),active:document.querySelector('[data-testid="fbs-kiz-scan-active"]')?.outerHTML||null,scanner:document.querySelector('[data-packing-scan]')?.outerHTML,allTestIds:[...document.querySelectorAll('[data-testid]')].map(e=>e.getAttribute('data-testid')).filter(x=>x.includes('scan')||x.includes('kiz'))})`)
    await writeFile(`${out}/reset-not-visible.json`, JSON.stringify({ error: String(error), debug, apiRequests }, null, 2))
    await writeFile(`${out}/reset-not-visible.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
    throw error
  }
  const activeBeforeClear = await cdp.evaluate(`(() => {const row=document.querySelector('[data-testid="fbs-kiz-row-active"]');return {undo:document.querySelector('[data-testid="fbs-scan-undo"]')?.outerHTML,activeRow:{present:Boolean(row),text:row?.innerText||null,html:row?.outerHTML||null},placeholder:document.querySelector('[data-packing-scan]')?.getAttribute('placeholder'),bodyText:document.body.innerText.slice(-1200)}})()`)
  assert.equal(activeBeforeClear.activeRow.present, true, 'the selected order row is active before the operator clears the scan')
  await writeFile(`${out}/active-before-clear.json`, JSON.stringify(activeBeforeClear, null, 2))
  await writeFile(`${out}/active-before-clear.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  const clicked = await cdp.evaluate(`(() => {const button=document.querySelector('[data-testid="fbs-scan-undo"]');if(!button||button.disabled)return false;button.click();return true})()`)
  assert(clicked, 'the operator clicked the actual “Отменить последний скан” control to clear the active selection')
  await waitFor(() => cdp.evaluate(`document.querySelector('[data-testid="fbs-scan-undo"]')?.disabled===true`))
  await waitFor(() => apiRequests.some(row => row.path.endsWith('/scan-undo') && row.method === 'POST' && row.status === 200))
  const undoRequest = apiRequests.find(row => row.path.endsWith('/scan-undo') && row.method === 'POST' && row.status === 200)
  assert.equal(undoRequest.request?.release_selection, true, 'the API undo explicitly releases this scan selection')
  const clearedDb = await fetchJson('http://127.0.0.1:16692/snapshot')
  const clearedNative = await postJson('http://127.0.0.1:17843/_proof/status')
  assert.equal(clearedNative.accepted_png_count, beforeNative.accepted_png_count, 'cancel happened before any external printer submission')
  assert.equal(clearedDb.markings.length, beforeDb.markings.length, 'cancel did not create or bind a KIZ')
  assert.equal(clearedDb.stock, beforeDb.stock, 'cancel did not move stock')
  assert.equal(clearedDb.orders.find(row => row.id === seed.order_ids[0])?.pack_status, 'pending')
  const pageLoaded = new Promise(resolve => cdp.on('Page.loadEventFired', resolve))
  await cdp.send('Page.reload', { ignoreCache: true })
  await Promise.race([pageLoaded, delay(30000).then(() => { throw Error('Timed out waiting for browser load event after explicit reload') })])
  try {
    await waitFor(() => cdp.evaluate(`Boolean(document.body.innerText.includes(${JSON.stringify(`KIZ supply `)}) && document.querySelector('[data-packing-scan]:not(:disabled)') && document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input')?.checked===true && document.querySelector('[data-packing-scan]')?.getAttribute('placeholder')==='Сканируйте штрихкод товара' && document.querySelector('[data-testid="fbs-scan-undo"]')?.disabled===true)`))
  } catch (error) {
    const debug = await cdp.evaluate(`({readyState:document.readyState,bodyText:document.body.innerText.slice(-1800),scanner:document.querySelector('[data-packing-scan]')?.outerHTML,reset:document.querySelector('[data-testid="fbs-scan-undo"]')?.outerHTML})`)
    await writeFile(`${out}/reload-not-restored.json`, JSON.stringify({ error: String(error), debug, apiRequests }, null, 2))
    await writeFile(`${out}/reload-not-restored.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
    throw error
  }
  const afterReload = await cdp.evaluate(`(() => {const row=document.querySelector('[data-testid="fbs-kiz-row-active"]');return {url:location.href,undoVisible:Boolean(document.querySelector('[data-testid="fbs-scan-undo"]')),placeholder:document.querySelector('[data-packing-scan]')?.getAttribute('placeholder'),activeRow:{present:Boolean(row),text:row?.innerText||null,html:row?.outerHTML||null},bodyText:document.body.innerText.slice(-1000)}})()`)
  await writeFile(`${out}/after-reload.json`, JSON.stringify(afterReload, null, 2))
  await writeFile(`${out}/after-reload.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  const afterNative = await postJson('http://127.0.0.1:17843/_proof/status')
  const afterDb = await fetchJson('http://127.0.0.1:16692/snapshot')
  const afterUi = await cdp.evaluate(`({error:document.querySelector('[role="alert"]')?.textContent||'',scannerValue:document.querySelector('[data-packing-scan]')?.value,bodyText:document.body.innerText.slice(-1800)})`)
  await writeFile(`${out}/ui-after-scan.json`, JSON.stringify(afterUi, null, 2))
  await writeFile(`${out}/ui-after-scan.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  await writeFile(`${out}/db-before.json`, JSON.stringify(beforeDb, null, 2))
  await writeFile(`${out}/db-after.json`, JSON.stringify(afterDb, null, 2))
  await writeFile(`${out}/native-status.json`, JSON.stringify({ beforeNative, afterNative }, null, 2))
  await writeFile(`${out}/api-requests.json`, JSON.stringify(apiRequests, null, 2))
  await writeFile(`${out}/scan-inputs.json`, JSON.stringify({ order_sticker_barcode: orderStickerBarcode, source_png_qr_text: seed.synthetic_order_stickers?.[0]?.text, persisted_sticker_code: beforeDb.orders.find(row => row.id === seed.order_ids[0])?.sticker_code, order_id: seed.order_ids[0], scan_id: selection.response.scan_id, undo_endpoint: `/operations/fbs-supplies/${seed.supply_id}/scan-undo`, undo_request: undoRequest.request }, null, 2))
  await writeFile(`${out}/source-and-seed.json`, JSON.stringify({ product_sha: productSha, runtime_checkout_sha: runtimeSha, native_identity: nativeIdentity, seed: { supply_id: seed.supply_id, order_ids: seed.order_ids, barcode: seed.barcode, sticker_codes: seed.sticker_codes, order_sticker_barcodes: seed.order_sticker_barcodes, synthetic_order_stickers: seed.synthetic_order_stickers } }, null, 2))
  await writeFile(`${out}/cdp-event-errors.json`, JSON.stringify(cdp.eventErrors, null, 2))
  await writeFile(`${out}/chrome.log`, chromeLog)
  assert.equal(selection.request.print_qr, true)
  assert.equal(selection.request.print_chz, false, 'explicit order-sticker selection does not allocate a pool CIS')
  assert.equal(afterNative.accepted_png_count - beforeNative.accepted_png_count, 0, 'the selected intent was reset before native dispatch')
  assert.equal(afterDb.markings.length, beforeDb.markings.length)
  assert.equal(afterReload.undoVisible, true)
  assert.equal(afterReload.placeholder, 'Сканируйте штрихкод товара')
  assert.equal(afterReload.activeRow.present, false, 'the same active-order row selector is absent after reload returns to the idle product-barcode scanner')
  process.stdout.write(JSON.stringify({ initialUi, orderStickerBarcode, selection, activeBeforeClear, clearedDb, afterReload, beforeNative, afterNative, afterUi, output: out }, null, 2) + '\n')
} finally {
  cdp?.ws.close()
  chrome.kill()
}
