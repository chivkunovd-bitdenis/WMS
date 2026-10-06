// Diagnostic observer: rethrow original errors, keep frozen contract unchanged.
import { mkdir, writeFile, open } from 'node:fs/promises';
import { resolve } from 'node:path';
if (process.env.GITHUB_ACTIONS !== 'true' || process.platform !== 'linux') throw new Error('Linux Actions only');
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE);
const launch = chromium.launch.bind(chromium);
let fixture = 0;
chromium.launch = async (options = {}) => {
  const browser = await launch({ ...options, args: [...(options.args || []), '--mute-audio'] });
  if (browser.version() !== '141.0.7390.37') throw new Error(`Wrong diagnostic browser ${browser.version()}`);
  console.log('C5 environment', JSON.stringify({ node: process.version, platform: process.platform, arch: process.arch, browser: browser.version() }));
  // Capture only fixture2, before its page creates the target cache.
  // Collector timing/streaming is asynchronous and never awaited by native decode.
  const traceDir = resolve(process.env.WMS672_EVIDENCE_DIR, 'engine');
  await mkdir(traceDir, { recursive: true });
  const cdp = await browser.newBrowserCDPSession();
  const includedCategories = ['disabled-by-default-cc.debug', 'disabled-by-default-memory-infra', '__metadata'];
  await writeFile(resolve(traceDir, 'system-info.json'), JSON.stringify(await cdp.send('SystemInfo.getInfo'), null, 2));
  const config = {
    transferMode: 'ReturnAsStream', streamFormat: 'json', streamCompression: 'gzip',
    bufferUsageReportingInterval: 1000,
    traceConfig: {
      recordMode: 'recordUntilFull', traceBufferSizeInKb: 65536,
      enableSampling: false, enableSystrace: false,
      includedCategories, excludedCategories: ['*'],
      memoryDumpConfig: { allowed_dump_modes: ['light'], triggers: [{ periodic_interval_ms: 250, mode: 'light' }] },
    },
  };
  await writeFile(resolve(traceDir, 'trace-config.json'), JSON.stringify(config, null, 2));
  const usage = [], clockSamples = [];
  let tracing = false, stopPromise, stopTimer, failureNotice;
  cdp.on('Tracing.bufferUsage', event => usage.push(event));
  const completed = new Promise(resolveTrace => cdp.once('Tracing.tracingComplete', resolveTrace));
  const syncClock = async label => {
    if (!tracing) return;
    const syncId = `C5-clock-${label}-${clockSamples.length}`;
    const epochBeforeMs = Date.now();
    await cdp.send('Tracing.recordClockSyncMarker', { syncId });
    clockSamples.push({ syncId, epochBeforeMs, epochAfterMs: Date.now() });
  };
  const startTrace = async () => {
    await writeFile(resolve(traceDir, 'categories.json'), JSON.stringify(await cdp.send('Tracing.getCategories'), null, 2));
    await cdp.send('Tracing.start', config);
    tracing = true;
    await syncClock('fixture-2-trace-start');
    // Numeric initial baseline, no deterministic/forced-GC option.
    await writeFile(resolve(traceDir, 'initial-memory-dump.json'), JSON.stringify(await cdp.send('Tracing.requestMemoryDump', { levelOfDetail: 'light' }), null, 2));
  };
  const stopTrace = reason => {
    if (stopPromise) return stopPromise;
    stopPromise = (async () => {
      clearTimeout(stopTimer);
      const stopRequestedEpochMs = Date.now();
      await syncClock('fixture-2-trace-end');
      await writeFile(resolve(traceDir, 'clock-sync.json'), JSON.stringify(clockSamples, null, 2));
      await writeFile(resolve(traceDir, 'categories-after.json'), JSON.stringify(await cdp.send('Tracing.getCategories'), null, 2));
      await cdp.send('Tracing.end');
      tracing = false;
      let traceDeadline;
      const completion = await Promise.race([completed, new Promise((_, reject) => { traceDeadline = setTimeout(() => reject(new Error('Trace completion exceeded15s')), 15000); })]).finally(() => clearTimeout(traceDeadline));
      await writeFile(resolve(traceDir, 'trace-completion.json'), JSON.stringify({ ...completion, usage, reason, failureNotice, stopRequestedEpochMs }, null, 2));
      if (!completion.stream) throw new Error('Engine trace did not return stream');
      const output = await open(resolve(traceDir, 'trace.json.gz'), 'w');
      let bytes = 0;
      try {
        while (true) {
          const chunk = await cdp.send('IO.read', { handle: completion.stream, size: 1048576 });
          const data = Buffer.from(chunk.data, chunk.base64Encoded ? 'base64' : 'utf8');
          bytes += data.length;
          if (bytes > 67108864) throw new Error('Compressed engine trace exceeds64MiB bound');
          await output.write(data);
          if (chunk.eof) break;
        }
      } finally { await output.close(); await cdp.send('IO.close', { handle: completion.stream }); }
      console.log('C5 engine trace', JSON.stringify({ bytes, reason, dataLossOccurred: completion.dataLossOccurred, maxBufferUsage: Math.max(0, ...usage.map(event => event.percentFull || 0)) }));
    })();
    return stopPromise;
  };
  const closeBrowser = browser.close.bind(browser);
  browser.close = async (...args) => {
    try {
      if (stopPromise) await stopPromise;
      else if (tracing) await stopTrace('browser-close');
      else await writeFile(resolve(traceDir, 'capture-not-reached.json'), JSON.stringify({ reason: 'C5 did not reach fixture2; no target trace/cause claim' }));
    } finally { await closeBrowser(...args); }
  };
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async (...args) => {
    const context = await newContext(...args);
    const id = ++fixture;
    if (id === 2) await startTrace();
    context.on('page', page => {
      if (id !== 2) return;
      page.on('console', message => {
        const text = message.text();
        const prefix = '__WMS672_NATIVE_REFUSAL__';
        if (!text.startsWith(prefix) || failureNotice || !tracing) return;
        failureNotice = { text, receivedEpochMs: Date.now() };
        // This observer timer does not delay/await the native failure or the test.
        void syncClock('native-failure-notice').catch(error => console.error('Clock capture:', error.message));
        stopTimer = setTimeout(() => { void stopTrace('native-failure-plus-1s').catch(error => console.error('Trace capture:', error.message)); }, 1000);
      });
    });
    const requests = [];
    await context.route('**/*', route => new URL(route.request().url()).origin === process.env.WMS672_TEST_URL ? route.continue() : route.abort());
    context.on('request', request => requests.push({ method: request.method(), url: request.url() }));
    await context.addInitScript(fixtureId => {
      const root = window.top;
      root.__c5DiagnosticEvents ??= [];
      window.__c5NativeFixtureId = fixtureId;
      root.__c5DiagnosticErrors ??= new WeakMap();
      root.__c5DiagnosticErrorCounter ??= 0;
      root.__c5NativeFrameCounter ??= 0;
      root.__c5NativeTotalPending ??= 0;
      root.__c5NativeFulfilled ??= 0;
      root.__c5NativeRejected ??= 0;
      window.__c5NativeFrameId = ++root.__c5NativeFrameCounter;
      window.__c5NativeFramePending = 0;
      const record = (kind, error, extra = {}) => {
        try {
          let identity = null;
          if (error && (typeof error === 'object' || typeof error === 'function')) {
            if (!root.__c5DiagnosticErrors.has(error)) root.__c5DiagnosticErrors.set(error, ++root.__c5DiagnosticErrorCounter);
            identity = root.__c5DiagnosticErrors.get(error);
          }
          if (root.__c5DiagnosticEvents.length < 5000) root.__c5DiagnosticEvents.push({
            kind, fixtureId, wallTime: performance.timeOrigin + performance.now(), visibility: document.visibilityState, frameStyle: window.frameElement?.getAttribute('style'), nativeFrameId: window.__c5NativeFrameId, nativeFramePending: window.__c5NativeFramePending, nativeTotalPending: root.__c5NativeTotalPending, nativeFulfilled: root.__c5NativeFulfilled, nativeRejected: root.__c5NativeRejected, time: performance.now(), realm: window === root ? 'parent' : 'iframe', identity,
            name: error?.name, message: error?.message, stack: error?.stack,
            localError: error instanceof Error, parentError: error instanceof root.Error,
            started: root.__wms672DecodeStarted, decoded: root.__wms672Decoded,
            decodeAt: root.__wms672Fault?.decodeAt, frames: root.__wms672Frames, ...extra,
          });
        } catch { /* observation must not alter product outcome */ }
      };
      window.__wms672DiagnosticRecord = record;
      const nativeDecode = HTMLImageElement.prototype.decode;
      HTMLImageElement.prototype.decode = function (...args) {
        const image = this;
        const index = root.__wms672DecodeStarted;
        const tracked = image.matches('img.barcode');
        if (tracked) {
          window.__c5NativeFramePending++; root.__c5NativeTotalPending++;
          record('native-start', null, { index, complete: image.complete, width: image.naturalWidth, height: image.naturalHeight, srcLength: image.src.length });
        }
        const finish = success => {
          try {
            if (!tracked) return;
            window.__c5NativeFramePending--; root.__c5NativeTotalPending--;
            if (success) root.__c5NativeFulfilled++; else root.__c5NativeRejected++;
            if (window.__c5NativeFramePending === 0) record('native-cohort-settled', null, { index });
          } catch { /* observation must not change native completion */ }
        };
        const reject = (error, synchronous = false) => {
          finish(false);
          record('native-reject', error, { index, synchronous, complete: image.complete, width: image.naturalWidth, height: image.naturalHeight, src: image.src, outerHTML: image.outerHTML });
          try {
            if (fixtureId === 2 && !root.__c5NativeTraceFailureNotice) {
              root.__c5NativeTraceFailureNotice = true;
              console.info('__WMS672_NATIVE_REFUSAL__', JSON.stringify({ index, nativeFrameId: window.__c5NativeFrameId, wallTime: performance.timeOrigin + performance.now() }));
            }
          } catch { /* collector notification must never replace the original native error */ }
          throw error;
        };
        let decoded;
        try { decoded = nativeDecode.apply(image, args); } catch (error) { return reject(error, true); }
        return decoded.then(value => { finish(true); return value; }, error => reject(error));
      };
      const originalCatch = Promise.prototype.catch;
      Promise.prototype.catch = function (handler) {
        if (typeof handler !== 'function') return originalCatch.call(this, handler);
        return originalCatch.call(this, error => { record('promise-catch', error); return handler(error); });
      };
      if (window === root) {
        const remove = Node.prototype.removeChild;
        Node.prototype.removeChild = function (child) {
          if (child.tagName === 'IFRAME') record('iframe-remove', null, { srcdoc: child.srcdoc, transfers: root.__wms672Transfers?.length, removedFrameId: child.contentWindow?.__c5NativeFrameId, removedFramePending: child.contentWindow?.__c5NativeFramePending });
          return remove.call(this, child);
        };
      }
    }, id);
    const close = context.close.bind(context);
    context.close = async (...args) => {
      if (id === 2 && tracing && !stopPromise) await stopTrace('fixture-2-context-close');
      const dir = resolve(process.env.WMS672_EVIDENCE_DIR, `fixture-${id}`);
      await mkdir(dir, { recursive: true });
      await writeFile(resolve(dir, 'requests.json'), JSON.stringify(requests, null, 2));
      for (const [index, page] of context.pages().entries()) {
        try {
          const data = await page.evaluate(() => ({ events: window.__c5DiagnosticEvents || [], nativeTotalPending: window.__c5NativeTotalPending, nativeFulfilled: window.__c5NativeFulfilled, nativeRejected: window.__c5NativeRejected, started: window.__wms672DecodeStarted, decoded: window.__wms672Decoded, decodeAt: window.__wms672Fault?.decodeAt, frames: window.__wms672Frames, transfers: window.__wms672Transfers?.length, iframes: document.querySelectorAll('iframe').length, alert: document.querySelector('[role=alert]')?.textContent }));
          await writeFile(resolve(dir, `page-${index}.json`), JSON.stringify(data, null, 2));
          await writeFile(resolve(dir, `page-${index}.html`), await page.content());
        } catch (error) { console.error('Diagnostic capture:', error.message); }
      }
      return close(...args);
    };
    if (id === 2) await syncClock('fixture-2-opened');
    return context;
  };
  return browser;
};
