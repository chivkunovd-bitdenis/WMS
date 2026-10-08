import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { setTimeout as delay } from 'node:timers/promises'

const root = new URL('.', import.meta.url).pathname
const runDir = process.env.WMS666_EVIDENCE_RUN || 'run-0c44ed45'
const out = `${root}${runDir}/native`
const chromeProfile = process.env.WMS666_CHROME_PROFILE || `${root}run-0c44ed45/chrome-profile`
const productSha = process.env.WMS666_PRODUCT_SHA
const runtimeSha = process.env.WMS666_RUNTIME_SHA
assert.match(productSha ?? '', /^[0-9a-f]{40}$/, 'WMS666_PRODUCT_SHA must pin the approved product commit')
assert.match(runtimeSha ?? '', /^[0-9a-f]{40}$/, 'WMS666_RUNTIME_SHA must pin the exact serving checkout')
const seed = JSON.parse(await readFile(`${root}${runDir}/seed-public.json`, 'utf8'))
const scanBarcode = process.env.WMS666_SCAN_BARCODE || seed.barcode
const followKizScan = process.env.WMS666_FOLLOW_KIZ_SCAN === '1'
const preferences = JSON.parse(process.env.WMS666_PREFERENCES || JSON.stringify({ printQr: true, printChz: true, reprintChz: false, printChzCopies: 2, reprintChzCopies: 1 }))
const expectedJobs = (preferences.printQr ? 1 : 0) + (preferences.printChz ? preferences.printChzCopies : 0)
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
let apiRequests = []
try {
  await waitFor(async () => { try { return (await fetch('http://127.0.0.1:16697/json/version')).ok } catch { return false } })
  const tabs = await fetchJson('http://127.0.0.1:16697/json/list')
  const page = tabs.find(tab => tab.type === 'page')
  assert(page?.webSocketDebuggerUrl, 'one dedicated Chrome page is available')
  cdp = new CDP(page.webSocketDebuggerUrl)
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  apiRequests = []
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
      try { responseBody = JSON.parse(bytes.toString()) } catch { responseBody = undefined }
      apiRequests.push({
        method: request.method, path, status: upstream.status, contentType, responseBytes: bytes.length,
        ...(request.postData ? { request: JSON.parse(request.postData) } : {}),
        ...(responseBody === undefined ? {} : { response: responseBody }),
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
    localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user', ${JSON.stringify(JSON.stringify(preferences))});
    localStorage.setItem('wms.print.labelSizeId','60x80');
    sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');
    sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing');
  ` })
  await cdp.send('Page.navigate', { url: `http://127.0.0.1:16696/app/ff/fbs?supply_id=${seed.supply_id}` })
  try {
    await waitFor(() => cdp.evaluate(`Boolean(document.querySelector('[data-packing-scan][placeholder="Сканируйте штрихкод товара"]:not(:disabled)') && document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input') && document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input'))`))
  } catch (error) {
    const debug = await cdp.evaluate(`({url:location.href,title:document.title,text:document.body.innerText.slice(-5000),html:document.body.innerHTML.slice(-5000)})`)
    await writeFile(`${out}/startup-debug.json`, JSON.stringify({ debug, chromeLog }, null, 2))
    throw error
  }
  const setFlag = async (testId, wanted) => cdp.evaluate(`(() => {const input=document.querySelector(${JSON.stringify(`[data-testid="${testId}"] input[type="checkbox"]`)});if(!input)return false;if(input.checked!==${Boolean(wanted)})input.click();return true})()`)
  assert(await setFlag('fbs-scan-print-qr-toggle', preferences.printQr))
  assert(await setFlag('fbs-scan-print-chz-toggle', preferences.printChz))
  assert(await setFlag('fbs-kiz-auto-reprint-toggle', preferences.reprintChz))
  if (preferences.printChz) {
    await waitFor(() => cdp.evaluate(`Boolean(document.querySelector('[data-testid="fbs-scan-print-chz-copies-value"]'))`))
    const currentCopies = Number(await cdp.evaluate(`document.querySelector('[data-testid="fbs-scan-print-chz-copies-value"]')?.textContent`))
    const delta = preferences.printChzCopies - currentCopies
    const buttonId = delta > 0 ? 'fbs-scan-print-chz-copies-plus' : 'fbs-scan-print-chz-copies-minus'
    for (let i = 0; i < Math.abs(delta); i += 1) await cdp.evaluate(`document.querySelector('[data-testid="${buttonId}"]')?.click()`)
  }
  await waitFor(async () => {
    const ui = await cdp.evaluate(`({qr:document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input')?.checked,chz:document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input')?.checked,reprint:document.querySelector('[data-testid="fbs-kiz-auto-reprint-toggle"] input')?.checked,copies:document.querySelector('[data-testid="fbs-scan-print-chz-copies-value"]')?.textContent})`)
    return ui.qr === preferences.printQr && ui.chz === preferences.printChz && ui.reprint === preferences.reprintChz && (!preferences.printChz || Number(ui.copies) === preferences.printChzCopies)
  })
  const initialUi = await cdp.evaluate(`({url:location.href,scanner:document.querySelector('[data-packing-scan]')?.outerHTML,qr:document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input')?.checked,chz:document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input')?.checked,copies:document.querySelector('[data-testid="fbs-scan-print-chz-copies-value"]')?.textContent,orders:[...document.querySelectorAll('[data-order-id]')].map(x=>x.getAttribute('data-order-id'))})`)
  await writeFile(`${out}/ui-before-scan.json`, JSON.stringify(initialUi, null, 2))
  await writeFile(`${out}/ui-before-scan.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  assert.equal(initialUi.qr, preferences.printQr)
  assert.equal(initialUi.chz, preferences.printChz)
  if (preferences.printChz) assert.equal(initialUi.copies, String(preferences.printChzCopies))
  assert(initialUi.orders.includes(seed.order_ids[0]))
  const beforeNative = await postJson('http://127.0.0.1:17843/_proof/status')
  const nativeIdentity = JSON.parse(await readFile(`${root}${runDir}/native/source-identity.json`, 'utf8'))
  assert.equal(nativeIdentity.product_sha, productSha)
  assert.equal(nativeIdentity.runtime_checkout_sha, runtimeSha)
  assert.equal(nativeIdentity.product_tree_matches, true)
  const beforeDb = await fetchJson('http://127.0.0.1:16692/snapshot')
  let expectedCurrentCis = process.env.WMS666_EXPECT_CIS || null
  if (expectedCurrentCis && process.env.WMS666_ASSIGN_CURRENT !== '1') {
    assert(beforeDb.markings.some(row => row.order_id === seed.order_ids[0] && row.cis === expectedCurrentCis && row.status === 'accepted'), 'QR-only case starts with the exact accepted current CIS binding')
  }
  let manuallyBoundCis = null
  if (process.env.WMS666_ASSIGN_CURRENT === '1') {
    manuallyBoundCis = beforeDb.codes[0].cis
    expectedCurrentCis ||= manuallyBoundCis
    const focused = await cdp.evaluate(`(() => {const e=[...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].find(x=>x.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(seed.order_ids[0])});if(!e)return false;e.focus();return document.activeElement===e})()`)
    assert(focused, 'operator can bind the existing pool CIS to the exact order before a QR-only scan')
    await cdp.send('Input.insertText', { text: manuallyBoundCis })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await waitFor(async () => (await fetchJson('http://127.0.0.1:16692/snapshot')).markings.some(row => row.order_id === seed.order_ids[0] && row.cis === manuallyBoundCis))
    if (process.env.WMS666_SYNC_CURRENT === '1') {
      const check = await cdp.evaluate(`(() => {const e=document.querySelector('[data-testid="fbs-packing-check-wb"]');if(!e||e.disabled)return false;e.click();return true})()`)
      assert(check, 'operator can explicitly reconcile the newly bound KIZ with the synthetic WB fixture')
      await waitFor(() => apiRequests.some(row => row.path.includes('/markings/sync') && row.method === 'POST' && row.status === 200), 30000)
      await waitFor(async () => {
        const current = await fetchJson('http://127.0.0.1:16692/snapshot')
        return current.markings.some(row => row.order_id === seed.order_ids[0] && row.cis === manuallyBoundCis && row.status === 'accepted')
      }, 30000)
    }
  }
  if (expectedCurrentCis) {
    const assignedDb = await fetchJson('http://127.0.0.1:16692/snapshot')
    assert(assignedDb.markings.some(row => row.order_id === seed.order_ids[0] && row.cis === expectedCurrentCis && ['accepted', 'unknown'].includes(row.status)), 'operator UI has established the exact current CIS binding before scan')
  }
  if (process.env.WMS666_BIND_ONLY !== '1') {
    const scanner = await cdp.evaluate(`(() => {const e=document.querySelector('[data-packing-scan][placeholder="Сканируйте штрихкод товара"]');e?.focus();return !!e&&document.activeElement===e})()`)
    assert(scanner)
    await cdp.send('Input.insertText', { text: scanBarcode })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  }
  if (followKizScan && process.env.WMS666_BIND_ONLY !== '1') {
    await waitFor(() => cdp.evaluate(`Boolean(document.querySelector('[data-packing-scan][placeholder="Сканируйте Честный знак"]:not(:disabled)'))`), 15000)
    const kizInput = await cdp.evaluate(`(() => {const e=document.querySelector('[data-packing-scan][placeholder="Сканируйте Честный знак"]');e?.focus();return !!e&&document.activeElement===e})()`)
    assert(kizInput, 'pending selected order exposes the KIZ scanner')
    await cdp.send('Input.insertText', { text: expectedCurrentCis })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  }
  if (expectedJobs > 0) {
    try {
      await waitFor(async () => (await postJson('http://127.0.0.1:17843/_proof/status')).accepted_png_count >= beforeNative.accepted_png_count + expectedJobs, 45000)
    } catch (error) {
      const debug = await cdp.evaluate(`({url:location.href,bodyText:document.body.innerText.slice(-3500),scanInput:document.querySelector('[data-packing-scan][placeholder="Сканируйте штрихкод товара"]')?.outerHTML,alerts:[...document.querySelectorAll('[role="alert"]')].map(e=>e.textContent)})`)
      await writeFile(`${out}/scan-timeout-debug.json`, JSON.stringify({ error: String(error), debug, apiRequests, cdpEventErrors: cdp.eventErrors }, null, 2))
      throw error
    }
  } else {
    await waitFor(() => cdp.evaluate(`Boolean(document.querySelector('[role="alert"]')?.textContent)`), 15000)
    await delay(1000)
  }
  await delay(1200)
  const afterNative = await postJson('http://127.0.0.1:17843/_proof/status')
  const afterDb = await fetchJson('http://127.0.0.1:16692/snapshot')
  const scanClaim = apiRequests.find(row => row.path.endsWith('/scan-auto-print') && row.method === 'POST')
  if (process.env.WMS666_EXPECT_ORDER_ID) assert.equal(scanClaim?.response?.order_id, process.env.WMS666_EXPECT_ORDER_ID, 'server selected the exact expected order target')
  if (preferences.printQr && !preferences.printChz) {
    assert(scanClaim, 'QR-only scan made one real product scan claim')
    assert.deepEqual(scanClaim.response?.printed_codes ?? [], [], 'QR-only scan dispatches no CHZ code')
  }
  if (!preferences.printQr && preferences.printChz) {
    assert(scanClaim, 'CHZ-only scan made one real product scan claim')
    assert.equal(scanClaim.response?.qr_asset ?? null, null, 'CHZ-only scan has no order QR asset')
    assert.equal((scanClaim.response?.printed_codes ?? []).length, 1, 'CHZ-only scan prepares exactly one CIS, then copies are handled by the print job')
  }
  if (expectedCurrentCis) {
    assert(afterDb.markings.some(row => row.order_id === seed.order_ids[0] && row.cis === expectedCurrentCis && ['accepted', 'unknown'].includes(row.status)), 'QR-only scan preserves the same current binding')
  }
  const afterUi = await cdp.evaluate(`({error:document.querySelector('[role="alert"]')?.textContent||'',scannerValue:document.querySelector('[data-packing-scan]')?.value,bodyText:document.body.innerText.slice(-1800)})`)
  await writeFile(`${out}/ui-after-scan.json`, JSON.stringify(afterUi, null, 2))
  await writeFile(`${out}/ui-after-scan.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  await writeFile(`${out}/db-before.json`, JSON.stringify(beforeDb, null, 2))
  await writeFile(`${out}/db-after.json`, JSON.stringify(afterDb, null, 2))
  await writeFile(`${out}/native-status.json`, JSON.stringify({ beforeNative, afterNative }, null, 2))
  await writeFile(`${out}/api-requests.json`, JSON.stringify(apiRequests, null, 2))
  await writeFile(`${out}/cdp-event-errors.json`, JSON.stringify(cdp.eventErrors, null, 2))
  await writeFile(`${out}/source-and-seed.json`, JSON.stringify({ product_sha: productSha, runtime_checkout_sha: runtimeSha, native_identity: nativeIdentity, seed: { supply_id: seed.supply_id, order_ids: seed.order_ids, task_id: seed.task_id, barcode: seed.barcode, scan_barcode: scanBarcode }, }, null, 2))
  await writeFile(`${out}/chrome.log`, chromeLog)
  assert.equal(afterNative.accepted_png_count - beforeNative.accepted_png_count, expectedJobs, 'native submissions equal the enabled output blocks and their configured copy count')
  assert.equal(apiRequests.filter(row => row.path.endsWith('/scan-auto-print') && row.method === 'POST').length, expectedJobs === 0 ? 0 : 1, 'clear flags remain inert; enabled modes make one actual scan claim')
  if (manuallyBoundCis || preferences.printChz) assert(afterDb.markings.some(row => row.order_id === seed.order_ids[0] && row.cis === (manuallyBoundCis || apiRequests.find(row => row.path.endsWith('/scan-auto-print'))?.response?.printed_codes?.[0]?.cis_code)))
  process.stdout.write(JSON.stringify({ initialUi, beforeNative, afterNative, afterUi, output: out }, null, 2) + '\n')
} catch (error) {
  const debug = cdp ? await cdp.evaluate(`({url:location.href,bodyText:document.body.innerText.slice(-3000),alerts:[...document.querySelectorAll('[role="alert"]')].map(e=>e.textContent)})`).catch(() => null) : null
  const db = await fetchJson('http://127.0.0.1:16692/snapshot').catch(() => null)
  await writeFile(`${out}/runner-failure.json`, JSON.stringify({ error: String(error), debug, apiRequests, db, chromeLog }, null, 2))
  throw error
} finally {
  cdp?.ws.close()
  chrome.kill()
}
