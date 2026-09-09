// WMS-398: two real staging catalog opens, read-only, no response substitution.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const WEB = 'https://web-production-9e7c1.up.railway.app';
const evidence = { started: new Date().toISOString(), runs: [], blocked: [], pageErrors: [], cache: 'Playwright routing disables HTTP cache; repeat reuses browser/context, not a normal warm HTTP-cache measurement.' };
const token = fs.readFileSync('/Users/deniscivkunov/Projects/WMS/.secrets/staging-token.txt', 'utf8').trim().replace(/^Bearer\s+/i, '');
let browser;
async function main() {
  const output = process.argv[2];
  assert(output?.startsWith('/') && output.endsWith('.json'));
  try {
    for (const path of ['/health/runtime', '/health']) {
      const r = await fetch(`${WEB}/api${path}`);
      evidence[path] = { status: r.status, body: await r.json() };
    }
    const me = await fetch(`${WEB}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } });
    assert(me.ok);
    assert.equal((await me.json()).tenant_id, '9c31f3f4-ce62-4c1f-891a-295b278f1e69');
    browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addInitScript(value => {
      localStorage.setItem('wms_token_ff', value);
      window.__catalogFirstRows = null;
      new MutationObserver(() => {
        if (window.__catalogFirstRows !== null) return;
        const rows = [...document.querySelectorAll('[data-testid="ff-product-row"]')].filter(row => row.getClientRects().length > 0);
        if (rows.length) window.__catalogFirstRows = { ms: performance.now(), rows: rows.length };
      }).observe(document, { subtree: true, childList: true, attributes: true });
    }, token);
    await context.route('**/*', route => {
      const request = route.request();
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
        evidence.blocked.push({ method: request.method(), path: new URL(request.url()).pathname });
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', error => evidence.pageErrors.push(error.message));
    for (let index = 0; index < 2; index++) {
      const run = { opening: index + 1, requests: [], catalog: [] };
      evidence.runs.push(run);
      const reads = [];
      const observe = response => {
        const url = new URL(response.url());
        if (url.origin !== WEB || !url.pathname.startsWith('/api/')) return;
        reads.push((async () => {
          await response.finished();
          const req = response.request();
          const timing = req.timing();
          const headers = await response.allHeaders();
          const item = { path: url.pathname + url.search, status: response.status(),
            startEpochMs: timing.startTime, responseStartMs: timing.responseStart,
            requestStartMs: timing.requestStart,
            ttfbFromSendMs: timing.responseStart - timing.requestStart,
            completeMs: timing.responseEnd,
            serverTiming: headers['server-timing'] ?? null,
            processTime: headers['x-process-time'] ?? null,
            contentLength: headers['content-length'] ?? null, contentEncoding: headers['content-encoding'] ?? null };
          run.requests.push(item);
          if (['/api/products', '/api/products/ff-catalog', '/api/products/ff-catalog-page'].includes(url.pathname)) {
            const bytes = await response.body();
            const body = JSON.parse(bytes.toString('utf8'));
            run.catalog.push({ ...item, decodedBodyBytes: bytes.length,
              rows: Array.isArray(body) ? body.length : body.items?.length,
              total: body.total ?? null, scopeTotal: body.scope_total ?? null });
          }
        })().catch(error => run.requests.push({ path: url.pathname, captureError: error.message })));
      };
      page.on('response', observe);
      if (index === 0) await page.goto(`${WEB}/app/ff/products`, { waitUntil: 'domcontentloaded' });
      else await page.reload({ waitUntil: 'domcontentloaded' });
      await page.getByTestId('ff-product-row').first().waitFor({ timeout: 30000 });
      await page.waitForLoadState('networkidle', { timeout: 15000 });
      run.firstVisible = await page.evaluate(() => window.__catalogFirstRows);
      run.finalRows = await page.getByTestId('ff-product-row').count();
      run.countLabel = await page.getByTestId('ff-catalog-filter-count').innerText();
      run.resources = await page.evaluate(() => performance.getEntriesByType('resource').filter(x => x.name.includes('/api/products')).map(x => ({ url: x.name, startTime: x.startTime, requestStart: x.requestStart, responseStart: x.responseStart, responseEnd: x.responseEnd, transferSize: x.transferSize, encodedBodySize: x.encodedBodySize, decodedBodySize: x.decodedBodySize })));
      run.webAssets = await page.locator('script[src]').evaluateAll(nodes => nodes.map(x => x.src));
      page.off('response', observe);
      await Promise.all(reads);
      run.requests.sort((a, b) => (a.startEpochMs ?? 0) - (b.startEpochMs ?? 0));
      process.stdout.write(JSON.stringify({ opening: run.opening, firstVisible: run.firstVisible, rows: run.finalRows, countLabel: run.countLabel, apiRequests: run.requests.length, catalog: run.catalog }) + '\n');
    }
    await page.screenshot({ path: output.replace(/\.json$/, '.png'), fullPage: false });
    evidence.result = 'measured';
  } catch (error) { evidence.error = error.message; process.exitCode = 1; }
  finally {
    if (browser) await browser.close();
    fs.writeFileSync(output, JSON.stringify(evidence, null, 2));
  }
}
main().catch(error => { process.stderr.write(error.message + '\n'); process.exitCode = 1; });
