import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { appendFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { setTimeout as sleep } from 'node:timers/promises';

const base = new URL('./run-28a799-final-matrix/', import.meta.url).pathname;
const seed = JSON.parse(await readFile(`${base}seed-public.json`, 'utf8'));
await mkdir(`${base}chrome-profile`, { recursive: true });
await writeFile(`${base}api-events.jsonl`, '');
await writeFile(`${base}native-http-events.jsonl`, '');
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--disable-background-networking', '--disk-cache-size=1',
  `--user-data-dir=${base}chrome-profile`, '--remote-debugging-port=16697', 'about:blank',
], { stdio: 'ignore' });
let cdp;
class Cdp {
  constructor(url) {
    this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = [];
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (!message.id) { if (message.method === 'Fetch.requestPaused') for (const handler of this.handlers) handler(message.params); return; }
      const item = this.pending.get(message.id);
      if (item) { this.pending.delete(message.id); message.error ? item.reject(Error(JSON.stringify(message.error))) : item.resolve(message.result); }
    };
  }
  send(method, params = {}) { return this.ready.then(() => new Promise((resolve, reject) => { const id = ++this.id; this.pending.set(id, { resolve, reject }); this.ws.send(JSON.stringify({ id, method, params })); })); }
  on(handler) { this.handlers.push(handler); }
  eval(expression) { return this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }).then((result) => { if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails)); return result.result.value; }); }
}
const get = async (url, method = 'GET') => { const response = await fetch(url, { method }); if (!response.ok) throw Error(`${url} returned ${response.status}`); return response.json(); };
const wait = async (fn, ms = 45000) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return; await sleep(150); } throw Error('wait timeout'); };

try {
  await wait(async () => { try { return (await fetch('http://127.0.0.1:16697/json/version')).ok; } catch { return false; } }, 20000);
  const tabs = await get('http://127.0.0.1:16697/json/list');
  cdp = new Cdp(tabs.find((tab) => tab.type === 'page').webSocketDebuggerUrl);
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable');
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*'}] });
  const api = [];
  cdp.on(async ({ requestId, request }) => {
    const url = new URL(request.url);
    if (url.origin === 'http://127.0.0.1:16696' && url.pathname.startsWith('/api/')) {
      if (request.method === 'OPTIONS') {
        await appendFile(`${base}api-events.jsonl`, `${JSON.stringify({ at: new Date().toISOString(), method: request.method, path: url.pathname + url.search, response_status: 200 })}\n`);
        await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [
          { name: 'Access-Control-Allow-Origin', value: '*' },
          { name: 'Access-Control-Allow-Headers', value: '*' },
          { name: 'Access-Control-Allow-Methods', value: '*' },
        ] });
        return;
      }
      const path = `/proxy${url.pathname.slice(4)}${url.search}`;
      const response = await fetch(`http://127.0.0.1:16692${path}`, {
        method: request.method,
        headers: { 'Content-Type': request.headers['content-type'] || 'application/json' },
        ...(request.postData ? { body: request.postData } : {}),
      });
      const bytes = Buffer.from(await response.arrayBuffer());
      const row = { method: request.method, path, status: response.status, bytes: bytes.length };
      if (path.endsWith('/scan-auto-print') && request.method === 'POST') { row.request = JSON.parse(request.postData); row.response = JSON.parse(bytes.toString()); }
      api.push(row);
      await appendFile(`${base}api-events.jsonl`, `${JSON.stringify({ at: new Date().toISOString(), ...row })}\n`);
      await cdp.send('Fetch.fulfillRequest', { requestId, responseCode: response.status, responseHeaders: [
        { name: 'Content-Type', value: response.headers.get('Content-Type') || 'application/json' },
        { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' },
      ], body: bytes.toString('base64') });
      return;
    }
    const event = { at: new Date().toISOString(), method: request.method, url: request.url };
    if (url.pathname === '/print' && request.method === 'POST' && request.postData) {
      const body = JSON.parse(request.postData);
      const match = /^data:image\/png;base64,(.+)$/.exec(String(body.imageDataUrl ?? ''));
      const png = match ? Buffer.from(match[1], 'base64') : Buffer.alloc(0);
      const inputPath = `${base}native-http-input-${String(Date.now())}.png`;
      if (png.length) await writeFile(inputPath, png);
      event.print = {
        idempotencyKey: body.idempotencyKey,
        widthMm: body.widthMm,
        heightMm: body.heightMm,
        pngBytes: png.length,
        pngSha256: createHash('sha256').update(png).digest('hex'),
        png: png.length ? inputPath.split('/').at(-1) : null,
      };
    }
    await appendFile(`${base}native-http-events.jsonl`, `${JSON.stringify(event)}\n`);
    await cdp.send('Fetch.continueRequest', { requestId });
  });
  const prefs = { printQr: true, printChz: false, reprintChz: false, printChzCopies: 2, reprintChzCopies: 1 };
  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.clear();sessionStorage.clear();localStorage.setItem('wms:fbs:scan-auto-print:unknown-tenant:unknown-user',${JSON.stringify(JSON.stringify(prefs))});localStorage.setItem('wms.print.labelSizeId','60x80');sessionStorage.setItem('wms:fbs:${seed.supply_id}:stage','packing');sessionStorage.setItem('wms:fbs:assembly:${seed.supply_id}:stage','packing')` });
  await cdp.send('Page.navigate', { url: `http://127.0.0.1:16696/app/ff/fbs?supply_id=${seed.supply_id}` });
  await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)')&&document.querySelectorAll('[data-order-id]').length===2)`));
  const dbBefore = await get('http://127.0.0.1:16692/snapshot');
  const initialNative = await get('http://127.0.0.1:17843/_proof/status', 'POST');
  assert.equal(initialNative.accepted_png_count, 0);
  const ui = async () => cdp.eval(`({qr:document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input').checked,chz:document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input').checked})`);
  const scan = async () => {
    await wait(() => cdp.eval(`Boolean(document.querySelector('[data-packing-scan]:not(:disabled)'))`));
    await cdp.eval(`document.querySelector('[data-packing-scan]').focus()`);
    await cdp.send('Input.insertText', { text: seed.barcode });
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  };
  const firstUi = await ui(); assert.deepEqual(firstUi, { qr: true, chz: false });
  await writeFile(`${base}qr-only-before.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  await scan();
  await sleep(2500);
  await writeFile(`${base}qr-only-debug.json`, JSON.stringify({
    ui: await cdp.eval(`({url:location.href,alert:document.querySelector('[role="alert"]')?.textContent||'',body:document.body.innerText.slice(-1200)})`),
    native: await get('http://127.0.0.1:17843/_proof/status', 'POST'),
    api,
  }, null, 2));
  await wait(async () => (await get('http://127.0.0.1:17843/_proof/status', 'POST')).accepted_png_count === 1);
  await sleep(400);
  const afterQrOnly = await get('http://127.0.0.1:17843/_proof/status', 'POST');
  const qrOnlyApi = api.filter((row) => row.path.endsWith('/scan-auto-print') && row.method === 'POST');
  assert.equal(qrOnlyApi.length, 1);
  const qrReceipts = (await readFile(`${base}native/sink-receipts.jsonl`, 'utf8')).trim().split('\n').map(JSON.parse);
  assert.equal(qrReceipts.length, 1, 'QR-only dispatched exactly one native job');
  assert.equal(qrReceipts[0].job_key, qrOnlyApi[0].response.scan_id, 'QR-only receipt has the API scan key');

  await cdp.eval(`document.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input').click();document.querySelector('[data-testid="fbs-scan-print-chz-toggle"] input').click()`);
  const secondUi = await ui(); assert.deepEqual(secondUi, { qr: false, chz: true });
  await writeFile(`${base}chz-only-before.png`, Buffer.from((await cdp.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  await scan();
  await wait(() => api.filter((row) => row.path.endsWith('/scan-auto-print') && row.method === 'POST').length === 2);
  await wait(async () => (await get('http://127.0.0.1:17843/_proof/status', 'POST')).accepted_png_count === 3);
  await sleep(500);
  const after = await get('http://127.0.0.1:17843/_proof/status', 'POST');
  const dbAfter = await get('http://127.0.0.1:16692/snapshot');
  const task = await get(`http://127.0.0.1:16692/proxy/operations/packaging-tasks/${seed.task_id}`);
  const allReceipts = (await readFile(`${base}native/sink-receipts.jsonl`, 'utf8')).trim().split('\n').map(JSON.parse);
  assert.equal(allReceipts.length, 3, 'QR-only plus two CHZ copies');
  const report = {
    candidate: '28a7999fefd886de41f6ffda5b05b69cd49aa496',
    case: 'QR-only then CHZ-only using actual product scans and real native handler',
    seed: { supply_id: seed.supply_id, order_ids: seed.order_ids, task_id: seed.task_id, barcode: seed.barcode },
    dbBefore, initialNative, qrOnly: { ui: firstUi, after: afterQrOnly, scan: qrOnlyApi[0].response, receipts: qrReceipts },
    chzOnly: { ui: secondUi, scan: api.filter((row) => row.path.endsWith('/scan-auto-print') && row.method === 'POST')[1].response, receipts: allReceipts.slice(1) },
    after, dbAfter, task, api: api.map(({ request, response, ...rest }) => ({ ...rest, ...(response ? { response } : {}) })),
    uiAfter: await cdp.eval(`document.body.innerText.slice(-1000)`),
  };
  await writeFile(`${base}qr-chz-modes-evidence.json`, `${JSON.stringify(report, null, 2)}\n`);
  await writeFile(`${base}api-requests.json`, `${JSON.stringify(api, null, 2)}\n`);
  console.log(JSON.stringify({ qrOnly: report.qrOnly, chzOnly: report.chzOnly, dbAfter, task }, null, 2));
} finally { cdp?.ws.close(); chrome.kill(); }
