// Execution adapter only. Frozen contracts and production code are never edited.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';

if (process.env.GITHUB_ACTIONS !== 'true' || process.platform !== 'linux') {
  throw new Error('This browser adapter is authorized only on the Linux GitHub runner');
}
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE);

if (!process.argv.includes('--render673')) {
  // Capture failure diagnostics before the unchanged test closes its context.
  let fixture = 0;
  // newContext belongs to Browser, not BrowserType: wrap the returned browser.
  const launch = chromium.launch.bind(chromium);
  chromium.launch = async (...args) => {
    const browser = await launch(...args);
    const newContext = browser.newContext.bind(browser);
    browser.newContext = async (...contextArgs) => {
      const context = await newContext(...contextArgs);
      const id = ++fixture;
      const captures = [];
      const captureDir = resolve(process.env.WMS672_EVIDENCE_DIR, `fixture-${id}`);
      await context.exposeBinding('__wms672CaptureDecodeSource', (_source, data) => {
        const capture = (async () => {
          await mkdir(captureDir, { recursive: true });
          const key = data.barcode?.replace(/[^a-zA-Z0-9_-]/g, '_') || 'unknown';
          await writeFile(resolve(captureDir, `${key}.decode.json`), JSON.stringify({ ...data, src: undefined }, null, 2));
          if (data.src.startsWith('data:image/png;base64,')) {
            await writeFile(resolve(captureDir, `${key}.png`), Buffer.from(data.src.split(',')[1], 'base64'));
          }
        })();
        captures.push(capture);
        return capture;
      });
      // Observe native decode failures before product cleanup destroys the frame.
      // No substitution of native results, frozen faults, expectations or timeouts.
      await context.addInitScript(() => {
        const decode = HTMLImageElement.prototype.decode;
        HTMLImageElement.prototype.decode = function (...args) {
          const barcode = this.closest('.label')?.getAttribute('data-barcode');
          const source = () => ({ barcode, src: this.src, width: this.naturalWidth, height: this.naturalHeight });
          if (barcode === 'INB-000000000226') void window.__wms672CaptureDecodeSource(source());
          return decode.apply(this, args).catch(error => {
            void window.__wms672CaptureDecodeSource({ ...source(), error: { name: error.name, message: error.message, code: error.code } });
            console.error('WMS672 native decode failure', JSON.stringify({
              name: error.name, message: error.message, code: error.code,
              srcLength: this.src.length, complete: this.complete,
              width: this.naturalWidth, height: this.naturalHeight,
              barcode: this.closest('.label')?.getAttribute('data-barcode'),
            }));
            throw error;
          });
        };
      });
      const requests = [];
      const events = [];
      context.on('page', page => {
        page.on('console', message => { if (message.type() === 'error') events.push({ type: 'console', text: message.text() }); });
        page.on('pageerror', error => events.push({ type: 'pageerror', text: error.stack }));
      });
      await context.route('**/*', route => new URL(route.request().url()).origin === process.env.WMS672_TEST_URL
        ? route.continue() : route.abort());
      context.on('request', request => requests.push({ method: request.method(), url: request.url() }));
      const close = context.close.bind(context);
      context.close = async (...closeArgs) => {
        const dir = resolve(process.env.WMS672_EVIDENCE_DIR, `fixture-${id}`);
        await Promise.allSettled(captures);
        await mkdir(dir, { recursive: true });
        await writeFile(resolve(dir, 'requests.json'), JSON.stringify(requests, null, 2));
        await writeFile(resolve(dir, 'events.json'), JSON.stringify(events, null, 2));
        for (const [index, page] of context.pages().entries()) {
          try {
            await writeFile(resolve(dir, `page-${index}.state.json`), JSON.stringify(await page.evaluate(() => ({
              decoded: window.__wms672Decoded, decodeStarted: window.__wms672DecodeStarted,
              transfers: window.__wms672Transfers?.map(t => ({ decoded: t.decoded, htmlLength: t.html.length })),
              fault: window.__wms672Fault, local: location.origin === new URL(window.__probeOrigin || 'http://127.0.0.1:16724').origin ? Object.entries(localStorage) : [], session: location.origin === 'http://127.0.0.1:16724' ? Object.entries(sessionStorage) : [],
              frames: [...document.querySelectorAll('iframe')].map(f => ({ images: f.contentDocument?.images.length, complete: [...(f.contentDocument?.images || [])].filter(i => i.complete).length })),
              alerts: [...document.querySelectorAll('[role=alert]')].map(a => a.textContent),
            })), null, 2));
            await page.screenshot({ path: resolve(dir, `page-${index}.png`), timeout: 3000 });
            await writeFile(resolve(dir, `page-${index}.html`), await page.content());
            const sources = await page.locator('iframe').evaluateAll(frames => frames.map(f => f.srcdoc));
            for (const [n, source] of sources.entries()) await writeFile(resolve(dir, `source-${index}-${n}.html`), source);
          } catch (error) { console.error('Diagnostic capture:', error.message); }
        }
        return close(...closeArgs);
      };
      return context;
    };
    return browser;
  };
} else {
  const dir = process.env.WMS673_RENDERED_ARTIFACTS_DIR;
  await mkdir(dir, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.WMS672_CHROMIUM });
  try {
    const context = await browser.newContext({ viewport: { width: Math.round(277 * 96 / 25.4), height: 720 } });
    // Block every external network request; only the runner's synthetic Vite graph is allowed.
    await context.route('**/*', route => new URL(route.request().url()).origin === process.env.WMS672_TEST_URL
      ? route.continue() : route.abort());
    const page = await context.newPage();
    await page.goto(`${process.env.WMS672_TEST_URL}/tests-e2e/wms672-harness.html`);
    const contract = await readFile('src/screens/v2/fbsPickingColor.wms673.pdf.test.ts', 'utf8');
    // Execute the contract's exact input builder; strip its sole TS argument annotation.
    const inputBuilder = contract.slice(contract.indexOf('const LONG_COLOR ='), contract.indexOf('\ndescribe'))
      .replace('count: number', 'count');
    for (const [count, name] of [[1, 'baseline-control'], [1, 'baseline-long-row'], [34, 'baseline-multipage']]) {
      const html = await page.evaluate(async ({ inputBuilder, count }) => {
        const { buildFbsPickingListPrintHtml, fbsBuildPickingRows } = await import('/src/screens/v2/fbsUx.ts');
        const { wms673Order, wms673PrintMeta } = await import('/src/screens/v2/wms673PrintFixtures.ts');
        return eval(`${inputBuilder}\nhtmlFor(${count})`);
      }, { inputBuilder, count });
      const key = createHash('sha256').update(html).digest('hex');
      const prefix = resolve(dir, key);
      await writeFile(`${prefix}.html`, html);
      const tape = await context.newPage();
      await tape.emulateMedia({ media: 'print' });
      await tape.setContent(html);
      await tape.evaluate(() => document.fonts.ready);
      const geometry = await tape.evaluate(() => {
        const rows = [...document.querySelectorAll('tbody tr')];
        const headers = [...document.querySelectorAll('thead th')];
        const table = document.querySelector('table');
        const bounds = el => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right }; };
        const textRects = cell => {
          const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
          const rects = [];
          while (walker.nextNode()) {
            if (!walker.currentNode.textContent.trim()) continue;
            const range = document.createRange(); range.selectNodeContents(walker.currentNode);
            rects.push(...range.getClientRects());
          }
          return rects;
        };
        const fits = cell => {
          const b = cell.getBoundingClientRect();
          return textRects(cell).every(r => r.left >= b.left - 1 && r.right <= b.right + 1 && r.top >= b.top - 1 && r.bottom <= b.bottom + 1);
        };
        const size = document.querySelector('td.size');
        const colorIndex = headers.findIndex(h => h.textContent.trim().toLowerCase() === 'цвет');
        const cells = rows.flatMap(row => [...row.cells]);
        return {
          tableBounds: bounds(table), columnBounds: headers.map(bounds),
          rowCellCounts: rows.map(r => r.cells.length),
          tableWithinPage: bounds(table).left >= -1 && bounds(table).right <= innerWidth + 1,
          headersAligned: rows.every(row => [...row.cells].every((cell, i) => Math.abs(bounds(cell).left - bounds(headers[i]).left) < 1 && Math.abs(bounds(cell).right - bounds(headers[i]).right) < 1)),
          allCellContentFits: cells.every(fits),
          neighboringCellsDoNotOverlap: rows.every(row => [...row.cells].every((c, i, all) => !i || bounds(all[i - 1]).right <= bounds(c).left + 1)) && cells.every(fits),
          rowsDoNotOverlap: rows.every((r, i) => !i || rows[i - 1].getBoundingClientRect().bottom <= r.getBoundingClientRect().top + 1),
          sizeStyle: size ? { width: getComputedStyle(size).width, fontSize: getComputedStyle(size).fontSize } : null,
          fixedWidths: headers.filter(h => ['number', 'image', 'sticker', 'quantity'].includes(h.className)).map(h => ({ className: h.className, width: getComputedStyle(h).width })),
          sizeCells: [...document.querySelectorAll('td.size')].map(c => ({ text: c.textContent.trim(), linesWithinCell: fits(c), lineCount: new Set(textRects(c).map(r => Math.round(r.top))).size })),
          colorCells: colorIndex < 0 ? [] : rows.map(r => ({ text: r.cells[colorIndex].textContent.trim(), linesWithinCell: fits(r.cells[colorIndex]) })),
        };
      });
      await writeFile(`${prefix}.geometry.json`, JSON.stringify(geometry, null, 2));
      await tape.pdf({ path: `${prefix}.pdf`, preferCSSPageSize: true, printBackground: true });
      await tape.screenshot({ path: `${prefix}.png` });
      console.log(JSON.stringify({ name, count, key, browser: browser.version(), geometry }));
      await tape.close();
    }
    await context.close();
  } finally { await browser.close(); }
}
