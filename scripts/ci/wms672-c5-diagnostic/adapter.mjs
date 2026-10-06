// Diagnostic observer: rethrow original errors, keep frozen contract unchanged.
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
if (process.env.GITHUB_ACTIONS !== 'true' || process.platform !== 'linux') throw new Error('Linux Actions only');
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE);
const launch = chromium.launch.bind(chromium);
let fixture = 0;
chromium.launch = async (options = {}) => {
  const browser = await launch({ ...options, args: [...(options.args || []), '--mute-audio'] });
  if (browser.version() !== '141.0.7390.37') throw new Error(`Wrong diagnostic browser ${browser.version()}`);
  console.log('C5 environment', JSON.stringify({ node: process.version, platform: process.platform, arch: process.arch, browser: browser.version() }));
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async (...args) => {
    const context = await newContext(...args);
    const id = ++fixture;
    const requests = [];
    await context.route('**/*', route => new URL(route.request().url()).origin === process.env.WMS672_TEST_URL ? route.continue() : route.abort());
    context.on('request', request => requests.push({ method: request.method(), url: request.url() }));
    await context.addInitScript(() => {
      const root = window.top;
      root.__c5DiagnosticEvents ??= [];
      root.__c5DiagnosticErrors ??= new WeakMap();
      root.__c5DiagnosticErrorCounter ??= 0;
      const record = (kind, error, extra = {}) => {
        try {
          let identity = null;
          if (error && (typeof error === 'object' || typeof error === 'function')) {
            if (!root.__c5DiagnosticErrors.has(error)) root.__c5DiagnosticErrors.set(error, ++root.__c5DiagnosticErrorCounter);
            identity = root.__c5DiagnosticErrors.get(error);
          }
          if (root.__c5DiagnosticEvents.length < 5000) root.__c5DiagnosticEvents.push({
            kind, time: performance.now(), realm: window === root ? 'parent' : 'iframe', identity,
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
        if (image.matches('img.barcode')) record('native-start', null, { index, complete: image.complete, width: image.naturalWidth, height: image.naturalHeight, srcLength: image.src.length });
        return nativeDecode.apply(image, args).then(value => value, error => {
          record('native-reject', error, { index, complete: image.complete, width: image.naturalWidth, height: image.naturalHeight, src: image.src, outerHTML: image.outerHTML });
          throw error;
        });
      };
      const originalCatch = Promise.prototype.catch;
      Promise.prototype.catch = function (handler) {
        if (typeof handler !== 'function') return originalCatch.call(this, handler);
        return originalCatch.call(this, error => { record('promise-catch', error); return handler(error); });
      };
      if (window === root) {
        const remove = Node.prototype.removeChild;
        Node.prototype.removeChild = function (child) {
          if (child.tagName === 'IFRAME') record('iframe-remove', null, { srcdoc: child.srcdoc, transfers: root.__wms672Transfers?.length });
          return remove.call(this, child);
        };
      }
    });
    const close = context.close.bind(context);
    context.close = async (...args) => {
      const dir = resolve(process.env.WMS672_EVIDENCE_DIR, `fixture-${id}`);
      await mkdir(dir, { recursive: true });
      await writeFile(resolve(dir, 'requests.json'), JSON.stringify(requests, null, 2));
      for (const [index, page] of context.pages().entries()) {
        try {
          const data = await page.evaluate(() => ({ events: window.__c5DiagnosticEvents || [], started: window.__wms672DecodeStarted, decoded: window.__wms672Decoded, decodeAt: window.__wms672Fault?.decodeAt, frames: window.__wms672Frames, transfers: window.__wms672Transfers?.length, iframes: document.querySelectorAll('iframe').length, alert: document.querySelector('[role=alert]')?.textContent }));
          await writeFile(resolve(dir, `page-${index}.json`), JSON.stringify(data, null, 2));
          await writeFile(resolve(dir, `page-${index}.html`), await page.content());
        } catch (error) { console.error('Diagnostic capture:', error.message); }
      }
      return close(...args);
    };
    return context;
  };
  return browser;
};
