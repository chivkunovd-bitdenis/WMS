#!/usr/bin/env node
'use strict';
// WMS-395 release smoke: public UI only; never supply an auth token or submit a form.
// Run only after root VERIFIED: --after-root-verified=<full deployed SHA>.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const arg = process.argv[2] || '';
assert.match(arg, /^--after-root-verified=[0-9a-f]{40}$/);
assert.equal(process.argv.length, 3);
const origin = 'https://wms.sellerfocus.pro';
const output = path.resolve(__dirname, '../production-public-smoke-20260909');
const evidence = { rootVerifiedSha: arg.split('=')[1], started: new Date().toISOString(), scope: 'Unauthenticated public UI smoke; not protected FBS or seller acceptance.', pages: [], responses: [], blockedMutations: [], pageErrors: [] };
let browser;
async function main() {
  fs.mkdirSync(output, { recursive: true });
  try {
    browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
    await context.route('**/*', route => {
      const req = route.request();
      if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method())) {
        evidence.blockedMutations.push({ method: req.method(), origin: new URL(req.url()).origin, path: new URL(req.url()).pathname });
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', err => evidence.pageErrors.push({ name: err.name, message: err.message }));
    page.on('response', r => {
      const u = new URL(r.url());
      if (u.origin === origin) evidence.responses.push({ path: u.pathname, status: r.status(), resourceType: r.request().resourceType() });
    });
    for (const [name, route] of [['ff-fbs-login', '/app/ff/fbs'], ['seller-login', '/seller']]) {
      const response = await page.goto(origin + route, { waitUntil: 'networkidle' });
      assert(response && response.status() === 200, `${route}: unexpected document HTTP status`);
      await page.locator('input[type="password"]').waitFor({ state: 'visible', timeout: 15000 });
      const observed = await page.evaluate(() => ({
        url: location.href, title: document.title,
        headings: [...document.querySelectorAll('h1,h2,h3')].map(n => n.textContent),
        passwordInputs: document.querySelectorAll('input[type="password"]').length,
        loginButtonLabels: [...document.querySelectorAll('button')].map(n => n.textContent?.trim()).filter(Boolean),
        recoveryLinks: [...document.querySelectorAll('a[href]')].filter(a => /забыли|восстанов|forgot|reset/i.test(a.textContent || '')).map(a => ({ text: a.textContent.trim(), href: a.href })),
      }));
      evidence.pages.push({ name, requestedPath: route, status: response.status(), observed });
      await page.screenshot({ path: path.join(output, `${name}.png`), animations: 'disabled' });
      const link = observed.recoveryLinks.find(a => new URL(a.href).origin === origin);
      if (link) {
        // Click the actual observed same-origin link; never submit recovery.
        await page.getByRole('link', { name: link.text, exact: true }).first().click();
        await page.waitForURL(link.href);
        await page.waitForLoadState('networkidle');
        evidence.pages.push({ name: `${name}-recovery`, observed: await page.evaluate(() => ({ url: location.href, headings: [...document.querySelectorAll('h1,h2,h3')].map(n => n.textContent), bodyText: document.body.innerText })) });
        await page.screenshot({ path: path.join(output, `${name}-recovery.png`), animations: 'disabled' });
      }
    }
    assert.equal(evidence.pageErrors.length, 0, 'Unhandled browser JavaScript error');
    assert.equal(evidence.blockedMutations.length, 0, 'Page attempted an unexpected mutation');
    evidence.result = 'PUBLIC_UI_PASS';
  } finally {
    if (browser) await browser.close();
    evidence.chromeClosed = true;
    fs.writeFileSync(path.join(output, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n');
  }
  console.log(JSON.stringify({ result: evidence.result, pages: evidence.pages.map(p => p.name), errors: evidence.pageErrors.length, blockedMutations: evidence.blockedMutations.length }));
}
main().catch(error => { evidence.result = 'FAILED_OR_INCOMPLETE'; evidence.error = error.message; fs.writeFileSync(path.join(output, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n'); console.error(error.message); process.exitCode = 1; });
