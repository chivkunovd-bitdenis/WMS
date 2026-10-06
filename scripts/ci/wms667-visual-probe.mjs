// Synthetic visual evidence only. Linux GitHub runner, exact unmodified product.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

if (process.env.GITHUB_ACTIONS !== 'true' || process.platform !== 'linux') {
  throw new Error('Authorized only on the Linux GitHub runner; no local browser');
}
const source = resolve('source');
const baseline = resolve('baseline');
const dir = process.env.WMS667_EVIDENCE_DIR;
const extraDesktop = process.env.WMS667_EXTRA_DESKTOP === 'true';
const widths = extraDesktop ? [1024] : [1440, 390];
await mkdir(dir, { recursive: true });
const sha = path => execFileSync('git', ['rev-parse', 'HEAD'], { cwd: path, encoding: 'utf8' }).trim();
assert.equal(sha(source), 'c4142888f32830c0138cf221987affcbd3f2ac7e');
assert.equal(sha(baseline), '463b03825dec5fdca43a39c117e7afc4080c0508');
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE);
const { createServer } = await import(pathToFileURL(resolve(source, 'frontend/node_modules/vite/dist/node/index.js')));
const longSeller = 'ИП Александрова Екатерина Владиславовна — товары для дома и путешествий';
const fixtures = {
  sellers: [{ id: 'seller-a', name: longSeller }, { id: 'seller-b', name: 'Селлер Б' }],
  totals: { 'a-positive': { quantity: 5, reserved: 5, available: 0 },
    'a-zero': { quantity: 0, reserved: 0, available: 0 },
    'b-positive': { quantity: 7, reserved: 9, available: -2 } },
};
const report = { sourceSha: sha(source), productSha: '2d139aee43464ff799fe64d1cbf05b043ff88007',
  baselineSha: sha(baseline), probeSha: sha('.'), extraDesktop, fixtures, cases: [], requests: [], externalBlocked: [] };
const html = `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>WMS-667 synthetic visual</title></head>
<body><div id="root"></div><script type="module">
import React from 'react'; import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom'; import { ThemeProvider } from '@mui/material/styles';
import { muiTheme } from '/src/mui/theme.ts'; import '/src/index.css'; import '/src/ui/ui.css';
import { FfProductsCatalogScreen } from '/src/screens/v2/FfProductsCatalogScreen.tsx';
const fixtures = ${JSON.stringify(fixtures)};
window.__requests = []; window.__hold = null; window.__release = null;
const row = (id, seller) => ({id, seller_id: seller, seller_name: fixtures.sellers.find(s=>s.id===seller).name,
  name: 'Товар ' + id, sku_code: 'NEEDLE-' + id, wb_nm_id: 667, wb_vendor_code: null,
  wb_subject_name: 'X', wb_primary_image_url: null, wb_barcodes: [], wb_primary_barcode: null,
  wb_size:null, wb_color:null, wb_brand:null, wb_composition:null, packaging_instructions:null,
  marketplaces:['wildberries'], requires_honest_sign:false, has_packaging_instructions:false});
const all = [row('a-positive','seller-a'),row('a-zero','seller-a'),row('b-positive','seller-b')];
const response = data => ({ok:true,json:async()=>data});
const nativeFetch = window.fetch.bind(window);
window.fetch = async (input, init={}) => {
  const url = new URL(String(input), location.origin);
  if (!url.pathname.startsWith('/api/')) return nativeFetch(input,init);
  if ((init.method || 'GET') !== 'GET') throw new Error('Synthetic probe forbids writes');
  window.__requests.push({path:url.pathname,params:Object.fromEntries(url.searchParams),method:init.method||'GET'});
  if (url.pathname.endsWith('/products/ff-catalog-page')) {
    let items = all.filter(r => !url.searchParams.get('seller_id') || r.seller_id===url.searchParams.get('seller_id'));
    if(url.searchParams.get('has_stock')==='true') items=items.filter(r=>fixtures.totals[r.id].quantity>0);
    const data={items,total:items.length,scope_total:3,categories:['X']};
    if(window.__hold==='catalog') {window.__hold=null;return new Promise(resolve=>{window.__release=()=>resolve(response(data));});}
    return response(data);
  }
  if (url.pathname.endsWith('/operations/inventory-balances/summary')) {
    const data=url.searchParams.getAll('product_id').map(product_id=>({product_id,...fixtures.totals[product_id]}));
    if(window.__hold==='summary') {window.__hold=null;return new Promise(resolve=>{window.__release=()=>resolve(response(data));});}
    return response(data);
  }
  return response([]);
};
createRoot(document.getElementById('root')).render(React.createElement(ThemeProvider,{theme:muiTheme},
  React.createElement(MemoryRouter,{initialEntries:['/app/ff/products']},
    React.createElement(FfProductsCatalogScreen,{token:'synthetic',authHeaders:()=>({}),sellers:fixtures.sellers,warehouses:[]}))));
window.__ready=true;
</script></body></html>`;

const browser = await chromium.launch({ headless: true });
report.browser = browser.version();
async function selectSeller(page, name) {
  await page.getByTestId('ff-catalog-seller-filter').getByRole('combobox').click();
  await page.getByRole('option', { name, exact: true }).click();
}
async function settled(page) {
  await page.waitForFunction(() => !document.querySelector('[data-testid="ff-products-loading"]') &&
    document.querySelector('[data-testid="ff-product-row"]'));
}
async function geometry(page) {
  return page.evaluate(() => {
    const rect = el => {const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};
    const paper=document.querySelector('[data-testid="ff-catalog-filters"]');
    const controls=[...paper.firstElementChild.children];
    const boxes=controls.map(el=>({text:el.textContent,rect:rect(el)}));
    const overlaps=[];
    for(let i=0;i<boxes.length;i++) for(let j=i+1;j<boxes.length;j++) {
      const a=boxes[i].rect,b=boxes[j].rect;
      if(Math.min(a.right,b.right)-Math.max(a.x,b.x)>1 && Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)>1) overlaps.push([i,j]);
    }
    const headers=[...document.querySelectorAll('thead th')];
    const stockIndex=headers.findIndex(el=>el.textContent.trim()==='Остаток');
    const rows=[...document.querySelectorAll('[data-testid="ff-product-row"]')];
    return {viewport:{width:innerWidth,height:innerHeight},paper:rect(paper),controls:boxes,overlaps,
      controlsWithinViewport:boxes.every(({rect:r})=>r.x>=-1&&r.right<=innerWidth+1),
      stockIndex, rows:rows.map(row=>({text:row.textContent,stock:row.cells[stockIndex]?.textContent,
        stockRect:rect(row.cells[stockIndex]),sellerRect:rect(row.cells[7]),
        cells:[...row.cells].map(rect)}))};
  });
}
async function runCase(server, name, width, scenario, isBaseline=false) {
  const base=`http://127.0.0.1:${server.config.server.port}`;
  const context=await browser.newContext({viewport:{width,height:1000}});
  await context.route('**/*', route => {
    const url=route.request().url();
    if(new URL(url).origin===base) return route.continue();
    report.externalBlocked.push(url);return route.abort();
  });
  const page=await context.newPage();const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  const result={name,width,baseline:isBaseline};
  try {
    await page.goto(`${base}/__wms667__/`);
    await settled(page);
    await selectSeller(page,longSeller);await settled(page);
    if(!isBaseline) {await page.getByTestId('ff-catalog-has-stock-filter').getByRole('checkbox').check();await settled(page);}
    await scenario(page,result);
    result.geometry=await geometry(page);
    assert.deepEqual(result.geometry.overlaps,[], 'Filter controls overlap');
    assert.equal(result.geometry.controlsWithinViewport,true,'Filters extend outside narrow viewport');
    assert.equal(errors.length,0,'Browser runtime error');
    result.pass=true;
  } catch(error) {result.pass=false;result.error=error.stack;}
  finally {
    if(!result.geometry) {try{result.geometry=await geometry(page);}catch{}}
    result.pageErrors=errors;
    report.requests.push({name,requests:await page.evaluate(()=>window.__requests||[])});
    await page.screenshot({path:resolve(dir,`${name}.png`),fullPage:true});
    await writeFile(resolve(dir,`${name}.html`),await page.content());
    await writeFile(resolve(dir,`${name}.json`),JSON.stringify(result,null,2));
    report.cases.push(result);await context.close();
  }
}
async function serverFor(root,port) {
  const server=await createServer({root:resolve(root,'frontend'),configFile:resolve(root,'frontend/vite.config.ts'),
    server:{host:'127.0.0.1',port,strictPort:true},
    plugins:[{name:'wms667-synthetic-harness',configureServer(s){s.middlewares.use(async(req,res,next)=>{
      if(req.url!=='/__wms667__/') return next();
      res.setHeader('Content-Type','text/html');res.end(await s.transformIndexHtml(req.url,html));
    });}}]});
  await server.listen();return server;
}
try {
  const old=await serverFor(baseline,16670);
  try {for(const width of widths) await runCase(old,`baseline-${width}`,width,async()=>{},true);}
  finally {await old.close();}
  const current=await serverFor(source,16671);
  try {
    for(const width of widths) await runCase(current,`candidate-${width}`,width,async(page,result)=>{
      assert.equal(await page.getByTestId('ff-product-row').count(),1);
      assert.match(await page.getByTestId('ff-catalog-stock-on-hand-a-positive').innerText(),/Остаток 5/);
      assert.match(await page.getByTestId('ff-catalog-stock-reserved-a-positive').innerText(),/Резерв 5/);
      assert.match(await page.getByTestId('ff-catalog-stock-available-a-positive').innerText(),/Доступно 0/);
      result.fullyReserved={onHand:5,reserved:5,available:0,included:true};
      const stock=page.getByTestId('ff-catalog-stock-on-hand-a-positive');
      await stock.scrollIntoViewIfNeeded();
      await page.screenshot({path:resolve(dir,`candidate-${width}-stock.png`)});
    });
    for(const stage of extraDesktop ? [] : ['catalog','summary']) await runCase(current,`late-${stage}`,1440,async(page,result)=>{
      await page.evaluate(stage=>{window.__hold=stage;window.__release=null;},stage);
      await page.getByTestId('ff-catalog-has-stock-filter').getByRole('checkbox').uncheck();
      await page.waitForFunction(()=>typeof window.__release==='function');
      await selectSeller(page,'Селлер Б');await settled(page);
      assert.equal(await page.getByTestId('ff-product-row').count(),1);
      assert.match(await page.getByTestId('ff-product-row').innerText(),/b-positive/);
      await page.evaluate(()=>window.__release());await page.waitForTimeout(150);
      assert.equal(await page.getByTestId('ff-product-row').count(),1);
      assert.match(await page.getByTestId('ff-product-row').innerText(),/b-positive/);
      assert.match(await page.getByTestId('ff-catalog-stock-on-hand-b-positive').innerText(),/Остаток 7/);
      assert.equal(await page.getByTestId('ff-catalog-stock-on-hand-a-positive').count(),0);
      result.oldResponseReleased=true;result.seller='seller-b';
    });
  } finally {await current.close();}
} finally {
  await browser.close();
  await writeFile(resolve(dir,'report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
}
assert.equal(report.cases.length,extraDesktop ? 2 : 6);
assert.equal(report.cases.filter(test=>!test.pass).length,0,'One or more visual cases failed; inspect artifacts');
