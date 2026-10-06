// Isolated synthetic controller test, no real browser/renderer/platform claim.
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { gzipSync } from 'node:zlib';
const dir = await mkdtemp(resolve(tmpdir(), 'wms672-owned-collector-control-'));
const calls = [], listeners = new Map(), contexts = [];
const cdp = {
  on(name, fn) { listeners.set(name, fn); },
  once(name, fn) { listeners.set(name, fn); },
  async send(name, args) {
    calls.push({ name, args, time: Date.now() });
    if (name === 'Tracing.getCategories') return { categories: ['disabled-by-default-cc.debug', 'disabled-by-default-memory-infra', '__metadata'] };
    if (name === 'SystemInfo.getInfo') return { synthetic: true };
    if (name === 'Tracing.requestMemoryDump') return { success: true, dumpGuid: 'synthetic' };
    if (name === 'Tracing.end') queueMicrotask(() => listeners.get('Tracing.tracingComplete')({ stream: 'synthetic', dataLossOccurred: false }));
    if (name === 'IO.read') return { data: gzipSync(JSON.stringify({ traceEvents: [] })).toString('base64'), base64Encoded: true, eof: true };
    return {};
  },
};
const browser = {
  version: () => '141.0.7390.37',
  async newBrowserCDPSession() { return cdp; },
  async newContext() {
    const handlers = new Map();
    const context = { async route() {}, on(name, fn) { handlers.set(name, fn); }, async addInitScript(fn, arg) { this.init = fn; this.initArg = arg; }, pages: () => [], async close() {}, handlers };
    contexts.push(context); return context;
  },
  async close() {},
};
globalThis.__wms672MockChromium = { async launch() { return browser; } };
const modulePath = resolve(dir, 'mock-playwright.mjs');
await writeFile(modulePath, 'export const chromium = globalThis.__wms672MockChromium;');
Object.defineProperty(process, 'platform', { value: 'linux' });
process.env.GITHUB_ACTIONS = 'true';
process.env.PLAYWRIGHT_MODULE = pathToFileURL(modulePath).href;
process.env.WMS672_EVIDENCE_DIR = resolve(dir, 'evidence');
process.env.WMS672_TEST_URL = 'http://127.0.0.1:16724';
await import(pathToFileURL(resolve('scripts/ci/wms672-c5-diagnostic/adapter.mjs')).href);
const wrapped = await globalThis.__wms672MockChromium.launch();
await wrapped.newContext();
assert.equal(calls.filter(x => x.name === 'Tracing.start').length, 0, 'first150 fixture is untraced');
const second = await wrapped.newContext();
assert.equal(calls.filter(x => x.name === 'Tracing.start').length, 1);
assert.equal(calls.find(x => x.name === 'Tracing.start').args.traceConfig.traceBufferSizeInKb, 65536);
assert.equal(calls.filter(x => x.name === 'Tracing.requestMemoryDump').length, 1, 'initial cache baseline dump');
let message;
second.handlers.get('page')({ on(name, fn) { if (name === 'console') message = fn; } });
message({ text: () => 'WMS672 decode failed at 299' });
await new Promise(resolve => setTimeout(resolve, 20));
assert.equal(calls.filter(x => x.name === 'Tracing.end').length, 0, 'synthetic299 reason cannot stop collector');
const start = Date.now();
message({ text: () => '__WMS672_NATIVE_REFUSAL__ {"index":532,"nativeFrameId":5}' });
message({ text: () => '__WMS672_NATIVE_REFUSAL__ {"index":533,"nativeFrameId":5}' });
await new Promise(resolve => setTimeout(resolve, 1150));
assert.equal(calls.filter(x => x.name === 'Tracing.end').length, 1, 'one stop despite peer failures');
const elapsed = calls.find(x => x.name === 'Tracing.end').time - start;
assert(elapsed >= 950 && elapsed < 1500, `one second release tail, actual ${elapsed}`);
await second.close();
await wrapped.close();
assert.equal(calls.filter(x => x.name === 'Tracing.end').length, 1, 'context/browser close do not duplicate stop');
const completion = JSON.parse(await readFile(resolve(dir, 'evidence/engine/trace-completion.json'), 'utf8'));
assert.equal(completion.reason, 'native-failure-plus-1s');
assert.equal(completion.dataLossOccurred, false);
const oldCatch = Promise.prototype.catch, oldInfo = console.info;
class FakeImage { constructor() { this.src = 'synthetic-source'; this.complete = true; this.naturalWidth = 836; this.naturalHeight = 356; this.outerHTML = '<img class=barcode>'; } matches() { return true; } decode() { return Promise.reject(globalThis.__sentinel); } }
class FakeNode { removeChild(child) { return child; } }
globalThis.window = { Error, __wms672DecodeStarted: 532 }; window.top = window;
globalThis.document = { visibilityState: 'visible' };
globalThis.HTMLImageElement = FakeImage; globalThis.Node = FakeNode;
second.init(second.initArg);
console.info = () => { throw new Error('collector console failed'); };
globalThis.__sentinel = Object.assign(new Error('native original'), { name: 'EncodingError' });
try { await assert.rejects(new FakeImage().decode(), error => error === globalThis.__sentinel, 'observer failure preserves original error'); }
finally { console.info = oldInfo; Promise.prototype.catch = oldCatch; }
console.log(JSON.stringify({ synthetic: true, firstFixtureTraceStarts: 0, secondFixtureTraceStarts: 1, synthetic299Stops: 0, genuineFailureStops: 1, releaseTailMs: elapsed, initialLightDump: 1, duplicateStop: 0, originalErrorPreservedIfConsoleThrows: true }, null, 2));
