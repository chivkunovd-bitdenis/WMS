// WMS-058: real React dialog in Chrome, synthetic HTTP only; no server or credentials.
const assert = require('node:assert/strict');
const path = require('node:path');
const { build } = require('../../../frontend/node_modules/esbuild');
const { chromium } = require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const baseline = process.argv.includes('--baseline');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(predicate) {
  for (let i = 0; i < 300; i++) { if (predicate()) return; await pause(10); }
  assert.fail('Timed out waiting for synthetic request');
}
async function main() {
  const bundled = await build({
    stdin: { contents: `import React,{useState} from 'react';
      import {createRoot} from 'react-dom/client';
      import {FfMarketplaceUnloadBoxAddDialog as Dialog} from './src/screens/ff/FfMarketplaceUnloadBoxAddDialog';
      const catalog=new Map(['P','Q'].map(id=>[id,{id,sku_code:id,product_name:id,wb_primary_barcode:id}]));
      function Harness(){const [open,setOpen]=useState(true);window.setDialogOpen=setOpen;
        const [scope,setScope]=useState({request:'request',box:'box'});window.setDialogScope=setScope;
        const [mounted,setMounted]=useState(true);window.setDialogMounted=setMounted;
        return mounted && <Dialog open={open} onClose={()=>setOpen(false)} requestId={scope.request} boxId={scope.box}
          boxLabel="Synthetic box" readOnly={false} token="synthetic-only" addressStorageEnabled
          catalogById={catalog} warehouseStockByProductId={new Map()} onUpdated={async()=>{}}/>;}
      createRoot(document.getElementById('root')).render(<Harness/>);`,
      resolveDir: path.resolve(__dirname, '../../../frontend'), loader: 'tsx' },
    bundle: true, write: false, platform: 'browser', format: 'iife', jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"' }, logLevel: 'silent',
  });
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const results = [];
  try {
    for (const scenario of baseline ? ['confirm'] : ['confirm', 'cancel-next', 'escape-next', 'close-pending', 'close-inflight', 'switch-request', 'switch-box', 'unmount']) {
      const context = await browser.newContext();
      try {
        const calls = [], errors = [];
        let releaseA, releaseP;
        const page = await context.newPage();
        page.on('pageerror', e => errors.push(e.message));
        await context.route('**/*', async route => {
          const request = route.request(), url = new URL(request.url());
          if (url.origin !== 'https://wms058.test') return route.abort();
          if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<div id="root"></div><script src="/harness.js"></script>' });
          if (url.pathname === '/harness.js') return route.fulfill({ contentType: 'application/javascript', body: bundled.outputFiles[0].text });
          if (url.pathname.endsWith('/pick-options')) return route.fulfill({ json: ['P','Q'].map(product_id => ({ product_id, sku_code: product_id, product_name: product_id, planned_qty: 1, picked_qty: 1, boxed_qty: 1, locations: [] })) });
          assert(url.pathname.endsWith('/scan'), `Unexpected route ${url.pathname}`);
          const body = request.postDataJSON(); calls.push(body);
          if (body.barcode === 'A') await new Promise(resolve => { releaseA = resolve; });
          if (body.barcode === 'P' && !body.allow_over_plan) await new Promise(resolve => { releaseP = resolve; });
          if (['A','B'].includes(body.barcode)) return route.fulfill({ json: { kind: 'container', container_kind: 'box', container_id: body.barcode, container_code: body.barcode, storage_location_id: `cell-${body.barcode}`, location_code: `cell-${body.barcode}` } });
          if (!body.allow_over_plan) return route.fulfill({ status: 422, json: { detail: 'plan_limit_exceeded' } });
          return route.fulfill({ json: { kind: 'product', product_id: body.product_id, storage_location_id: body.storage_location_id, picked_qty: 2 } });
        });
        await page.goto('https://wms058.test');
        const input = page.getByTestId('ff-mp-box-add-scan-input');
        const scan = async code => { await input.fill(code); await input.press('Enter'); };
        await input.waitFor();
        await page.waitForFunction(() => !document.querySelector('[data-testid="ff-mp-box-add-scan-input"]').disabled);
        await scan('A'); await until(() => releaseA);
        await scan('P'); releaseA(); await until(() => releaseP);
        assert.equal(calls.find(x => x.barcode === 'P').container_id, 'A', 'A queued before product must become product source');
        await scan('B');
        if (['cancel-next','escape-next'].includes(scenario)) await scan('Q');
        if (scenario === 'close-inflight') {
          await page.getByTestId('ff-mp-box-add-close').click();
          await page.evaluate(() => window.setDialogOpen(true));
          releaseP(); await pause(250);
          assert.equal(calls.length, 2, 'Close invalidates old queue even after reopen');
          assert.equal(await page.getByTestId('ff-mp-box-add-over-plan-dialog').count(), 0);
          await scan('B'); await until(() => calls.length === 3);
        } else {
          releaseP();
          const modal = page.getByTestId('ff-mp-box-add-over-plan-dialog');
          await modal.waitFor(); await pause(150);
          if (baseline) {
            await page.getByTestId('ff-mp-box-add-over-plan-confirm').click();
            await until(() => calls.some(x => x.allow_over_plan));
            assert.equal(calls.find(x => x.allow_over_plan).container_id, 'B');
          } else {
            assert.equal(calls.length, 2, 'Queued source/second rejection must wait for current decision');
            if (scenario === 'confirm') {
              await page.getByTestId('ff-mp-box-add-over-plan-confirm').click();
              await until(() => calls.length === 4);
              assert.deepEqual(calls[2], { ...calls[1], allow_over_plan: true });
              assert.equal(calls[3].barcode, 'B');
            } else if (['cancel-next','escape-next'].includes(scenario)) {
              if (scenario === 'escape-next') await modal.press('Escape');
              else await modal.getByRole('button', { name: 'Отмена', exact: true }).click();
              await until(() => calls.length === 4); await modal.waitFor();
              assert.equal(calls[3].barcode, 'Q'); assert.equal(calls[3].container_id, 'B');
              await page.getByTestId('ff-mp-box-add-over-plan-confirm').click();
              await until(() => calls.length === 5);
              assert.deepEqual(calls[4], { ...calls[3], allow_over_plan: true });
              assert(!calls.some(x => x.barcode === 'P' && x.allow_over_plan));
            } else {
              if (scenario === 'switch-request') await page.evaluate(() => window.setDialogScope({request:'other',box:'box'}));
              else if (scenario === 'switch-box') await page.evaluate(() => window.setDialogScope({request:'request',box:'other'}));
              else if (scenario === 'unmount') await page.evaluate(() => window.setDialogMounted(false));
              else await page.evaluate(() => window.setDialogOpen(false));
              await pause(150);
              assert.equal(calls.length, 2);
              await page.getByTestId('ff-mp-box-add-over-plan-dialog').waitFor({ state: 'hidden' });
              if (scenario === 'unmount') await page.evaluate(() => window.setDialogMounted(true));
              else await page.evaluate(() => window.setDialogOpen(true));
              await scan('B'); await until(() => calls.length === 3);
              assert.equal(calls[2].barcode, 'B');
              assert.equal(calls[2].container_id, undefined, 'New dialog scope must not inherit old source');
            }
          }
        }
        assert.deepEqual(errors, []);
        results.push({ scenario, calls });
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
  console.log(JSON.stringify({ mode: baseline ? 'reproduced-original-bug' : 'regressions-passed', syntheticHTTP: true, results }, null, 2));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
