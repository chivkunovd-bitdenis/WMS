import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { setTimeout as delay } from 'node:timers/promises'

const base = new URL('.', import.meta.url).pathname
const run = process.env.WMS666_EVIDENCE_RUN || 'run-b6d23148/flag-mutual-exclusion'
const out = `${base}${run}`
const profile = process.env.WMS666_CHROME_PROFILE || `${base}../../../../../../run-b6d23148/clear-scan-final2/chrome-profile`
const seed = JSON.parse(await readFile(`${base}${run.split('/').slice(0, -1).join('/')}/seed-public.json`, 'utf8'))
await mkdir(out, { recursive: true })

const chrome = spawn(process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--mute-audio', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--disable-background-networking', '--disable-extensions',
  `--user-data-dir=${profile}`, '--remote-debugging-port=16697', 'about:blank',
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
        for (const handler of this.handlers.get(message.method) ?? []) Promise.resolve(handler(message.params)).catch(() => {})
        return
      }
      const pending = this.pending.get(message.id)
      if (!pending) return
      this.pending.delete(message.id)
      message.error ? pending.reject(Error(JSON.stringify(message.error))) : pending.resolve(message.result)
    }
  }
  async send(method, params = {}) {
    await this.ready
    const id = ++this.id
    this.ws.send(JSON.stringify({ id, method, params }))
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }))
  }
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails))
    return r.result.value
  }
  on(method, handler) { this.handlers.set(method, [...(this.handlers.get(method) ?? []), handler]) }
}
const waitFor = async (test, timeout = 30000) => {
  const end = Date.now() + timeout
  while (Date.now() < end) { if (await test()) return; await delay(200) }
  throw Error('Timed out waiting for UI')
}
let cdp
const records = []
try {
  await waitFor(async () => { try { return (await fetch('http://127.0.0.1:16697/json/version')).ok } catch { return false } })
  const tab = (await (await fetch('http://127.0.0.1:16697/json/list')).json()).find(x => x.type === 'page')
  cdp = new CDP(tab.webSocketDebuggerUrl)
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  cdp.on('Fetch.requestPaused', async ({ requestId, request }) => {
    const url = new URL(request.url)
    if (url.origin === 'http://127.0.0.1:16696' && url.pathname.startsWith('/api/')) {
      if (request.method === 'OPTIONS') {
        await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: '*' }] })
        return
      }
      const upstream = await fetch(`http://127.0.0.1:16692/proxy${url.pathname.slice('/api'.length)}${url.search}`, {
        method: request.method,
        headers: { 'Content-Type': request.headers['content-type'] || 'application/json' },
        ...(request.postData ? { body: request.postData } : {}),
      })
      const bytes = Buffer.from(await upstream.arrayBuffer())
      await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: upstream.status, responseHeaders: [
        { name: 'Content-Type', value: upstream.headers.get('content-type') || 'application/json' },
        { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' },
      ], body: bytes.toString('base64') })
      return
    }
    await cdp.send('Fetch.continueRequest', { requestId })
  })
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.clear();sessionStorage.clear();localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',${JSON.stringify(JSON.stringify({ printQr: false, printChz: false, reprintChz: false, printChzCopies: 1, reprintChzCopies: 1 }))});sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing');` })
  await cdp.send('Page.navigate', { url: `http://127.0.0.1:16696/app/ff/fbs?supply_id=${seed.supply_id}` })
  await waitFor(() => cdp.evaluate(`Boolean(document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input')&&document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input')&&document.querySelector('[data-testid="fbs-kiz-auto-reprint-toggle"] input'))`))

  const state = async () => cdp.evaluate(`(() => {const qr=document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input');const chz=document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input');const reprint=document.querySelector('[data-testid="fbs-kiz-auto-reprint-toggle"] input');return {qr:qr.checked,chz:chz.checked,chzDisabled:chz.disabled,reprint:reprint.checked,reprintDisabled:reprint.disabled,chzCopies:document.querySelector('[data-testid="fbs-scan-print-chz-copies-value"]')?.textContent??null,reprintCopies:document.querySelector('[data-testid="fbs-scan-reprint-chz-copies-value"]')?.textContent??null,bodyText:document.body.innerText.slice(-1000)}})()`)
  const toggle = async (testId, checked) => cdp.evaluate(`(() => {const e=document.querySelector('[data-testid="${testId}"] input');if(e&&e.checked!==${Boolean(checked)}&&!e.disabled)e.click();return !!e})()`)
  const setCopies = async (valueTestId, plusTestId, minusTestId, target) => {
    let now = Number(await cdp.evaluate(`document.querySelector('[data-testid="${valueTestId}"]')?.textContent`))
    const button = target > now ? plusTestId : minusTestId
    while (now !== target) {
      await cdp.evaluate(`document.querySelector('[data-testid="${button}"]')?.click()`)
      await delay(80)
      now = Number(await cdp.evaluate(`document.querySelector('[data-testid="${valueTestId}"]')?.textContent`))
      if (!Number.isFinite(now)) throw Error(`missing copies counter ${valueTestId}`)
    }
  }
  const capture = async name => {
    await delay(300)
    const value = await state()
    await writeFile(`${out}/${name}.json`, JSON.stringify(value, null, 2))
    await writeFile(`${out}/${name}.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'))
    records.push({ name, ...value })
    return value
  }

  await toggle('fbs-scan-print-qr-toggle', true)
  await toggle('fbs-scan-print-chz-toggle', true)
  await setCopies('fbs-scan-print-chz-copies-value', 'fbs-scan-print-chz-copies-plus', 'fbs-scan-print-chz-copies-minus', 2)
  let value = await state()
  assert.equal(value.qr, true)
  assert.equal(value.chz, true)
  assert.equal(value.reprintDisabled, true)
  await toggle('fbs-kiz-auto-reprint-toggle', true)
  value = await capture('qr-on-chz-on-reprint-blocked')
  assert.equal(value.reprint, false, 'QR on + CHZ on blocks reprint and preserves the chosen CHZ count')
  assert.equal(value.chzCopies, '2')

  await toggle('fbs-scan-print-qr-toggle', false)
  value = await capture('qr-off-chz-on-reprint-blocked')
  assert.equal(value.qr, false)
  assert.equal(value.chz, true)
  assert.equal(value.reprintDisabled, true)
  assert.equal(value.reprint, false)

  await toggle('fbs-scan-print-chz-toggle', false)
  await toggle('fbs-kiz-auto-reprint-toggle', true)
  await setCopies('fbs-scan-reprint-chz-copies-value', 'fbs-scan-reprint-chz-copies-plus', 'fbs-scan-reprint-chz-copies-minus', 2)
  value = await capture('qr-off-reprint-on-chz-blocked')
  assert.equal(value.qr, false)
  assert.equal(value.chz, false)
  assert.equal(value.reprint, true)
  assert.equal(value.chzDisabled, true)
  assert.equal(value.reprintCopies, '2')

  await toggle('fbs-scan-print-qr-toggle', true)
  await toggle('fbs-scan-print-chz-toggle', true)
  value = await capture('qr-on-reprint-on-chz-blocked')
  assert.equal(value.qr, true)
  assert.equal(value.reprint, true)
  assert.equal(value.chz, false)
  assert.equal(value.chzDisabled, true)
  assert.equal(value.reprintCopies, '2', 'the reprint copy setting remains intact when QR changes')

  await writeFile(`${out}/matrix.json`, `${JSON.stringify({ product_sha: 'b6d23148f1571d08d13d83c6179c385e2f6a1efc', runtime_checkout_sha: 'b6d23148f1571d08d13d83c6179c385e2f6a1efc', conclusion: 'CHZ print and KIZ reprint cannot be enabled together in the actual UI; QR is independent, both QR states verified, and each enabled mode retains its own copies count.', states: records }, null, 2)}\n`)
  console.log(JSON.stringify(records.map(({ name, qr, chz, chzDisabled, reprint, reprintDisabled, chzCopies, reprintCopies }) => ({ name, qr, chz, chzDisabled, reprint, reprintDisabled, chzCopies, reprintCopies })), null, 2))
} catch (error) {
  await writeFile(`${out}/failure.json`, JSON.stringify({ error: String(error), chromeLog }, null, 2)).catch(() => {})
  throw error
} finally {
  cdp?.ws.close()
  chrome.kill()
}
