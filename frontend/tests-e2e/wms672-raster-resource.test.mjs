// Additive WMS-672 R3/R4/R6 lifecycle contract. Actual utility, controlled
// decode/raster boundary: this is not a Chromium, PDF or physical-print proof.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {test} from 'node:test';

const require = createRequire(new URL('../package.json', import.meta.url));
const {JSDOM} = require('jsdom');
const ts = require('typescript');
const source = readFileSync(new URL('../src/utils/printBarcodeLabel.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}}).outputText;
const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aBVcAAAAASUVORK5CYII=';
const flush = async () => {for (let i = 0; i < 4; i++) await new Promise(setImmediate);};
const length = (value, reference, fallback) => {
  if (/^-?[\d.]+px$/.test(value)) return Number.parseFloat(value);
  if (/^-?[\d.]+mm$/.test(value)) return Number.parseFloat(value) * 96 / 25.4;
  if (/^-?[\d.]+%$/.test(value)) return Number.parseFloat(value) * reference / 100;
  if (value === '0') return 0;
  return fallback;
};
const overlap = (a, b) => a.x < b.x + b.width && b.x < a.x + a.width
  && a.y < b.y + b.height && b.y < a.y + a.height;

function fixture({bounded = false, stallFrames = false, refusal = false} = {}) {
  const dom = new JSDOM('<body></body>', {url: 'https://synthetic.wms.test/',
    runScripts: 'dangerously', pretendToBeVisual: true});
  const w = dom.window;
  const labels = Array.from({length: 300}, (_, i) => ({title: `Короб ${i + 1} <&>`,
    barcode: `INB-${String(i + 1).padStart(12, '0')}`, barcodeDataUrl: png,
    layout: 'internalBox', labelSize: {id: '58x40', widthMm: 58, heightMm: 40}}));
  const state = {started: 0, ready: 0, pending: 0, maxPending: 0, peakRetained: 0,
    retained: new Set(), releases: 0, boundaries: [], violations: [], saves: [],
    transfers: [], cleanup: [], finished: false, nativeError: null, fallbackTurns: 0};
  let frame, fw, images, originalHTML, originalStyles;
  // The established zero-geometry style from product478. Preparation may begin
  // before append; taking a new snapshot there would bless temporary geometry.
  const originalFrameStyle = 'position: fixed; right: 0px; bottom: 0px; width: 0px; height: 0px; border: 0px;';
  let capacity;
  let release;
  const held = new Promise(resolve => {release = resolve;});
  const exports = {};
  w.exports = exports;
  w.eval(compiled);

  // jsdom has no layout engine. This boundary resolves declared px/mm/% boxes,
  // absolute/fixed positioning and ordinary block flow, independent of helper
  // names or thumbnail/cohort sizes. Real browser coverage remains mandatory.
  function rect(element) {
    const view = element.ownerDocument.defaultView;
    const style = view.getComputedStyle(element);
    const viewport = element.ownerDocument === w.document
      ? {x: 0, y: 0, width: w.innerWidth, height: w.innerHeight}
      : {...rect(frame), x: 0, y: 0};
    const root = !element.parentElement || element.tagName === 'HTML';
    const parent = root ? viewport : rect(element.parentElement);
    const width = length(style.width, parent.width, element.tagName === 'IMG' ? 836 : parent.width);
    const height = length(style.height, parent.height, element.tagName === 'IMG' ? width * 356 / 836 : 0);
    let base = parent;
    const positioned = ['absolute', 'fixed'].includes(style.position);
    if (style.position === 'fixed') base = viewport;
    if (style.position === 'absolute') {
      let ancestor = element.parentElement;
      while (ancestor && ['', 'static'].includes(view.getComputedStyle(ancestor).position)) ancestor = ancestor.parentElement;
      base = ancestor ? rect(ancestor) : viewport;
    }
    const x = base.x + length(style.left, base.width,
      positioned && style.right && style.right !== 'auto' ? base.width - width - length(style.right, base.width, 0) : 0);
    const y = base.y + length(style.top, base.height,
      positioned && style.bottom && style.bottom !== 'auto' ? base.height - height - length(style.bottom, base.height, 0)
        : !positioned && element.previousElementSibling ? rect(element.previousElementSibling).y - base.y + rect(element.previousElementSibling).height : 0);
    return {x, y, width, height};
  }
  function visible(element) {
    for (let node = element; node; node = node.parentElement) {
      const s = node.ownerDocument.defaultView.getComputedStyle(node);
      if (node.hidden || s.display === 'none' || ['hidden', 'collapse'].includes(s.visibility)
        || (s.opacity !== '' && Number(s.opacity) === 0) || s.contentVisibility === 'hidden') return false;
    }
    return true;
  }
  function rasterBoundary() {
    if (!images || !state.retained.size || state.pending) return;
    const f = rect(frame);
    const problems = [];
    if (!visible(frame) || f.width <= 0 || f.height <= 0 || f.x < 0 || f.y < 0
      || f.x + f.width > w.innerWidth || f.y + f.height > w.innerHeight) problems.push('print iframe has no nonzero in-viewport raster geometry');
    if (frame.getAttribute('aria-hidden') !== 'true' || w.getComputedStyle(frame).pointerEvents !== 'none') problems.push('preparation frame is not aria-hidden and pointer-inert');
    const eligible = f.width > 0 && f.height > 0 && visible(frame) ? images.filter(image => {
      if (!visible(image)) return false;
      const r = rect(image);
      return r.width > 0 && r.height > 0 && r.x >= 0 && r.y >= 0
        && r.x + r.width <= f.width && r.y + r.height <= f.height;
    }) : [];
    if (eligible.length !== state.retained.size || eligible.some(image => !state.retained.has(image))) problems.push('only the original decoded cohort must be raster-eligible');
    const boxes = eligible.map(rect);
    if (boxes.some(r => r.width >= 836 || r.height >= 356)) problems.push('preparation must permit a smaller scaled image key');
    if (eligible.some(image => !['', 'auto'].includes(fw.getComputedStyle(image).imageRendering))) problems.push('pixelated/nearest-neighbor filtering retains the original full image key');
    if (boxes.some((a, i) => boxes.slice(i + 1).some(b => overlap(a, b)))) problems.push('preparation thumbnails overlap');
    state.boundaries.push({ready: state.ready, retained: state.retained.size, eligible: eligible.length, problems});
    if (problems.length) state.violations.push(...problems);
    else {state.releases += state.retained.size; state.retained.clear();}
  }

  const rafs = new Map();
  let rafId = 0;
  w.requestAnimationFrame = callback => {
    const id = ++rafId;
    if (!stallFrames) rafs.set(id, setImmediate(() => {
      rafs.delete(id); rasterBoundary(); callback(w.performance.now());
    }));
    return id;
  };
  w.cancelAnimationFrame = id => {clearImmediate(rafs.get(id)); rafs.delete(id);};
  if (stallFrames) {
    // Deliver timers as tasks without a wall-clock wait. No fake raster release:
    // this preservation case tests fallback completion, not engine capacity.
    w.setTimeout = callback => setImmediate(() => {state.fallbackTurns++; callback();});
    w.clearTimeout = clearImmediate;
  }
  const snapshot = () => ({frameStyle: frame.getAttribute('style'),
    styles: originalStyles.map(([element]) => element.getAttribute('style')),
    sources: images.map(image => image.getAttribute('src')), html: frame.srcdoc,
    sheet: fw.document.querySelector('style').textContent, pending: state.pending});
  const append = w.document.body.appendChild.bind(w.document.body);
  w.document.body.appendChild = node => {
    const result = append(node);
    if (node.tagName === 'IFRAME') frame = node;
    return result;
  };
  const remove = w.document.body.removeChild.bind(w.document.body);
  w.document.body.removeChild = node => {
    if (node === frame) state.cleanup.push(snapshot());
    return remove(node);
  };
  const operation = exports.printBarcodeLabels(labels, {beforeTransfer: html => {
    state.saves.push({html, ready: state.ready, snapshot: snapshot()});
  }}).then(() => {state.finished = true; return {error: null};}, error => {
    state.finished = true; return {error};
  });
  assert.ok(frame, 'actual utility creates the print iframe');
  originalHTML = frame.srcdoc;
  const onload = frame.onload;
  frame.onload = null; // jsdom cannot navigate srcdoc: deliver real utility HTML once.
  frame.contentDocument.open(); frame.contentDocument.write(originalHTML); frame.contentDocument.close();
  fw = frame.contentWindow;
  images = [...fw.document.querySelectorAll('img.barcode')];
  assert.equal(images.length, 300);
  originalStyles = [...fw.document.querySelectorAll('*')].map(element => [element, element.getAttribute('style')]);
  const originalSheet = fw.document.querySelector('style').textContent;
  for (const view of [w, fw]) view.Element.prototype.getBoundingClientRect = function () {
    const r = rect(this); return {...r, left: r.x, top: r.y, right: r.x + r.width, bottom: r.y + r.height, toJSON: () => r};
  };
  Object.defineProperties(fw.HTMLImageElement.prototype, {
    naturalWidth: {configurable: true, get: () => 836},
    naturalHeight: {configurable: true, get: () => 356},
    decode: {configurable: true, value: async function () {
      assert.ok(images.includes(this), 'decode executes on an original tape image, not a thumbnail copy');
      const index = ++state.started;
      if (state.pending === 0 && state.retained.size) state.violations.push('next cohort starts before prior successful images are raster-consumed');
      state.pending++; state.maxPending = Math.max(state.maxPending, state.pending);
      if (refusal && index !== 2) await held;
      else await Promise.resolve();
      capacity ??= state.started; // synthetic budget: one actual initial parallel cohort, not a Chrome quota.
      state.pending--;
      if ((refusal && index === 2) || (bounded && state.retained.size >= capacity)) {
        const error = new fw.DOMException('The source image cannot be decoded.', 'EncodingError');
        state.nativeError ??= error;
        throw error;
      }
      state.ready++; state.retained.add(this);
      state.peakRetained = Math.max(state.peakRetained, state.retained.size);
    }},
  });
  fw.focus = () => {};
  fw.print = () => state.transfers.push({ready: state.ready, snapshot: snapshot()});
  onload.call(frame, new fw.Event('load'));
  function assertOriginal(s) {
    assert.equal(s.frameStyle, originalFrameStyle, 'restore exact zero-geometry iframe inline style');
    const leakedStyles = originalStyles.flatMap(([element, style], index) => s.styles[index] === style
      ? [] : [{index, tag: element.tagName, expected: style, actual: s.styles[index]}]);
    assert.deepEqual(leakedStyles, [], 'restore every original inline style exactly');
    assert.deepEqual(s.sources, labels.map(label => label.barcodeDataUrl), 'original source PNGs survive preparation');
    assert.equal(s.html, originalHTML, 'retain the exact full source HTML');
    assert.equal(s.sheet, originalSheet, 'physical page and pixelated print CSS are unchanged');
  }
  return {state, frame, fw, labels, operation, release, assertOriginal, originalHTML,
    close: () => {release(); for (const handle of rafs.values()) clearImmediate(handle); dom.window.close();}};
}

test('RR1 R3/R4 decoded original cohorts raster-consume retained resources before later decode; all 300 precede one transfer', async context => {
  const f = fixture({bounded: true});
  try {
    const outcome = await f.operation;
    context.diagnostic(JSON.stringify({started: f.state.started, ready: f.state.ready,
      maxPending: f.state.maxPending, peakRetained: f.state.peakRetained, releases: f.state.releases,
      firstBoundary: f.state.boundaries[0], violations: [...new Set(f.state.violations)],
      transfers: f.state.transfers.length, error: outcome.error?.message}));
    assert.equal(f.state.ready, 300, 'all 300 require raster consumption of earlier original decodes; waiting frames with an ineligible zero-size iframe accumulates retained resources');
    assert.equal(outcome.error, null);
    assert.ok(f.state.maxPending >= 2, 'native readiness remains parallel');
    assert.ok(f.state.peakRetained < 300, 'preparation does not retain the entire tape');
    assert.ok(f.state.releases > 0, 'render consumption actually releases modeled original-key locks');
    assert.deepEqual(f.state.violations, []);
    assert.equal(f.state.saves.length, 1); assert.equal(f.state.transfers.length, 1);
    for (const event of [...f.state.saves, ...f.state.transfers]) {
      assert.equal(event.ready, 300, 'no durable source/transfer before every successful decode');
      f.assertOriginal(event.snapshot);
    }
  } finally {f.close();}
});

test('RR2 R4/R6 stalled parent frames still complete 300 native decodes and restore exact original tape before one handoff', async () => {
  const f = fixture({stallFrames: true});
  try {
    assert.equal((await f.operation).error, null);
    assert.equal(f.state.started, 300); assert.equal(f.state.ready, 300);
    assert.ok(f.state.maxPending >= 2); assert.ok(f.state.fallbackTurns > 0);
    assert.equal(f.state.saves.length, 1); assert.equal(f.state.transfers.length, 1);
    assert.equal(f.state.saves[0].html, f.originalHTML);
    for (const event of [...f.state.saves, ...f.state.transfers]) {
      assert.equal(event.ready, 300); f.assertOriginal(event.snapshot);
    }
    const doc = new f.fw.DOMParser().parseFromString(f.originalHTML, 'text/html');
    assert.deepEqual([...doc.querySelectorAll('.label')].map(node => node.dataset.barcode), f.labels.map(label => label.barcode));
    assert.deepEqual([...doc.querySelectorAll('.title')].map(node => node.textContent), f.labels.map(label => label.title));
    assert.match(doc.querySelector('style').textContent, /@page\s*\{\s*size:\s*58mm 40mm;/);
    assert.match(doc.querySelector('style').textContent, /image-rendering:\s*pixelated/);
    assert.equal(f.frame.isConnected, true, 'full source lives for the print consumer until afterprint');
    f.fw.dispatchEvent(new f.fw.Event('afterprint'));
    assert.equal(f.state.cleanup.length, 1); f.assertOriginal(f.state.cleanup[0]);
    assert.equal(f.frame.isConnected, false);
  } finally {f.close();}
});

test('RR3 R4/R6 native refusal drains every started peer and restores original styles/source before cleanup with same reason and zero handoff', async context => {
  const f = fixture({refusal: true});
  try {
    await flush();
    assert.ok(f.state.nativeError instanceof f.fw.DOMException);
    assert.ok(f.state.pending > 0, 'real started peers are held independently of native refusal');
    const held = {connected: f.frame.isConnected, finished: f.state.finished,
      cleanup: f.state.cleanup.length, started: f.state.started};
    f.release();
    const outcome = await f.operation;
    context.diagnostic(JSON.stringify({held, afterDrain: {pending: f.state.pending, ready: f.state.ready,
      started: f.state.started, saves: f.state.saves.length, transfers: f.state.transfers.length}}));
    assert.deepEqual(held, {connected: true, finished: false, cleanup: 0, started: f.state.started}, 'no teardown or new cohort while failed preparation still has active peers');
    assert.equal(outcome.error, f.state.nativeError, 'original EncodingError object and reason survive drain');
    assert.equal(outcome.error.message, 'The source image cannot be decoded.');
    assert.equal(f.state.pending, 0); assert.equal(f.state.ready, f.state.started - 1);
    assert.deepEqual(f.state.saves, []); assert.deepEqual(f.state.transfers, []);
    assert.equal(f.state.cleanup.length, 1); assert.equal(f.state.cleanup[0].pending, 0);
    f.assertOriginal(f.state.cleanup[0]);
    assert.equal(f.frame.isConnected, false);
  } finally {f.release(); await f.operation; f.close();}
});
