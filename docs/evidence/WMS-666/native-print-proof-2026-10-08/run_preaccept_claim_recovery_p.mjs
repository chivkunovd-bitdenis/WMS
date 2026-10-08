import assert from 'node:assert/strict';
import { appendFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const [seedFileArg, evidenceDirArg, receiptFileArg] = process.argv.slice(2);
const seedFile = seedFileArg
  ? resolve(seedFileArg)
  : new URL('./run-28a799-final-matrix/seed-public.json', import.meta.url).pathname;
const evidenceRoot = `${evidenceDirArg
  ? resolve(evidenceDirArg)
  : new URL('./run-28a799-final-matrix/preaccept-recovery/', import.meta.url).pathname}/`;
const receiptFile = receiptFileArg
  ? resolve(receiptFileArg)
  : new URL('./run-28a799-final-matrix/native/sink-receipts.jsonl', import.meta.url).pathname;
const seed = JSON.parse(await readFile(seedFile, 'utf8'));
await mkdir(`${evidenceRoot}native-inputs`, { recursive: true });
await writeFile(`${evidenceRoot}api-events.jsonl`, '');
await writeFile(`${evidenceRoot}native-events.jsonl`, '');

const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--disable-background-networking', '--disk-cache-size=1',
  `--user-data-dir=${evidenceRoot}chrome-profile`, '--remote-debugging-port=16697', 'about:blank',
], { stdio: 'ignore' });
let cdp;
class Cdp {
  constructor(url) {
    this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = [];
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (!message.id) {
        if (message.method === 'Fetch.requestPaused') for (const handler of this.handlers) handler(message.params);
        return;
      }
      const pending = this.pending.get(message.id);
      if (pending) {
        this.pending.delete(message.id);
        message.error ? pending.reject(Error(JSON.stringify(message.error))) : pending.resolve(message.result);
      }
    };
  }
  send(method, params = {}) {
    return this.ready.then(() => new Promise((resolve, reject) => {
      const id = ++this.id; this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    }));
  }
  on(handler) { this.handlers.push(handler); }
  eval(expression) {
    return this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }).then((result) => {
      if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
      return result.result.value;
    });
  }
}

const get = async (url, method = 'GET') => {
  const response = await fetch(url, { method });
  if (!response.ok) throw Error(`${url} returned ${response.status}`);
  return response.json();
};
const wait = async (predicate, timeoutMs = 45000) => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await sleep(100);
  }
  throw Error(`Timed out after ${timeoutMs}ms`);
};
const apiEvents = [];
const nativeEvents = [];
const nativeFailureResponse = JSON.stringify({ error: 'synthetic_preacceptance_transport_failure' });
let failedBeforeHandler = false;

try {
  await wait(async () => { try { return (await fetch('http://127.0.0.1:16697/json/version')).ok; } catch { return false; } }, 20000);
  const tabs = await get('http://127.0.0.1:16697/json/list');
  cdp = new Cdp(tabs.find((tab) => tab.type === 'page').webSocketDebuggerUrl);
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable');
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
  cdp.on(async ({ requestId, request }) => {
    const url = new URL(request.url);
    if (url.origin === 'http://127.0.0.1:16696' && url.pathname.startsWith('/api/')) {
      if (request.method === 'OPTIONS') {
        const event = { at: new Date().toISOString(), method: 'OPTIONS', path: url.pathname + url.search, response_status: 200 };
        apiEvents.push(event); await appendFile(`${evidenceRoot}api-events.jsonl`, `${JSON.stringify(event)}\n`);
        await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [
          { name: 'Access-Control-Allow-Origin', value: '*' },
          { name: 'Access-Control-Allow-Headers', value: '*' },
          { name: 'Access-Control-Allow-Methods', value: '*' },
        ] });
        return;
      }
      const path = `/proxy${url.pathname.slice(4)}${url.search}`;
      const upstream = await fetch(`http://127.0.0.1:16692${path}`, {
        method: request.method,
        headers: { 'Content-Type': request.headers['content-type'] || 'application/json' },
        ...(request.postData ? { body: request.postData } : {}),
      });
      const responseBytes = Buffer.from(await upstream.arrayBuffer());
      const event = {
        at: new Date().toISOString(), method: request.method, path, response_status: upstream.status,
        ...(request.postData ? { request: JSON.parse(request.postData) } : {}),
        ...(path.endsWith('/scan-auto-print') && request.method === 'POST'
          ? { response: JSON.parse(responseBytes.toString()) }
          : {}),
      };
      apiEvents.push(event); await appendFile(`${evidenceRoot}api-events.jsonl`, `${JSON.stringify(event)}\n`);
      await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: upstream.status, responseHeaders: [
        { name: 'Content-Type', value: upstream.headers.get('Content-Type') || 'application/json' },
        { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' },
      ], body: responseBytes.toString('base64') });
      return;
    }
    if (url.origin === 'http://127.0.0.1:17843' && url.pathname === '/print' && request.method === 'POST') {
      const body = JSON.parse(request.postData || '{}');
      const match = /^data:image\/png;base64,(.+)$/.exec(String(body.imageDataUrl ?? ''));
      const png = match ? Buffer.from(match[1], 'base64') : Buffer.alloc(0);
      const index = nativeEvents.length + 1;
      const pngName = `native-input-${String(index).padStart(2, '0')}.png`;
      if (png.length) await writeFile(`${evidenceRoot}native-inputs/${pngName}`, png);
      const event = {
        at: new Date().toISOString(), method: request.method, path: url.pathname,
        idempotency_key: body.idempotencyKey, width_mm: body.widthMm, height_mm: body.heightMm,
        png_bytes: png.length, png_sha256: createHash('sha256').update(png).digest('hex'),
        png: png.length ? `native-inputs/${pngName}` : null,
        simulated_before_handler_acceptance: !failedBeforeHandler,
      };
      nativeEvents.push(event); await appendFile(`${evidenceRoot}native-events.jsonl`, `${JSON.stringify(event)}\n`);
      if (!failedBeforeHandler) {
        failedBeforeHandler = true;
        await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: 503, responseHeaders: [
          { name: 'Content-Type', value: 'application/json' },
          { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' },
        ], body: Buffer.from(nativeFailureResponse).toString('base64') });
        return;
      }
    }
    await cdp.send('Fetch.continueRequest', { requestId });
  });

  // Isolate one server-claimed QR job so CHZ cannot become a second print path
  // after the synthetic pre-acceptance failure.
  const prefs = { printQr: true, printChz: true, reprintChz: false, printChzCopies: 2, reprintChzCopies: 1 };
  const added = await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.clear(); sessionStorage.clear();
    localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user', ${JSON.stringify(JSON.stringify(prefs))});
    localStorage.setItem('wms.print.labelSizeId','60x80');
    sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');
    sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing');
  ` });
  await cdp.send('Page.navigate', { url: `http://127.0.0.1:16696/app/ff/fbs?supply_id=${seed.supply_id}` });
  await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)')&&document.querySelectorAll('[data-order-id]').length===2)`));
  await cdp.send('Page.removeScriptToEvaluateOnNewDocument', { identifier: added.identifier });
  const before = { db: await get('http://127.0.0.1:16692/snapshot'), native: await get('http://127.0.0.1:17843/_proof/status', 'POST') };
  assert.equal(before.native.accepted_png_count, 0);
  const scan = async () => {
    await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)'))`));
    await cdp.eval(`document.querySelector('[data-packing-scan]').focus()`);
    await cdp.send('Input.insertText', { text: seed.barcode });
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  };
  await scan();
  await wait(() => failedBeforeHandler && apiEvents.some((event) => event.path?.endsWith('/scan-auto-print') && event.response_status === 200));
  await sleep(900);
  const afterFirstFailure = {
    ui: await cdp.eval(`({error:document.querySelector('[role="alert"]')?.textContent||'',body:document.body.innerText.slice(-1000)})`),
    db: await get('http://127.0.0.1:16692/snapshot'),
    native: await get('http://127.0.0.1:17843/_proof/status', 'POST'),
  };
  assert.equal(afterFirstFailure.native.accepted_png_count, 0, 'first PNG was rejected before the real Handler accepted it');
  await writeFile(`${evidenceRoot}before-reload.json`, JSON.stringify({ before, afterFirstFailure, apiEvents, nativeEvents }, null, 2));
  await writeFile(`${evidenceRoot}before-reload.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'));

  await cdp.send('Page.reload');
  await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)')&&document.querySelectorAll('[data-order-id]').length===2)`));
  await scan();
  await wait(() => nativeEvents.length >= 2);
  await wait(async () => (await get('http://127.0.0.1:17843/_proof/status', 'POST')).accepted_png_count >= 3);
  await sleep(900);
  await sleep(750);
  const afterRecovery = {
    ui: await cdp.eval(`({error:document.querySelector('[role="alert"]')?.textContent||'',body:document.body.innerText.slice(-1000)})`),
    db: await get('http://127.0.0.1:16692/snapshot'),
    native: await get('http://127.0.0.1:17843/_proof/status', 'POST'),
    apiEvents, nativeEvents,
  };
  await writeFile(`${evidenceRoot}after-recovery.json`, JSON.stringify(afterRecovery, null, 2));
  await writeFile(`${evidenceRoot}after-recovery.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'));

  const scans = apiEvents.filter((event) => event.path?.endsWith('/scan-auto-print') && event.method === 'POST');
  const nativeQr = nativeEvents.slice(0, 2);
  assert.equal(scans.length, 2, 'React made one real scan claim before and one after reload');
  assert.equal(scans[0].response_status, 200);
  assert.equal(nativeQr.length, 2, 'native transport was attempted before and after reload');
  assert.equal(scans[1].response_status, 200);
  assert.equal(scans[0].response?.order_id, scans[1].response?.order_id, 'reload/rescan preserves the same claimed order');
  assert.equal(scans[0].response?.scan_id, scans[1].response?.scan_id, 'reload/rescan recovers the same scan intent');
  assert.equal(nativeQr[0].idempotency_key, scans[0].response?.scan_id, 'native job uses the server claim key');
  assert.equal(nativeQr[0].idempotency_key, nativeQr[1].idempotency_key, 'retry reuses the exact native job key');
  assert.equal(nativeQr[0].png_sha256, nativeQr[1].png_sha256, 'retry reuses exact rendered PNG bytes');
  const successfulReceiptCount = afterRecovery.native.accepted_png_count;
  assert.equal(successfulReceiptCount, 3, 'one QR plus exactly two CHZ copies were accepted after the pre-acceptance failure');
  const sinkReceipts = (await readFile(receiptFile, 'utf8'))
    .trim().split('\n').filter(Boolean).map(JSON.parse);
  assert.equal(sinkReceipts.length, 3, 'the sink contains one QR receipt and two CHZ-copy receipts');
  assert.equal(sinkReceipts[0].job_key, nativeQr[0].idempotency_key);
  assert.deepEqual(sinkReceipts.slice(1).map((entry) => entry.job_key), [`${nativeQr[0].idempotency_key}:chz`, `${nativeQr[0].idempotency_key}:chz:c2`]);
  const selectedOrderIds = new Set(scans.map((event) => event.response?.order_id).filter(Boolean));
  assert.equal(selectedOrderIds.size, 1, 'reload/retry must not consume a neighboring order');
  console.log(JSON.stringify({ seed: { supply_id: seed.supply_id, order_ids: seed.order_ids }, scans: scans.map((event) => ({ request: event.request, response: event.response })), nativeQr, sinkReceipts, successfulReceiptCount, report: `${evidenceRoot}after-recovery.json` }, null, 2));
} catch (error) {
  await writeFile(`${evidenceRoot}failure-trace.json`, JSON.stringify({
    at: new Date().toISOString(), error: String(error), apiEvents, nativeEvents,
  }, null, 2));
  throw error;
} finally {
  cdp?.ws.close(); chrome.kill();
}
