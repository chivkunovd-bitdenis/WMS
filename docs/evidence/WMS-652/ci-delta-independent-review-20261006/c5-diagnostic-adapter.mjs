// Diagnostic interception only; leave the frozen C5 test and product unchanged.
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE);
const launch = chromium.launch.bind(chromium);
let fixture = 0;
chromium.launch = async (options) => {
  const browser = await launch({ ...options, args: [...(options.args ?? []), '--mute-audio'] });
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async (...args) => {
    const context = await newContext(...args);
    const id = ++fixture;
    await context.route('**/*', route => new URL(route.request().url()).origin === process.env.WMS672_TEST_URL
      ? route.continue() : route.abort());
    await context.addInitScript(() => {
      if (window === top) window.__c5Diagnostics = [];
      const record = (boundary, error) => {
        try {
          top.__c5Diagnostics?.push({ boundary, name: error?.name, message: error?.message,
            stack: error?.stack, parentError: error instanceof top.Error,
            localError: error instanceof Error, realm: window === top ? 'parent' : 'iframe',
            started: top.__wms672DecodeStarted, decoded: top.__wms672Decoded,
            decodeAt: top.__wms672Fault?.decodeAt, frames: top.__wms672Frames });
        } catch { /* Diagnostic capture must never change the rejection. */ }
      };
      const decode = HTMLImageElement.prototype.decode;
      HTMLImageElement.prototype.decode = async function () {
        try { return await decode.call(this); }
        catch (error) { record('native-decode', error); throw error; }
      };
      const originalCatch = Promise.prototype.catch;
      Promise.prototype.catch = function (handler) {
        if (typeof handler !== 'function') return originalCatch.call(this, handler);
        return originalCatch.call(this, function (error) {
          record('promise-catch', error);
          return handler(error);
        });
      };
    });
    const close = context.close.bind(context);
    context.close = async (...closeArgs) => {
      const dir = resolve(process.env.WMS672_EVIDENCE_DIR, `diagnostic-${id}`);
      await mkdir(dir, { recursive: true });
      for (const [index, page] of context.pages().entries()) {
        const summary = await page.evaluate(() => ({
          diagnostics: window.__c5Diagnostics,
          started: window.__wms672DecodeStarted, decoded: window.__wms672Decoded,
          decodeAt: window.__wms672Fault?.decodeAt,
          transferCount: window.__wms672Transfers?.length,
          alerts: Array.from(document.querySelectorAll('[role=alert]')).map(e => e.textContent),
          frameCount: document.querySelectorAll('iframe').length,
          printDisabled: document.querySelector('[data-testid=ff-inbound-boxes-print-all]')?.disabled,
        }));
        await writeFile(resolve(dir, `page-${index}.json`), JSON.stringify(summary, null, 2));
      }
      return close(...closeArgs);
    };
    return context;
  };
  return browser;
};
