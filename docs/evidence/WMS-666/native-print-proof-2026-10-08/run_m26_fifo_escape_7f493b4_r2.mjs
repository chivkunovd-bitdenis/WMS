import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'

const here = new URL('.', import.meta.url).pathname
const run = 'run-7f493b4-m26-fifo-escape-r2'
const out = `${here}${run}`
const backend = process.env.WMS666_BACKEND || 'http://127.0.0.1:16692'
const origin = process.env.WMS666_ORIGIN || 'http://127.0.0.1:16696'
const printOrigin = process.env.WMS666_PRINT_ORIGIN || 'http://127.0.0.1:17843'
const cdpPort = Number(process.env.WMS666_CDP_PORT || 16697)
const productSha = '7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc'
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
const apiEvents = []; const printInputs = []; let cdp; let releaseHeldValidation = null; let heldValidation = null; let notifyHeldValidation; const heldValidationReady = new Promise(resolve => { notifyHeldValidation = resolve })
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
      if (path.endsWith('/fbs-orders/kiz/validate') && upstream.status === 200) {
        heldValidation = { requestId, status: upstream.status, type, bodyBase64: bytes.toString('base64'), event }
        await saveJson('held-validation-response.json', { at: new Date().toISOString(), status: upstream.status, request: event.request, response: body })
        notifyHeldValidation()
        await new Promise(resolve => { releaseHeldValidation = resolve })
      }
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

  const ui = () => cdp.eval(`(()=>{const visibleText=(node)=>{if(!node)return '';const style=getComputedStyle(node);const rect=node.getBoundingClientRect();return style.display!=='none'&&style.visibility!=='hidden'&&style.opacity!=='0'&&(rect.width>0||rect.height>0)?node.textContent?.trim()||'':''};const activeRow=document.querySelector('[data-testid="fbs-kiz-row-active"]');const visibleError=visibleText(document.querySelector('[data-testid="fbs-unified-scan"] [role="alert"]'))||visibleText(activeRow?.querySelector('[data-testid="fbs-kiz-scan-error"]'));return {url:location.href,alert:visibleText(document.querySelector('[role="alert"]')),error:visibleError,message:document.querySelector('[data-testid="fbs-kiz-scan-message"]')?.textContent||'',active:document.querySelector('[data-testid="fbs-kiz-scan-active"]')?.innerText||null,activeRow:activeRow?.getAttribute('data-order-id')||null,kizInput:document.querySelector('[data-testid="fbs-kiz-scan-input"]')?.outerHTML||null,rowInput:activeRow?.querySelector('[data-testid="fbs-kiz-row-input"]')?.outerHTML||null,scanner:{value:document.querySelector('[data-packing-scan]')?.value||'',placeholder:document.querySelector('[data-packing-scan]')?.placeholder||'',disabled:document.querySelector('[data-packing-scan]')?.disabled??true},reset:{exists:Boolean(document.querySelector('[data-testid="fbs-kiz-scan-reset"]')),disabled:document.querySelector('[data-testid="fbs-kiz-scan-reset"]')?.disabled??null},focus:{tag:document.activeElement?.tagName||null,testid:document.activeElement?.getAttribute('data-testid')||null,id:document.activeElement?.id||null,placeholder:document.activeElement?.getAttribute('placeholder')||null},body:document.body.innerText.slice(-2000)}})()`)
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
  await wait(async () => { const current = await ui(); return current.activeRow === orderA.id })
  const selectedA = await ui(); await saveJson('ui-A-selected', selectedA); await screenshot('ui-A-selected')
  const aLookup = apiEvents.findLast(row => row.path.includes('/fbs-orders/kiz/lookup') && row.status === 200)
  assert.equal(aLookup.response.order_id, orderA.id)
  assert.equal(selectedA.activeRow, orderA.id)
  assert.match(selectedA.scanner.placeholder, /Честный знак/i)

  const validCis = beforeDb.codes[0].cis
  await physicalScan(validCis, 'valid-kiz-A')
  await Promise.race([heldValidationReady, delay(20000).then(() => { throw Error('timed out waiting for real successful KIZ validation response') })])
  assert(heldValidation, 'the actual API response was held before the UI received it')
  assert.equal(heldValidation.status, 200)
  assert.deepEqual(heldValidation.event.request, { order_id: orderA.id, value: validCis })
  const heldUi = await ui(); const heldDb = await get('/snapshot'); const heldNative = await post('/_proof/status')
  await saveJson('held-before-escape.json', { ui: heldUi, db: heldDb, native: heldNative, held: { status: heldValidation.status, request: heldValidation.event.request, response: JSON.parse(Buffer.from(heldValidation.bodyBase64, 'base64').toString()) }, focus_was_changed_by_runner: false })
  await screenshot('held-before-escape')
  const naturalFocus = heldUi.focus
  const cancellationsBefore = apiEvents.filter(row => row.path.endsWith('/cancel'))
  await delay(750)
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
  await delay(750)
  const whileHeldUi = await ui(); const whileHeldDb = await get('/snapshot'); const whileHeldNative = await post('/_proof/status')
  const cancellationsWhileHeld = apiEvents.filter(row => row.path.endsWith('/cancel'))
  await saveJson('escape-while-validation-held.json', { ui: whileHeldUi, db: whileHeldDb, native: whileHeldNative, natural_focus_after_scan: naturalFocus, cancellations_before: cancellationsBefore, cancellations_while_response_held: cancellationsWhileHeld })
  await screenshot('escape-while-validation-held')
  assert.deepEqual(cancellationsBefore, [], 'no prior cancellation existed before Escape')
  assert.equal(whileHeldNative.accepted_png_count, heldNative.accepted_png_count, 'the printer cannot see this job before validation is returned to the UI')

  releaseHeldValidation()
  releaseHeldValidation = null
  const outcomeUntil = Date.now() + 25000
  let finalNative = await post('/_proof/status')
  let finalDb = await get('/snapshot')
  let finalUi = await ui()
  let finalIdle = await get('/idle')
  const findCurrentBinding = (snapshot) => snapshot.markings.find(row => row.order_id === orderA.id && row.cis === validCis) ?? null
  const isCompleted = () => Boolean(
    findCurrentBinding(finalDb)
    && finalDb.orders.find(row => row.id === orderA.id)?.pack_status === 'packed'
    && finalNative.accepted_png_count > initialReceiptCount
    && finalIdle.active === 0
    && finalUi.activeRow == null
    && !finalUi.error
  )
  while (Date.now() < outcomeUntil && !isCompleted() && !finalUi.error) {
    await delay(150)
    finalNative = await post('/_proof/status'); finalDb = await get('/snapshot'); finalUi = await ui(); finalIdle = await get('/idle')
  }
  finalUi = await ui(); finalDb = await get('/snapshot'); finalNative = await post('/_proof/status'); finalIdle = await get('/idle')
  const commitEvents = apiEvents.filter(row => /fbs-orders\/kiz\/(commit|bind)/.test(row.path))
  const aMarked = findCurrentBinding(finalDb)
  await saveJson('after-response-release.json', { ui: finalUi, db: finalDb, native: finalNative, api_idle: finalIdle, held: { status: heldValidation.status, request: heldValidation.event.request, response: JSON.parse(Buffer.from(heldValidation.bodyBase64, 'base64').toString()) }, cancel_requests_while_held: cancellationsWhileHeld, cancel_requests_total: apiEvents.filter(row => row.path.endsWith('/cancel')), commit_events: commitEvents, marking_for_A: aMarked })
  await screenshot('after-response-release')
  let bSelected = null
  if (finalUi.activeRow == null && !finalUi.error && finalNative.accepted_png_count > initialReceiptCount) {
    await physicalScan(orderB.sticker_barcode, 'sticker-B-next')
    await delay(1000)
    bSelected = await ui(); await saveJson('after-next-B', bSelected); await screenshot('after-next-B')
  }
  await saveJson('result', {
    product_sha: productSha, runtime_sha: productSha,
    case: 'M26 FIFO: Escape during held successful KIZ validation cannot overtake the accepted row scan',
    synthetic_only: true,
    actions: [
      { input: orderA.sticker_barcode, selected_order_id: orderA.id, result: 'A selected by persisted sticker QR barcode' },
      { input: validCis, validation_status: heldValidation.status, request: heldValidation.event.request, natural_focus_after_enter: naturalFocus, result: 'actual validation API returned 200; unchanged response held before UI' },
      { action: 'Escape with natural focus while validation response held', cancel_requests_before_release: cancellationsWhileHeld, native_receipts_before_release: heldNative.accepted_png_count, result: cancellationsWhileHeld.length === 0 ? 'accepted scan remained queued until validation response release' : 'RED: cancellation request reached the API before the validation response reached the UI' },
      { action: 'release unchanged validation response', final_error: finalUi.error, commit_events: commitEvents, current_A_marking: aMarked, native_receipts_after: finalNative.accepted_png_count, order_A_pack_status: finalDb.orders.find(row => row.id === orderA.id)?.pack_status, next_B: bSelected && { active_row: bSelected.activeRow, error: bSelected.error }, result: 'see after-response-release.json for actual post-response outcome' },
    ],
    api_events: apiEvents,
  })
  assert.deepEqual(cancellationsWhileHeld, [], 'Escape cannot overtake an accepted KIZ scan while the real validation response is held')
  assert(isCompleted(), 'A reaches exact current binding, one native QR receipt, packed state, idle API and neutral scan target before B')
  assert(commitEvents.some(row => row.status >= 200 && row.status < 300), 'released valid KIZ is committed for A')
  assert(aMarked, 'A current binding is saved after the unchanged validation response')
  assert(finalNative.accepted_png_count > initialReceiptCount, 'A QR reaches the native print handler after the response is released')
  assert.equal(finalDb.orders.find(row => row.id === orderA.id)?.pack_status, 'packed', 'A completes packing after the delayed accepted scan')
  assert(bSelected && bSelected.activeRow === orderB.id && !bSelected.error, 'the following B sticker selects B after A completes')
  assert.deepEqual(finalDb.stock, beforeDb.stock, 'packing did not change stock')
  console.log(JSON.stringify({ case: 'M26 FIFO delayed validation + Escape', orderA: orderA.id, valid_cis: validCis, held_status: heldValidation.status, focus_after_scan: naturalFocus, cancels_before_release: cancellationsWhileHeld.length, receipt_before: heldNative.accepted_png_count, receipt_after: finalNative.accepted_png_count, A_pack_status: finalDb.orders.find(row => row.id === orderA.id)?.pack_status, B_selected: bSelected?.activeRow, final_error: finalUi.error }, null, 2))
  await writeFile(`${out}/native/chrome.log`, chromeLog)
  console.log(JSON.stringify({ case: 'M26 FIFO delayed validation + Escape', selected_A: orderA.id, selected_B: bSelected?.activeRow, current_cis: validCis, validation_status: heldValidation.status, cancellations_while_held: cancellationsWhileHeld.length, native_receipts: finalNative.accepted_png_count, pack_status: finalDb.orders.find(row => row.id === orderA.id)?.pack_status, API_idle: finalIdle.active }, null, 2))
} catch (error) {
  const debugUi = cdp ? await cdp.eval(`({body:document.body.innerText.slice(-2000),active:document.querySelector('[data-testid="fbs-kiz-scan-active"]')?.innerText||null,activeRow:document.querySelector('[data-testid="fbs-kiz-row-active"]')?.getAttribute('data-order-id')||null,alert:document.querySelector('[role="alert"]')?.textContent||'',error:document.querySelector('[data-testid="fbs-kiz-scan-error"]')?.textContent?.trim()||'',scan:document.querySelector('[data-packing-scan]')?.outerHTML||null,kiz:document.querySelector('[data-testid="fbs-kiz-scan-input"]')?.outerHTML||null,rowKiz:document.querySelector('[data-testid="fbs-kiz-row-active"] [data-testid="fbs-kiz-row-input"]')?.outerHTML||null})`).catch(String) : null
  await saveJson('failure', { error: String(error), debug_ui: debugUi, held_validation: heldValidation && { status: heldValidation.status, request: heldValidation.event.request }, api_events: apiEvents, print_inputs: printInputs, chrome_log: chromeLog }).catch(() => undefined)
  console.error(error)
  process.exitCode = 1
} finally {
  try { releaseHeldValidation?.() } catch {}
  try { cdp?.ws.close() } catch {}
  chrome.kill('SIGTERM')
  await Promise.race([new Promise(resolve => chrome.once('exit', resolve)), delay(5000)])
  await writeFile(`${out}/native/chrome.log`, chromeLog).catch(() => undefined)
  // Chrome's WebSocket can keep Node alive after its own child is stopped.
  setTimeout(() => process.exit(process.exitCode ?? 0), 250).unref()
}
