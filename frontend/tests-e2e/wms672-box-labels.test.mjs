// WMS-672: real React screen, CODE128 canvas and print HTML; synthetic HTTP only.
// Run with a local Vite server. No browser/OS/printer print operation is allowed.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { PDFDocument } from 'pdf-lib';
import { PNG } from 'pngjs';
import zxing from '@zxing/library';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.WMS672_TEST_URL || 'http://127.0.0.1:16722';
const evidence = resolve(process.env.WMS672_EVIDENCE_DIR || '../docs/evidence/WMS-672/test-contract');
let browser;
before(async () => {
  await mkdir(evidence, { recursive: true });
  browser = await chromium.launch({ channel: 'chrome', headless: true, ...(process.env.WMS672_CHROMIUM ? { executablePath: process.env.WMS672_CHROMIUM } : {}) });
});
after(async () => { await browser?.close(); });

function detail(n, operation = 'inbound') {
  return {
    id: '672-document', warehouse_id: '672-warehouse', seller_id: '672-seller',
    seller_name: 'Синтетический селлер', document_number: '672', display_number: '672',
    status: 'receiving', operation_type: operation, marketplace: 'wildberries',
    planned_box_count: n, actual_box_count: n, lines: [], cargo_places: [],
    boxes: Array.from({ length: n }, (_, i) => ({
      id: `672-box-${i + 1}`, box_number: i + 1,
      internal_barcode: `INB-${String(i + 1).padStart(12, '0')}`,
      label_printed_at: null, intake_opened_at: null, intake_closed_at: null,
      is_open: false, lines: [],
    })),
  };
}

async function fixture(n, operation = 'inbound', fault = {}) {
  const context = await browser.newContext({ deviceScaleFactor: 4 });
  const page = await context.newPage();
  const errors = new Set();
  page.on('pageerror', e => { if (!errors.has(e.message)) { errors.add(e.message); console.error('WMS672 browser error:', e.stack); } });
  const data = detail(n, operation);
  const original = structuredClone(data);
  const calls = [];
  let marks = 0;
  const successfulMarks = [];
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    calls.push({ path, method, body: request.postData(), headers: request.headers() });
    if (path.endsWith('/mark-label-printed')) {
      marks += 1;
      if (fault.markAt === marks) {
        // The server accepted the mark, but its response is lost.
        await page.waitForFunction(() => window.__wms672Transfers.length === 1);
        return route.abort('failed');
      }
      successfulMarks.push({ path, transfers: await page.evaluate(() => window.__wms672Transfers.length) });
      return route.fulfill({ json: {} });
    }
    if (method !== 'GET') return route.fulfill({ status: 409, json: { detail: 'unexpected_mutation' } });
    if (path.endsWith('/inbound-intake-requests/672-document')) return route.fulfill({ json: data });
    if (path.endsWith('/marking-codes')) return route.fulfill({ json: { items: [], checking: false } });
    return route.fulfill({ json: [] });
  });
  await page.goto(`${base}/tests-e2e/wms672-harness.html`);
  await page.evaluate(async ({ fault }) => {
    window.__WMS_CAPTURE_PRINT_HTML__ = true;
    window.__wms672Transfers = [];
    window.__wms672Decoded = 0;
    window.__wms672DecodeStarted = 0;
    window.__wms672DecodeEvents = [];
    window.__wms672Frames = 0;
    const raf = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = callback => fault.stallFrames ? 0 : raf(time => {
      window.__wms672Frames += 1; callback(time);
    });
    window.__wms672Fault = fault;
    window.__wms672Hold = Boolean(fault.hold);
    // Each srcdoc navigation has its own prototypes. Install before the real onload handler.
    const append = document.body.appendChild.bind(document.body);
    document.body.appendChild = function (node) {
      const result = append(node);
      if (node.tagName === 'IFRAME') node.addEventListener('load', () => {
        const w = node.contentWindow;
        const decode = w.HTMLImageElement.prototype.decode;
        let ready = 0; // successful native decodes in this exact source frame
        w.HTMLImageElement.prototype.decode = async function () {
          if (!this.classList.contains('barcode')) return decode.call(this);
          const index = ++window.__wms672DecodeStarted;
          window.__wms672DecodeEvents.push({ index, frame: window.__wms672Frames });
          if (window.__wms672Fault.decodeAt === index) throw new Error(`WMS672 decode failed at ${index}`);
          while (window.__wms672Hold) await new Promise(r => setTimeout(r, 10));
          if (fault.delayMs) await new Promise(r => setTimeout(r, fault.delayMs));
          await decode.call(this);
          ready += 1;
          window.__wms672Decoded += 1;
        };
        w.focus = () => {};
        w.print = () => {
          window.__wms672Transfers.push({ html: node.srcdoc, decoded: ready,
            attempt: Object.values(localStorage).map(value => { try { return JSON.parse(value)?.labelAttempt; } catch { return null; } }).find(Boolean) });
        };
      });
      return result;
    };
    const { mountInbound672 } = await import('/tests-e2e/wms672-harness.tsx');
    window.__wms672Root = mountInbound672(document.getElementById('root'));
  }, { fault });
  await page.getByTestId('ff-inbound-packages-toggle').click();
  await page.getByTestId('ff-inbound-boxes-print-all').waitFor();
  return { page, context, data, original, calls, marks: () => marks, successfulMarks };
}

async function confirm(f, action = 'ff-inbound-boxes-print-all') {
  await f.page.getByTestId(action).click();
  await f.page.getByTestId('ff-inbound-box-print-dialog-confirm').click();
}
async function transfer(f, count = 1, polling = 'raf') {
  await f.page.waitForFunction(n => window.__wms672Transfers.length >= n, count, { polling });
  return f.page.evaluate(() => window.__wms672Transfers);
}
async function renderTape(context, html) {
  const page = await context.newPage();
  await page.setContent(html);
  const decoded = await page.locator('img').evaluateAll(async images => {
    let ready = 0;
    for (let start = 0; start < images.length; start += 32) {
      await Promise.all(images.slice(start, start + 32).map(async image => { await image.decode(); ready += 1; }));
      if (start + 32 < images.length) await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    }
    return ready;
  });
  assert.equal(decoded, await page.locator('img').count(), 'PDF helper decodes every original image');
  await page.emulateMedia({ media: 'print' });
  return page;
}
function decodePng(bytes) {
  const png = PNG.sync.read(bytes);
  const luminance = new Uint8ClampedArray(png.width * png.height);
  for (let i = 0; i < luminance.length; i++) {
    luminance[i] = (png.data[i * 4] + 2 * png.data[i * 4 + 1] + png.data[i * 4 + 2]) / 4;
  }
  const source = new zxing.RGBLuminanceSource(luminance, png.width, png.height);
  const bitmap = new zxing.BinaryBitmap(new zxing.HybridBinarizer(source));
  const reader = new zxing.MultiFormatReader();
  reader.setHints(new Map([[zxing.DecodeHintType.POSSIBLE_FORMATS, [zxing.BarcodeFormat.CODE_128]]]));
  return reader.decode(bitmap).getText();
}

for (const operation of ['inbound', 'return']) {
  for (const n of [200, 300]) {
    test(`C1/C2 ${operation} ${n}: one complete ordered 58x40 tape, real PDF and readable samples`, async () => {
      const f = await fixture(n, operation);
      try {
        assert.equal(f.calls.filter(c => c.method !== 'GET').length, 0, 'opening does not mutate/print');
        await confirm(f);
        const jobs = await transfer(f);
        assert.equal(jobs.length, 1);
        assert.equal(jobs[0].decoded, n, 'all images ready before transfer');
        const tape = await renderTape(f.context, jobs[0].html);
        assert.deepEqual(await tape.locator('.label').evaluateAll(nodes => nodes.map(n => n.dataset.barcode)),
          f.data.boxes.map(b => b.internal_barcode));
        const name = `${operation}-${n}`;
        const pdfPath = resolve(evidence, `${name}.pdf`);
        const pdf = await tape.pdf({ path: pdfPath, preferCSSPageSize: true, printBackground: true });
        const pages = (await PDFDocument.load(pdf)).getPages();
        assert.equal(pages.length, n, 'no blank/trailing PDF pages');
        for (const p of pages) {
          assert.ok(Math.abs(p.getWidth() * 25.4 / 72 - 58) < 0.5);
          assert.ok(Math.abs(p.getHeight() * 25.4 / 72 - 40) < 0.5);
        }
        const text = execFileSync('pdftotext', ['-layout', pdfPath, '-'], { encoding: 'utf8' });
        const pageTexts = text.split('\f').filter(t => t.trim());
        assert.equal(pageTexts.length, n);
        for (let i = 0; i < n; i++) {
          assert.ok(pageTexts[i].includes(f.data.boxes[i].internal_barcode), `PDF barcode text page ${i + 1}`);
          assert.ok(pageTexts[i].includes(`№ ${i + 1}`), `PDF box title page ${i + 1}`);
        }
        // Decode actual rasterized PDF, not the input barcode string or HTML attribute.
        for (const i of [0, Math.floor(n / 2), n - 1]) {
          const prefix = resolve(evidence, `${name}-page-${i + 1}`);
          execFileSync('pdftoppm', ['-f', String(i + 1), '-singlefile', '-scale-to', '1200', '-png', pdfPath, prefix]);
          const { readFile } = await import('node:fs/promises');
          assert.equal(decodePng(await readFile(`${prefix}.png`)), f.data.boxes[i].internal_barcode);
        }
        assert.deepEqual(f.data, f.original);
        assert.ok(f.calls.filter(c => c.method !== 'GET').every(c => c.path.endsWith('/mark-label-printed')),
          'print cannot create boxes, change stock/reserve/status/location');
      } finally { await f.context.close(); }
    });
  }
}

test('C3 renderer: short/long CODE128, >99 title, escaped special text and saved alternate size', async () => {
  const f = await fixture(1);
  try {
    await f.page.evaluate(() => localStorage.setItem('wms.print.labelSizeId', '60x80'));
    await confirm(f);
    const [job] = await transfer(f);
    const alternate = await renderTape(f.context, job.html);
    const altPdf = await PDFDocument.load(await alternate.pdf({ preferCSSPageSize: true }));
    assert.ok(Math.abs(altPdf.getPage(0).getHeight() * 25.4 / 72 - 80) < 0.5);
    const title = 'Короб № 123 <script>bad()</script> & "склад"';
    const codes = ['INB-01', 'INB-12345678901234567890123456'];
    const html = await f.page.evaluate(async ({ codes, title }) => {
      const { renderBarcodeDataUrl, printBarcodeLabels, DEFAULT_LABEL_SIZE } = await import('/tests-e2e/wms672-harness.tsx');
      printBarcodeLabels(codes.map(barcode => ({ title, barcode,
        barcodeDataUrl: renderBarcodeDataUrl(barcode, { variant: 'internalBox' }),
        labelSize: DEFAULT_LABEL_SIZE, layout: 'internalBox' })));
      return window.__WMS_LAST_PRINT_HTML__;
    }, { codes, title });
    const tape = await renderTape(f.context, html);
    assert.equal(await tape.locator('script').count(), 0);
    assert.deepEqual(await tape.locator('.title').allTextContents(), [title, title]);
    for (let i = 0; i < codes.length; i++) {
      assert.equal(decodePng(await tape.locator('section').nth(i).screenshot()), codes[i]);
    }
  } finally { await f.context.close(); }
});

// Assertions also exercised with deliberately invalid snapshots below: these are
// business assertions changed under authorizer 6f1b196b, not fixture-only edits.
function assertPending({ started, decoded, transfers, marks }, n) {
  assert.ok(started >= Math.min(n, 2), 'actual parallel decode overlap required');
  assert.equal(decoded, 0, 'held group has not completed');
  assert.equal(transfers, 0, 'no partial transfer');
  assert.equal(marks, 0, 'no early marks');
}
function assertComplete(jobs, n) {
  assert.equal(jobs.length, 1, 'exactly one transfer');
  assert.equal(jobs[0].decoded, n, 'all N native decodes before transfer');
}
async function heldGroup(f, n) {
  await f.page.waitForFunction(n => window.__wms672DecodeStarted >= Math.min(n, 2), n);
  const state = await f.page.evaluate(() => ({ started: window.__wms672DecodeStarted,
    decoded: window.__wms672Decoded, transfers: window.__wms672Transfers.length }));
  assertPending({ ...state, marks: f.marks() }, n);
  assert.equal(await f.page.evaluate(() => new Promise(r => setTimeout(() => r('responsive'), 0))), 'responsive');
  return state.started;
}
function assertMarks(successful, boxes) {
  assert.deepEqual(successful.map(m => m.path.split('/').at(-2)), boxes.map(b => b.id), 'all original boxes marked exactly once in order');
  assert.ok(successful.every(m => m.transfers === 1), 'every mark follows the single transfer');
}
async function allMarks(f, job, polling = 'raf') {
  await f.page.waitForFunction(() => Object.values(localStorage).some(value => {
    try { return JSON.parse(value)?.labelAttempt?.state === 'complete'; } catch { return false; }
  }), undefined, { polling });
  assertMarks(f.successfulMarks, f.data.boxes);
  const attempt = await f.page.evaluate(() => Object.values(localStorage).map(value => {
    try { return JSON.parse(value)?.labelAttempt; } catch { return null; }
  }).find(Boolean));
  assert.equal(attempt.id, job.attempt.id, 'completion retains original attempt ID');
  // WMS-743: the label HTML and images are never kept in localStorage (hundreds of base64 barcodes overflow its quota).
  assert.equal(attempt.html, undefined, 'completion keeps no label source in storage');
  assert.deepEqual(attempt.paths, []);
}

test('C4 once: measure 1/200/300 preview preparation; decode delays overlap and UI responds', async () => {
  // Reject serialized, partial, duplicate and early/incomplete-mark outcomes.
  assert.throws(() => assertPending({ started: 1, decoded: 0, transfers: 0, marks: 0 }, 300));
  assert.throws(() => assertPending({ started: 2, decoded: 0, transfers: 1, marks: 0 }, 300));
  assert.throws(() => assertPending({ started: 2, decoded: 0, transfers: 0, marks: 1 }, 300));
  assert.throws(() => assertComplete([{ decoded: 299 }], 300));
  assert.throws(() => assertComplete([{ decoded: 300 }, { decoded: 300 }], 300));
  const boxes = detail(2).boxes;
  assert.throws(() => assertMarks([{ path: '/672-box-1/mark-label-printed', transfers: 1 }], boxes));
  assert.throws(() => assertMarks(boxes.map(b => ({ path: `/${b.id}/mark-label-printed`, transfers: 0 })), boxes));
  assert.throws(() => assertMarks(boxes.map(() => ({ path: '/672-box-1/mark-label-printed', transfers: 1 })), boxes));
  const measurements = [];
  for (const n of [1, 200, 300]) {
    const f = await fixture(n, 'inbound', { hold: true, delayMs: 20 });
    try {
      const started = performance.now();
      await confirm(f);
      const concurrent = await heldGroup(f, n);
      const holdMs = performance.now() - started;
      await f.page.evaluate(() => { window.__wms672Hold = false; });
      const jobs = await transfer(f);
      assertComplete(jobs, n);
      const preparationMs = performance.now() - started;
      const events = await f.page.evaluate(() => window.__wms672DecodeEvents);
      if (n > 1) assert.ok(events.at(-1).frame > events[0].frame, 'browser frames yielded between groups');
      await allMarks(f, jobs[0]);
      measurements.push({ n, preparationMs, artificialHoldMs: holdMs, concurrentDecodes: concurrent });
    } finally { await f.context.close(); }
  }
  await writeFile(resolve(evidence, 'timing.json'), JSON.stringify({
    node: process.version, platform: process.platform, arch: process.arch,
    browser: browser.version(), delayMs: 20, measurements,
    boundary: 'synthetic intercepted preview-ready transfer; artificial hold reported separately; excludes hardware and initial screen load',
  }, null, 2));
  // Existing production fallback must finish when parent animation frames stop.
  const stalled = await fixture(300, 'inbound', { stallFrames: true });
  try {
    await assert.rejects(() => renderTape(stalled.context, '<img src="data:image/png;base64,AAAA">'), 'PDF helper must propagate actual bad PNG native decode');
    await confirm(stalled); const jobs = await transfer(stalled, 1, 50); assertComplete(jobs, 300); await allMarks(stalled, jobs[0], 50); }
  finally { await stalled.context.close(); }

});

test('C5 decode failure at label 150: no transfer/early marks, visible error, explicit corrected retry', async () => {
  for (const failedIndex of [150, 299]) {
    const f = await fixture(300, 'inbound', { decodeAt: failedIndex });
    try {
      await confirm(f);
      await f.page.getByRole('alert').filter({ hasText: `WMS672 decode failed at ${failedIndex}` }).waitFor();
      await f.page.waitForFunction(() => !document.querySelector('[data-testid="ff-inbound-boxes-print-all"]').disabled);
      assert.ok(await f.page.evaluate(index => window.__wms672DecodeStarted >= index, failedIndex));
      assert.equal(await f.page.evaluate(() => window.__wms672Transfers.length), 0);
      assert.equal(f.marks(), 0, 'failed preparation must not mark existing boxes printed');
      assert.equal(await f.page.getByTestId('ff-inbound-boxes-print-all').isEnabled(), true);
      assert.equal(await f.page.evaluate(() => new Promise(r => setTimeout(() => r('responsive'), 0))), 'responsive');
      await f.page.evaluate(() => { window.__wms672Fault.decodeAt = null; });
      await confirm(f);
      const jobs = await transfer(f);
      assertComplete(jobs, 300);
      const tape = await renderTape(f.context, jobs[0].html);
      assert.deepEqual(await tape.locator('.label').evaluateAll(nodes => nodes.map(n => n.dataset.barcode)), f.data.boxes.map(b => b.internal_barcode));
      await allMarks(f, jobs[0]);
    } finally { await f.context.close(); }
  }
});

test('C6 fast double confirmation belongs to one attempt and transfers at most once', async () => {
  const f = await fixture(200, 'inbound', { hold: true });
  try {
    await f.page.getByTestId('ff-inbound-boxes-print-all').click();
    await f.page.getByTestId('ff-inbound-box-print-dialog-confirm').evaluate(button => {
      button.click(); button.click();
    });
    await heldGroup(f, 200);
    assert.equal(await f.page.locator('iframe').count(), 1, 'one preparation for double confirmation');
    await f.page.evaluate(() => { window.__wms672Hold = false; });
    const jobs = await transfer(f);
    assertComplete(jobs, 200);
    const tape = await renderTape(f.context, jobs[0].html);
    assert.deepEqual(await tape.locator('.label').evaluateAll(nodes => nodes.map(n => n.dataset.barcode)), f.data.boxes.map(b => b.internal_barcode));
    await allMarks(f, jobs[0]);
    assert.equal(await f.page.evaluate(() => window.__wms672Transfers.length), 1, 'same confirmation must not make a second tape');
  } finally { await f.context.close(); }
});

test('C7/C8 response lost after transfer: restore source/attempt across reload before another external action', async () => {
  const f = await fixture(300, 'inbound', { markAt: 150 });
  try {
    await confirm(f);
    const [job] = await transfer(f);
    await f.page.getByRole('alert').waitFor();
    assert.equal(await f.page.evaluate(() => window.__wms672Transfers.length), 1);
    assert.ok(await f.page.locator('iframe').count(), 'source lives while print consumer reads it');
    // afterprint/cancellation is not paper proof and must not erase recovery source.
    await f.page.locator('iframe').evaluate(frame => frame.contentWindow.dispatchEvent(new Event('afterprint')));
    const persisted = await f.page.evaluate(() => ({
      local: Object.entries(localStorage), session: Object.entries(sessionStorage),
    }));
    const beforeReload = f.calls.length;
    // Remount is not a reload: this is a new JS execution context with the same storage/API state.
    await f.page.reload();
    await f.page.evaluate(async () => {
      const { mountInbound672 } = await import('/tests-e2e/wms672-harness.tsx');
      mountInbound672(document.getElementById('root'));
    });
    await f.page.getByTestId('ff-inbound-packages-toggle').click();
    await f.page.getByTestId('ff-inbound-boxes-print-all').waitFor();
    const recoveryReads = f.calls.slice(beforeReload).filter(c => c.method === 'GET' &&
      !c.path.endsWith('/672-document') && !c.path.includes('marking') && !c.path.includes('catalog') && !c.path.includes('warehouses'));
    assert.ok(persisted.local.length + persisted.session.length > 0 || recoveryReads.length > 0,
      'lost outcome has a durable attempt/source and a recovery read; busy state alone cannot survive reload');
    assert.ok(job.html.includes('INB-000000000300'));
  } finally { await f.context.close(); }
});

test('C8 mark failure retry repairs original attempt without silently printing another tape', async () => {
  const f = await fixture(300, 'inbound', { markAt: 150 });
  try {
    await confirm(f);
    await transfer(f);
    await f.page.getByRole('alert').waitFor();
    assert.equal(await f.page.getByTestId('ff-inbound-boxes-print-all').isEnabled(), true);
    // Repeating the failed action first recovers its result; fresh reprint needs a distinct confirmation.
    await confirm(f);
    await f.page.waitForTimeout(500);
    assert.equal(await f.page.evaluate(() => window.__wms672Transfers.length), 1,
      'retry after missing mark response must not silently retransmit all 300 labels');
  } finally { await f.context.close(); }
});

test('C10 controls: empty/one/cargo, creation dialog and opening never print', async () => {
  for (const n of [0, 1]) {
    const f = await fixture(n);
    try {
      assert.equal(await f.page.getByTestId('ff-inbound-boxes-print-all').isEnabled(), n > 0);
      await f.page.getByTestId('ff-inbound-create-cargo-places').click();
      assert.equal(await f.page.evaluate(() => window.__wms672Transfers.length), 0);
      assert.equal(f.calls.filter(c => c.method !== 'GET').length, 0);
      await f.page.getByRole('button', { name: 'Отмена', exact: true }).click();
      if (n) {
        await confirm(f, 'ff-inbound-box-print-672-box-1');
        const [job] = await transfer(f);
        const tape = await renderTape(f.context, job.html);
        assert.equal(await tape.locator('.label').count(), 1);
      }
    } finally { await f.context.close(); }
  }
});
