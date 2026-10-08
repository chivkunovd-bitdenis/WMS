import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { setTimeout as delay } from 'node:timers/promises'

const root = new URL('.', import.meta.url).pathname
const runDir = process.env.WMS666_EVIDENCE_RUN
const productSha = process.env.WMS666_PRODUCT_SHA
const runtimeSha = process.env.WMS666_RUNTIME_SHA
assert(runDir, 'WMS666_EVIDENCE_RUN must name a fresh synthetic case directory')
assert.match(productSha ?? '', /^[0-9a-f]{40}$/)
assert.match(runtimeSha ?? '', /^[0-9a-f]{40}$/)
const out = `${root}${runDir}/manual-unlink`
const seed = JSON.parse(await readFile(`${root}${runDir}/seed-public.json`, 'utf8'))
await mkdir(out, { recursive: true })
const chromeProfile = process.env.WMS666_CHROME_PROFILE || `${root}run-final/chrome-profile`
const chrome = spawn(process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--mute-audio', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--disable-background-networking', '--disable-extensions', '--disk-cache-size=1',
  `--user-data-dir=${chromeProfile}`, '--remote-debugging-port=16697', 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] })
let cdp
class CDP {
  constructor(url) {
    this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = []
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject })
    this.ws.onmessage = event => {
      const message = JSON.parse(event.data)
      if (!message.id) { if (message.method === 'Fetch.requestPaused') for (const handler of this.handlers) Promise.resolve(handler(message.params)).catch(() => {}); return }
      const pending = this.pending.get(message.id)
      if (!pending) return
      this.pending.delete(message.id)
      message.error ? pending.reject(Error(JSON.stringify(message.error))) : pending.resolve(message.result)
    }
  }
  send(method, params = {}) {
    return this.ready.then(() => new Promise((resolve, reject) => {
      const id = ++this.id; this.pending.set(id, { resolve, reject }); this.ws.send(JSON.stringify({ id, method, params }))
    }))
  }
  on(handler) { this.handlers.push(handler) }
  async eval(expression) {
    const result = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails))
    return result.result.value
  }
}
const waitFor = async (predicate, timeout = 30000) => {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) { if (await predicate()) return; await delay(150) }
  throw Error(`Timed out after ${timeout}ms`)
}
const getJson = async url => { const response = await fetch(url); if (!response.ok) throw Error(`${url}: ${response.status}`); return response.json() }
const postPath = async (path, method, body) => {
  const response = await fetch(`http://127.0.0.1:16692/proxy${path}`, {
    method, headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}),
  })
  return { status: response.status, body: await response.text() }
}

const api = []
let unlinkResult = null
try {
  await waitFor(async () => { try { return (await fetch('http://127.0.0.1:16697/json/version')).ok } catch { return false } }, 20000)
  const tabs = await getJson('http://127.0.0.1:16697/json/list')
  cdp = new CDP(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl)
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  cdp.on(async ({ requestId, request }) => {
    const url = new URL(request.url)
    if (url.origin === 'http://127.0.0.1:16696' && url.pathname.startsWith('/api/')) {
      if (request.method === 'OPTIONS') {
        await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [
          { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: '*' },
        ] })
        return
      }
      const path = `/proxy${url.pathname.slice(4)}${url.search}`
      if (url.pathname.includes('/print-bindings/validate')) {
        const body = JSON.parse(request.postData || '{}')
        assert.equal(body.bindings?.length, 1, 'the delayed validation is for one exact prepared binding')
        const binding = body.bindings[0]
        assert.equal(binding.order_id, seed.order_ids[0])
        const tape = api.findLast(row => row.path.endsWith('/order-print-tape'))
        const exact = tape?.response?.orders?.[0]?.printed_codes?.find(code => code.marking_id === binding.marking_id)
        assert(exact, 'the validated marking ID came from the actual prepared tape response')
        assert.equal(binding.cis_code, exact.cis_code, 'validation carries the prepared full CIS exactly')
        unlinkResult = await postPath(`/operations/fbs-orders/${seed.order_ids[0]}/kiz`, 'DELETE')
        assert.equal(unlinkResult.status, 204, `the synthetic operator unlink completed: ${unlinkResult.body}`)
      }
      const response = await fetch(`http://127.0.0.1:16692${path}`, {
        method: request.method,
        headers: { 'Content-Type': request.headers['content-type'] || 'application/json' },
        ...(request.postData ? { body: request.postData } : {}),
      })
      const bytes = Buffer.from(await response.arrayBuffer())
      let responseBody
      try { responseBody = JSON.parse(bytes.toString()) } catch { responseBody = undefined }
      api.push({ method: request.method, path, status: response.status, ...(request.postData ? { request: JSON.parse(request.postData) } : {}), ...(responseBody === undefined ? {} : { response: responseBody }) })
      await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: response.status, responseHeaders: [
        { name: 'Content-Type', value: response.headers.get('Content-Type') || 'application/json' }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' },
      ], body: bytes.toString('base64') })
      return
    }
    await cdp.send('Fetch.continueRequest', { requestId })
  })
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.clear(); sessionStorage.clear();
    localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user', JSON.stringify({printQr:false,printChz:false,reprintChz:false,printChzCopies:2,reprintChzCopies:1}));
    localStorage.setItem('wms.print.labelSizeId','60x80');
    sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');
    sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing');
    window.top.__WMS_PRINT_CALLS__=window.top.__WMS_PRINT_CALLS__||0;
    window.print=function(){window.top.__WMS_PRINT_CALLS__++};
  ` })
  await cdp.send('Page.navigate', { url: `http://127.0.0.1:16696/app/ff/fbs?supply_id=${seed.supply_id}` })
  await waitFor(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)') && document.querySelectorAll('[data-order-id]').length===2)`))
  const beforeDb = await getJson('http://127.0.0.1:16692/snapshot')
  const beforeNative = await (await fetch('http://127.0.0.1:17843/_proof/status', { method: 'POST' })).json()
  const cis = beforeDb.codes.find(code => code.status === 'available')?.cis
  assert(cis, 'the synthetic current seller/product pool has an available full CIS')
  const input = await cdp.eval(`(() => {const e=[...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].find(x=>x.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(seed.order_ids[0])});if(!e)return false;e.focus();return document.activeElement===e})()`)
  assert(input, 'the selected order has its ordinary KIZ input')
  await cdp.send('Input.insertText', { text: cis })
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await waitFor(async () => (await getJson('http://127.0.0.1:16692/snapshot')).markings.some(row => row.order_id === seed.order_ids[0] && row.cis === cis))
  const boundDb = await getJson('http://127.0.0.1:16692/snapshot')
  const current = boundDb.markings.find(row => row.order_id === seed.order_ids[0] && row.cis === cis)
  assert(current, 'the exact pool CIS is current on the target order before the race')
  const uiBefore = await cdp.eval(`({order:document.querySelector('[data-order-id="${seed.order_ids[0]}"]')?.innerText,printCalls:window.__WMS_PRINT_CALLS__})`)
  await writeFile(`${out}/before.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  await waitFor(() => cdp.eval(`Boolean(document.querySelector('[data-testid="fbs-kiz-reprint-inline"]')?.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(seed.order_ids[0])})`))
  await cdp.eval(`document.querySelector('[data-testid="fbs-kiz-reprint-inline"]').click()`)
  await waitFor(() => cdp.eval(`Boolean(document.querySelector('[data-testid="marking-print-confirm"]'))`))
  await cdp.eval(`document.querySelector('[data-testid="marking-print-confirm"]').click()`)
  await waitFor(() => api.some(row => row.path.endsWith('/print-bindings/validate') && row.status === 409), 30000)
  const afterDb = await getJson('http://127.0.0.1:16692/snapshot')
  const nativeStatus = await (await fetch('http://127.0.0.1:17843/_proof/status', { method: 'POST' })).json()
  const ui = await cdp.eval(`({printCalls:window.__WMS_PRINT_CALLS__,alerts:[...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent),text:document.body.innerText.slice(-1600)})`)
  assert.equal(unlinkResult?.status, 204)
  assert.equal(api.findLast(row => row.path.endsWith('/print-bindings/validate'))?.status, 409)
  assert.equal(ui.printCalls, 0, 'unlink after tape preparation blocks the HTML print boundary')
  assert.equal(nativeStatus.accepted_png_count, beforeNative.accepted_png_count, 'manual HTML rejection makes no native QR/CIS job')
  const evidence = { product_sha: productSha, runtime_checkout_sha: runtimeSha, case: 'current operator binding → real manual tape response → synthetic unlink before final validator → 409 and no print dispatch', seed: { supply_id: seed.supply_id, order_ids: seed.order_ids }, initial_cis: cis, current_binding_before_prepare: current, tape: api.findLast(row => row.path.endsWith('/order-print-tape'))?.response, unlink: unlinkResult, api, beforeDb, boundDb, afterDb, beforeNative, nativeStatus, ui }
  await writeFile(`${out}/proof.json`, JSON.stringify(evidence, null, 2))
  await writeFile(`${out}/ui-before.json`, JSON.stringify(uiBefore, null, 2))
  await writeFile(`${out}/after.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  process.stdout.write(JSON.stringify({ api: api.map(row => ({ path: row.path, status: row.status })), cis, unlinkResult, nativeStatus, ui }, null, 2) + '\n')
} catch (error) {
  await writeFile(`${out}/failure.json`, JSON.stringify({ error: String(error), api, unlinkResult }, null, 2))
  throw error
} finally { cdp?.ws.close(); chrome.kill() }
