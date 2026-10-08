import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { spawn } from 'node:child_process'
import { setTimeout as sleep } from 'node:timers/promises'

const base = resolve('docs/evidence/WMS-666/native-print-proof-2026-10-08/run-5066f1dc/manual')
const seed = JSON.parse(await (await import('node:fs/promises')).readFile(`${base}/seed-public.json`, 'utf8'))
await mkdir(`${base}/chrome-profile`, { recursive: true })
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--disable-background-networking', '--disk-cache-size=1',
  `--user-data-dir=${base}/chrome-profile`, '--remote-debugging-port=16697', 'about:blank',
], { stdio: 'ignore' })
let cdp
class Cdp {
  constructor(url) {
    this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.listeners = new Map()
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject })
    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data)
      if (!message.id) { for (const listener of this.listeners.get(message.method) ?? []) void listener(message.params); return }
      const pending = this.pending.get(message.id); if (!pending) return
      this.pending.delete(message.id); message.error ? pending.reject(Error(JSON.stringify(message.error))) : pending.resolve(message.result)
    }
  }
  send(method, params = {}) { return this.ready.then(() => new Promise((resolve, reject) => { const id = ++this.id; this.pending.set(id, { resolve, reject }); this.ws.send(JSON.stringify({ id, method, params })) })) }
  on(method, fn) { this.listeners.set(method, [...(this.listeners.get(method) ?? []), fn]) }
  eval(expression) { return this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }).then(result => { if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails)); return result.result.value }) }
}
const wait = async (check, ms = 30000) => { const until = Date.now() + ms; while (Date.now() < until) { if (await check()) return; await sleep(100) } throw Error(`wait timed out ${ms}ms`) }
const api = []
try {
  await wait(async () => { try { return (await fetch('http://127.0.0.1:16697/json/version')).ok } catch { return false } })
  const tabs = await (await fetch('http://127.0.0.1:16697/json/list')).json()
  cdp = new Cdp(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl)
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  cdp.on('Fetch.requestPaused', async ({ requestId, request }) => {
    const url = new URL(request.url)
    if (url.origin === 'http://127.0.0.1:16696' && url.pathname.startsWith('/api/')) {
      if (request.method === 'OPTIONS') {
        await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [
          { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: '*' },
        ] }); return
      }
      const path = `/proxy${url.pathname.slice(4)}${url.search}`
      const upstream = await fetch(`http://127.0.0.1:16692${path}`, { method: request.method, headers: { 'Content-Type': request.headers['content-type'] || 'application/json' }, ...(request.postData ? { body: request.postData } : {}) })
      const bytes = Buffer.from(await upstream.arrayBuffer()); let response
      try { response = JSON.parse(bytes.toString()) } catch { response = undefined }
      const event = { method: request.method, path, status: upstream.status, ...(request.postData ? { request: JSON.parse(request.postData) } : {}), ...(response === undefined ? {} : { response }) }
      api.push(event); await writeFile(`${base}/manual-assign-api.json`, JSON.stringify(api, null, 2))
      await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: upstream.status, responseHeaders: [
        { name: 'Content-Type', value: upstream.headers.get('content-type') || 'application/json' }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' },
      ], body: bytes.toString('base64') }); return
    }
    await cdp.send('Fetch.continueRequest', { requestId })
  })
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.clear();sessionStorage.clear();
    localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',${JSON.stringify(JSON.stringify({ printQr: false, printChz: false, reprintChz: false, printChzCopies: 2, reprintChzCopies: 1 }))});
    localStorage.setItem('wms.print.labelSizeId','60x80');
    sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');
    sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing');
    window.__WMS_CAPTURE_PRINT_HTML__=true;window.__WMS_LAST_PRINT_HTML__='';window.__WMS_PRINT_BOUNDARIES__=[];
    window.print=function(){window.top.__WMS_PRINT_BOUNDARIES__.push({frame:this===window?location.href:'unknown',title:document.title,html:document.documentElement.outerHTML})};
  ` })
  await cdp.send('Page.navigate', { url: `http://127.0.0.1:16696/app/ff/fbs?supply_id=${seed.supply_id}` })
  await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)')&&document.querySelectorAll('[data-order-id]').length===2&&document.querySelectorAll('[data-testid="fbs-kiz-row-input"]').length===2)`))
  const before = await (await fetch('http://127.0.0.1:16692/snapshot')).json()
  assert.equal(before.markings.length, 0)
  assert.equal(before.codes.length, 4)
  const bindResults = []
  for (const [index, orderId] of seed.order_ids.entries()) {
    const cis = before.codes[index].cis
    const found = await cdp.eval(`(() => {const x=[...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].find(e=>e.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(orderId)});if(!x)return null;x.focus();return true})()`)
    assert.equal(found, true, `operator row exists for order ${orderId}`)
    await cdp.send('Input.insertText', { text: cis })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    await wait(async () => (await fetch('http://127.0.0.1:16692/snapshot').then(r => r.json())).markings.some(m => m.order_id === orderId && m.cis === cis))
    bindResults.push({ order_id: orderId, cis })
  }
  const after = await (await fetch('http://127.0.0.1:16692/snapshot')).json()
  assert.equal(after.markings.length, 2)
  assert.deepEqual(new Set(after.markings.map(x => x.order_id)), new Set(seed.order_ids))
  const ui = await cdp.eval(`({rows:[...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].map(e=>({order:e.closest('[data-order-id]')?.getAttribute('data-order-id'),value:e.value,tail:e.closest('[data-order-id]')?.getAttribute('data-kiz-tail')})),reprintButtons:document.querySelectorAll('[data-testid="fbs-kiz-reprint-inline"]').length,alerts:[...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent)})`)
  await writeFile(`${base}/manual-assignment.json`, JSON.stringify({ productP: '5066f1dc3c362935fe31292671ca6fad2a4205bf', seed, before, bindResults, after, ui, api }, null, 2))
  await writeFile(`${base}/manual-assignment.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  console.log(JSON.stringify({ bindResults, afterMarkings: after.markings, reprintButtons: ui.reprintButtons, alerts: ui.alerts, apiCalls: api.map(x => [x.method,x.path,x.status]) }, null, 2))
} catch (error) {
  await writeFile(`${base}/manual-assignment-failure.json`, JSON.stringify({ error: String(error), api }, null, 2))
  throw error
} finally { cdp?.ws.close(); chrome.kill() }
