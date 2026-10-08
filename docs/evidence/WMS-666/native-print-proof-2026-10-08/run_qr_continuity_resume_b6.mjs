import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'

const here = new URL('.', import.meta.url).pathname
const run = process.env.WMS666_EVIDENCE_RUN
assert(run, 'set WMS666_EVIDENCE_RUN to an existing seeded evidence folder')
const out = `${here}${run}`
const backend = process.env.WMS666_BACKEND || 'http://127.0.0.1:16692'
const origin = process.env.WMS666_ORIGIN || 'http://127.0.0.1:16696'
const handler = process.env.WMS666_PRINT_ORIGIN || 'http://127.0.0.1:17843'
const cdpPort = Number(process.env.WMS666_CDP_PORT || 16697)
assert.equal(process.env.WMS666_PRODUCT_SHA, 'b6d23148f1571d08d13d83c6179c385e2f6a1efc')
assert.equal(process.env.WMS666_RUNTIME_SHA, process.env.WMS666_PRODUCT_SHA)
const seed = JSON.parse(await readFile(`${out}/seed-public.json`, 'utf8'))
const nativeDir = `${out}/native/continuation`
await mkdir(nativeDir, { recursive: true })
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
  async send(method, params = {}) { await this.ready; const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject })) }
  on(method, fn) { this.listeners.set(method, [...(this.listeners.get(method) || []), fn]) }
  async eval(expression) { const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails)); return r.result.value }
}
const get = async path => { const r = await fetch(`${backend}${path}`); if (!r.ok) throw Error(`${path}: ${r.status}`); return r.json() }
const post = async path => { const r = await fetch(`${handler}${path}`, { method: 'POST' }); if (!r.ok) throw Error(`${path}: ${r.status}`); return r.json() }
const wait = async (fn, ms = 30000) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return; await delay(100) } throw Error('timed out waiting for UI/API') }
const rows = []; const prints = []; let cdp
try {
  assert.equal((await get('/idle')).active, 0)
  await wait(async () => { try { return (await fetch(`http://127.0.0.1:${cdpPort}/json/version`)).ok } catch { return false } }, 25000)
  const tabs = await getFromCdp(`${cdpPort}/json/list`)
  cdp = new CDP(tabs.find(t => t.type === 'page').webSocketDebuggerUrl)
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable'); await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  cdp.on('Fetch.requestPaused', async ({ requestId, request }) => {
    const u = new URL(request.url)
    if (u.origin === origin && u.pathname.startsWith('/api/')) {
      if (request.method === 'OPTIONS') return cdp.send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: '*' }] })
      const path = `/proxy${u.pathname.slice(4)}${u.search}`
      const upstream = await fetch(`${backend}${path}`, { method: request.method, headers: { 'Content-Type': request.headers['content-type'] || 'application/json' }, ...(request.postData ? { body: request.postData } : {}) })
      const bytes = Buffer.from(await upstream.arrayBuffer()); const type = upstream.headers.get('Content-Type') || 'application/json'
      let body = null; try { if (type.includes('json')) body = JSON.parse(bytes.toString()) } catch {}
      const row = { at: new Date().toISOString(), method: request.method, path, status: upstream.status, ...(request.postData ? { request: JSON.parse(request.postData) } : {}), ...(body === null ? {} : { response: body }) }
      rows.push(row); await writeFile(`${nativeDir}/api-events.json`, JSON.stringify(rows, null, 2) + '\n')
      return cdp.send('Fetch.fulfillRequest', { requestId, responseCode: upstream.status, responseHeaders: [{ name: 'Content-Type', value: type }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }], body: bytes.toString('base64') })
    }
    if (u.origin === handler && u.pathname === '/print' && request.method === 'POST') {
      const payload = JSON.parse(request.postData || '{}'); const m = /^data:image\/png;base64,(.*)$/.exec(payload.imageDataUrl || '')
      const bytes = m ? Buffer.from(m[1], 'base64') : Buffer.alloc(0)
      prints.push({ at: new Date().toISOString(), key: payload.idempotencyKey, pngBytes: bytes.length, pngSha256: createHash('sha256').update(bytes).digest('hex') })
      await writeFile(`${nativeDir}/print-inputs.json`, JSON.stringify(prints, null, 2) + '\n')
    }
    await cdp.send('Fetch.continueRequest', { requestId })
  })
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.clear();sessionStorage.clear();localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',${JSON.stringify(JSON.stringify({ printQr: true, printChz: false, reprintChz: false, printChzCopies: 2, reprintChzCopies: 1 }))});localStorage.setItem('wms.print.labelSizeId','60x80');sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing');` })
  await cdp.send('Page.navigate', { url: `${origin}/app/ff/fbs?supply_id=${seed.supply_id}` })
  await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)') && document.querySelector('[data-testid="fbs-packing-check-wb"]'))`))
  const dbBeforeSync = await get('/snapshot'); const hBefore = await post('/_proof/status')
  const screen = async () => cdp.eval(`({text:document.body.innerText.slice(-1800),alert:document.querySelector('[role="alert"]')?.textContent||'',scanner:document.querySelector('[data-packing-scan]')?.value||''})`)
  const snap = async name => { const db = await get('/snapshot'); const native = await post('/_proof/status'); const ui = await screen(); await writeFile(`${nativeDir}/${name}.json`, JSON.stringify({ db, native, ui }, null, 2) + '\n'); await writeFile(`${nativeDir}/${name}.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64')); return { db, native, ui } }
  const syncButton = await cdp.eval(`(() => {const e=document.querySelector('[data-testid="fbs-packing-check-wb"]');if(!e||e.disabled)return false;e.click();return true})()`)
  assert(syncButton, 'actual operator Verify in WB button is enabled')
  await wait(() => rows.some(r => r.method === 'POST' && /\/markings\/sync$/.test(r.path) && r.status === 200), 45000)
  await wait(async () => { const s = await get('/snapshot'); return s.synthetic_provider_readbacks?.some(x => x.decision === 'accepted') }, 30000)
  const afterSync = await snap('after-synthetic-provider-sync')
  assert(afterSync.db.synthetic_provider_readbacks.some(x => x.decision === 'accepted'), 'explicit local synthetic provider readback accepted the current bound CIS')
  const scan = async (value, label) => {
    const before = await cdp.eval(`document.querySelector('[data-packing-scan]').value`)
    await cdp.eval(`(() => {const e=document.querySelector('[data-packing-scan]');e.focus();e.value='';e.dispatchEvent(new Event('input',{bubbles:true}));return true})()`)
    await cdp.send('Input.insertText', { text: value }); await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }); await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
    const input = { label, value, priorValue: before, at: new Date().toISOString() }; await writeFile(`${nativeDir}/input-${label}.json`, JSON.stringify(input, null, 2) + '\n'); return input
  }
  const a = dbBeforeSync.orders.find(x => x.id === seed.order_ids[0]); const b = dbBeforeSync.orders.find(x => x.id === seed.order_ids[1])
  assert.equal(a.sticker_barcode, seed.order_sticker_barcodes[0])
  const beforeRescanPrints = (await post('/_proof/status')).accepted_png_count
  const afterARescan = process.env.WMS666_CONTINUE_B_ONLY === '1'
    ? { db: await get('/snapshot'), native: await post('/_proof/status'), ui: await screen() }
    : await (async () => {
      await scan(a.sticker_barcode, 'printed-order-sticker-A')
      await delay(1500)
      const state = await snap('after-A-rescan')
      assert.equal(state.native.accepted_png_count, beforeRescanPrints, 'rescan of completed printed QR did not submit a duplicate native job')
      return state
    })()
  if (process.env.WMS666_CONTINUE_B_ONLY === '1') {
    await writeFile(`${nativeDir}/before-B-after-reload.json`, JSON.stringify(afterARescan, null, 2) + '\n')
  }
  if (process.env.WMS666_SYNC_ONLY === '1') {
    const undoState = await cdp.eval(`(() => {const e=document.querySelector('[data-testid="fbs-scan-undo"]');return {exists:Boolean(e),disabled:e?.disabled??null,label:e?.getAttribute('aria-label')??null}})()`)
    const undoClicked = undoState.exists && !undoState.disabled ? await cdp.eval(`(() => {const e=document.querySelector('[data-testid="fbs-scan-undo"]');e.click();return true})()`) : false
    if (undoClicked) await wait(() => cdp.eval(`!document.querySelector('[data-testid="fbs-scan-undo"]:not(:disabled)')`), 15000)
    const final = await snap('after-final-synthetic-provider-sync')
    await writeFile(`${nativeDir}/summary-sync-only.json`, JSON.stringify({ product_sha: process.env.WMS666_PRODUCT_SHA, runtime_sha: process.env.WMS666_RUNTIME_SHA, seed, after_sync: afterSync, undo_state: undoState, undo_clicked: undoClicked, final, no_new_print: final.native.accepted_png_count === hBefore.accepted_png_count, outbound_marketplace: false }, null, 2) + '\n')
    assert.equal(final.native.accepted_png_count, hBefore.accepted_png_count, 'provider sync is not a print action')
    assert.equal(final.ui.scanner, '', 'no pending scanner input after explicit verification')
    process.stdout.write(JSON.stringify({ undo_state: undoState, undo_clicked: undoClicked, ui: { alert: final.ui.alert, pending: final.ui.text.includes('сканируйте ЧЗ'), scanner: final.ui.scanner }, orders: final.db.orders.filter(x => seed.order_ids.includes(x.id)).map(x => ({ id: x.id, pack_status: x.pack_status })), provider_readbacks: final.db.synthetic_provider_readbacks, receipts: final.native.accepted_png_count }, null, 2) + '\n')
  } else {
  const bInput = await scan(seed.barcode, 'product-barcode-B')
  await wait(() => rows.some(r => r.method === 'POST' && r.path.endsWith('/scan-auto-print') && r.request?.barcode === seed.barcode && r.response?.order_id === b.id), 40000)
  await wait(() => cdp.eval(`Boolean([...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].some(e=>e.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(b.id)}))`), 15000)
  const bUi = await screen(); const dbForB = await get('/snapshot'); const code = dbForB.codes.find(x => x.status === 'available')
  assert(code, 'B has an available seller/product scoped CIS')
  const entered = await cdp.eval(`(() => {const e=[...document.querySelectorAll('[data-testid="fbs-kiz-row-input"]')].find(x=>x.closest('[data-order-id]')?.getAttribute('data-order-id')===${JSON.stringify(b.id)});if(!e)return false;e.focus();return document.activeElement===e})()`)
  assert(entered); await cdp.send('Input.insertText', { text: code.cis }); await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }); await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await writeFile(`${nativeDir}/B-product-and-kiz.json`, JSON.stringify({ product_input: bInput, ui_before_kiz: bUi, code_id: code.id, cis: code.cis, db_before: dbForB }, null, 2) + '\n')
  await wait(async () => (await post('/_proof/status')).accepted_png_count >= hBefore.accepted_png_count + 1, 45000)
  await wait(async () => (await get('/idle')).active === 0, 45000)
  await delay(500); const final = await snap('final'); const receiptText = await readFile(`${here}run-b6d23148/qr-only-continuity-native-api/native/sink-receipts.jsonl`, 'utf8')
  await writeFile(`${nativeDir}/summary.json`, JSON.stringify({ product_sha: process.env.WMS666_PRODUCT_SHA, runtime_sha: process.env.WMS666_RUNTIME_SHA, seed, db_before_sync: dbBeforeSync, handler_before: hBefore, after_sync: afterSync, after_a_rescan: afterARescan, b_input: bInput, b_ui_before_kiz: bUi, final, print_inputs: prints, api_events: rows, receipts: receiptText.trim().split('\n').map(JSON.parse), chromeLog, cdpErrors: cdp.errors }, null, 2) + '\n')
  process.stdout.write(JSON.stringify({ after_sync: afterSync.ui, after_a_rescan_receipts: afterARescan.native.accepted_png_count, b: { order_id: b.id, ui_before_kiz: bUi }, final: final.ui, receipts: final.native.accepted_png_count, idle: await get('/idle') }, null, 2) + '\n')
  }
} catch (error) {
  await writeFile(`${nativeDir}/failure.json`, JSON.stringify({ error: String(error), stack: error?.stack, api_events: rows, print_inputs: prints, ui: cdp ? await cdp.eval(`({text:document.body.innerText.slice(-1400),alert:document.querySelector('[role="alert"]')?.textContent||''})`).catch(String) : null, chromeLog }, null, 2) + '\n').catch(() => {})
  throw error
} finally { cdp?.ws.close(); chrome.kill() }

async function getFromCdp(url) { const r = await fetch(`http://127.0.0.1:${url}`); if (!r.ok) throw Error(`CDP ${r.status}`); return r.json() }
