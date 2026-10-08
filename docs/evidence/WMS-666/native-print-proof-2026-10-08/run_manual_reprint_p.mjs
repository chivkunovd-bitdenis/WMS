import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { spawn } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'

const root = resolve('docs/evidence/WMS-666/native-print-proof-2026-10-08/run-5066f1dc/manual')
const seed = JSON.parse(await (await import('node:fs/promises')).readFile(`${root}/seed-public.json`, 'utf8'))
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--disable-background-networking', '--disable-extensions',
  `--user-data-dir=${root}/chrome-profile`, '--remote-debugging-port=16697', 'about:blank',
], { stdio: 'ignore' })
let cdp
class CDP {
  constructor(url) {
    this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = new Map()
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject })
    this.ws.onmessage = e => { const m = JSON.parse(e.data); if (!m.id) { for (const f of this.handlers.get(m.method) ?? []) void f(m.params); return }; const p = this.pending.get(m.id); if (p) { this.pending.delete(m.id); m.error ? p.reject(Error(JSON.stringify(m.error))) : p.resolve(m.result) } }
  }
  async send(method, params = {}) { await this.ready; const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject })) }
  on(method, f) { this.handlers.set(method, [...(this.handlers.get(method) ?? []), f]) }
  async eval(expression) { const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails)); return r.result.value }
}
const waitFor = async (fn, timeout = 30000) => { const end = Date.now() + timeout; while (Date.now() < end) { if (await fn()) return; await delay(150) }; throw Error(`wait timeout ${timeout}`) }
const api = []
try {
  await waitFor(async () => { try { return (await fetch('http://127.0.0.1:16697/json/version')).ok } catch { return false } })
  const pages = await (await fetch('http://127.0.0.1:16697/json/list')).json()
  cdp = new CDP(pages.find(x => x.type === 'page').webSocketDebuggerUrl)
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  cdp.on('Fetch.requestPaused', async ({ requestId, request }) => {
    const u = new URL(request.url)
    if (u.origin === 'http://127.0.0.1:16696' && u.pathname.startsWith('/api/')) {
      if (request.method === 'OPTIONS') return cdp.send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: '*' }] })
      const path = `/proxy${u.pathname.slice(4)}${u.search}`
      const res = await fetch(`http://127.0.0.1:16692${path}`, { method: request.method, headers: { 'Content-Type': request.headers['content-type'] || 'application/json' }, ...(request.postData ? { body: request.postData } : {}) })
      const bytes = Buffer.from(await res.arrayBuffer()); let body
      try { body = JSON.parse(bytes.toString()) } catch { body = undefined }
      api.push({ method: request.method, path, status: res.status, ...(request.postData ? { request: JSON.parse(request.postData) } : {}), ...(body === undefined ? {} : { response: body }) })
      await writeFile(`${root}/manual-reprint-api.json`, JSON.stringify(api, null, 2))
      return cdp.send('Fetch.fulfillRequest', { requestId, responseCode: res.status, responseHeaders: [{ name: 'Content-Type', value: res.headers.get('content-type') || 'application/json' }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }], body: bytes.toString('base64') })
    }
    return cdp.send('Fetch.continueRequest', { requestId })
  })
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.clear();sessionStorage.clear();
    localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',${JSON.stringify(JSON.stringify({ printQr: false, printChz: false, reprintChz: false, printChzCopies: 2, reprintChzCopies: 1 }))});
    localStorage.setItem('wms.print.labelSizeId','60x80');
    sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing');
    window.__WMS_CAPTURE_PRINT_HTML__=true;window.__WMS_LAST_PRINT_HTML__='';window.__WMS_PRINT_BOUNDARIES__=[];
    window.print=function(){window.top.__WMS_PRINT_BOUNDARIES__.push({title:document.title,html:document.documentElement.outerHTML})};
  ` })
  const before = await (await fetch('http://127.0.0.1:16692/snapshot')).json()
  const target = before.markings.find(m => m.order_id === seed.order_ids[0])
  assert(target && target.status === 'rejected', 'synthetic fixture has the same current KIZ marked rejected')
  const beforeNative = await (await fetch('http://127.0.0.1:17843/_proof/status', { method: 'POST' })).json()
  await writeFile(`${root}/manual-reprint-before.json`, JSON.stringify({ before, beforeNative, target }, null, 2))
  await cdp.send('Page.navigate', { url: `http://127.0.0.1:16696/app/ff/fbs?supply_id=${seed.supply_id}` })
  await waitFor(() => cdp.eval(`Boolean(document.querySelector('[data-testid="fbs-kiz-reprint-inline"]'))`))
  const uiBefore = await cdp.eval(`({text:document.body.innerText.slice(-2500),buttons:[...document.querySelectorAll('[data-testid="fbs-kiz-reprint-inline"]')].map(b=>({disabled:b.disabled,title:b.title,aria:b.getAttribute('aria-label'),html:b.outerHTML})),selected:document.querySelector('[data-testid="fbs-kiz-reprint-inline"]')?.closest('[data-order-id]')?.getAttribute('data-order-id')})`)
  await writeFile(`${root}/manual-reprint-ui-before.json`, JSON.stringify(uiBefore, null, 2))
  assert.equal(uiBefore.selected, target.order_id)
  await cdp.eval(`document.querySelector('[data-testid="fbs-kiz-reprint-inline"]').click()`)
  await waitFor(() => cdp.eval(`Boolean(document.querySelector('[data-testid="marking-print-confirm"]'))`))
  const dialog = await cdp.eval(`({text:document.body.innerText.slice(-3000),tape:document.querySelector('[data-testid="marking-print-tape"]')?.innerText})`)
  await writeFile(`${root}/manual-reprint-dialog.json`, JSON.stringify(dialog, null, 2))
  await writeFile(`${root}/manual-reprint-dialog.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  await cdp.eval(`document.querySelector('[data-testid="marking-print-confirm"]').click()`)
  await waitFor(() => cdp.eval(`Boolean(window.__WMS_LAST_PRINT_HTML__)`))
  const html = await cdp.eval(`window.__WMS_LAST_PRINT_HTML__`)
  await writeFile(`${root}/manual-print.html`, html)
  await waitFor(() => cdp.eval(`document.querySelector('[role="dialog"]')===null || !document.body.innerText.includes('Печать')`), 5000).catch(() => {})
  const after = await (await fetch('http://127.0.0.1:16692/snapshot')).json()
  const afterNative = await (await fetch('http://127.0.0.1:17843/_proof/status', { method: 'POST' })).json()
  const uiAfter = await cdp.eval(`({boundaries:window.__WMS_PRINT_BOUNDARIES__?.length||0,body:document.body.innerText.slice(-1800),alerts:[...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent)})`)
  const proof = { productP: '5066f1dc3c362935fe31292671ca6fad2a4205bf', runtimeSHA: 'a629bcc14740b7fd9db80d0c609a0a8f94b29e7f', route: 'React inline exact reprint → actual FBS order-print-tape API → actual final print-bindings validation → product HTML iframe print boundary; PDF rendering follows from saved HTML', fixture: 'Synthetic DB-only provider rejection; no marketplace request or acknowledgement', target, beforeNative, afterNative, beforeMarkings: before.markings, afterMarkings: after.markings, beforeCodes: before.codes.map(c => ({ id: c.id, cis: c.cis, status: c.status })), afterCodes: after.codes.map(c => ({ id: c.id, cis: c.cis, status: c.status })), api, htmlBytes: Buffer.byteLength(html), htmlHasTargetCis: html.includes(target.cis), uiBefore, dialog, uiAfter }
  assert(api.some(x => x.path.includes('/order-print-tape') && x.status === 200), 'real order tape was fetched')
  assert(api.some(x => x.path.includes('/print-bindings/validate') && x.status === 204), 'late validation accepted explicit current rejected reprint')
  assert(html.includes(target.cis), 'captured print HTML contains the exact already-bound CIS')
  assert(!api.some(x => x.path.includes('assign') || x.path.includes('generate')), 'no allocate/assign route in reprint path')
  assert.equal(after.markings.find(m => m.id === target.id)?.cis, target.cis)
  assert.equal(after.codes.map(c => c.id).join(','), before.codes.map(c => c.id).join(','), 'no new marking-code rows were allocated')
  await writeFile(`${root}/manual-reprint-after.json`, JSON.stringify({ proof, after, afterNative, uiAfter }, null, 2))
  await writeFile(`${root}/manual-reprint-after.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
  console.log(JSON.stringify({ api: api.map(x => [x.method, x.path, x.status]), target, htmlBytes: Buffer.byteLength(html), htmlHasTargetCis: html.includes(target.cis), afterMarking: after.markings.find(m => m.id === target.id), beforeReceipts: beforeNative.receipts?.length, afterReceipts: afterNative.receipts?.length }, null, 2))
} catch (error) {
  await writeFile(`${root}/manual-reprint-failure.json`, JSON.stringify({ error: String(error), api }, null, 2))
  throw error
} finally { cdp?.ws.close(); chrome.kill() }
