// WMS-669 C11: unchanged real component, synthetic HTTP, Linux GitHub only.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
if (process.env.GITHUB_ACTIONS !== 'true' || process.platform !== 'linux') throw new Error('Linux GitHub runner only');
const dir = process.env.WMS669_EVIDENCE_DIR;
await mkdir(dir, {recursive:true});
const sha = path => execFileSync('git',['rev-parse','HEAD'],{cwd:path,encoding:'utf8'}).trim();
assert.equal(sha('source'),'7a47ad36f3a08ba973882b80cfe1bca87c2b873f');
assert.equal(sha('baseline'),'d7f4633912b066f740efdb2ce1ecabfba356755d');
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE);
const {createServer} = await import(pathToFileURL(resolve('source/frontend/node_modules/vite/dist/node/index.js')));
const report={productSha:sha('source'),baselineSha:sha('baseline'),probeSha:sha('.'),cases:[],externalBlocked:[]};
const html=`<!doctype html><html lang="ru"><head><meta charset="utf-8"></head><body><div id="root"></div><script type="module">
import React from 'react';import {createRoot} from 'react-dom/client';import {MemoryRouter} from 'react-router-dom';
import {ThemeProvider,CssBaseline} from '@mui/material';import {muiTheme} from '/src/mui/theme.ts';
import '/src/index.css';import '/src/ui/ui.css';import {SellerProductsStockScreen} from '/src/screens/v2/SellerProductsStockScreen.tsx';
window.__requests=[];window.__fail=false;
const row=(i)=>({key:'product:p'+i,id:'p'+i,on_fulfillment:true,marketplace:i===30?'ozon':'wildberries',
name:'Пуховик зимний женский удлинённый с капюшоном — очень длинное название товара, цвет чёрный, коллекция осень-зима '+i,
sku_code:'SKU-'+i,wb_vendor_code:i<21?'2329блэк':'23290',wb_subject_name:i<29?'Пуховики':null,wb_size:i<29?'48':null,
wb_nm_id:669+i,wb_primary_image_url:null,wb_barcodes:['66900000'+i],wb_primary_barcode:'66900000'+i,
ozon_sku:i===30?'ozon-sku':null,ozon_offer_id:i===30?'offer-ozon':null,
packaging_instructions:'ТЗ',has_packaging_instructions:true,requires_honest_sign:true});
const all=[...Array.from({length:31},(_,i)=>row(i)),{key:'wb:669101',on_fulfillment:false,marketplace:'wildberries',nm_id:669101,
vendor_code:'2329блэк',category:'Пуховики',sizes:['46','48'],name:'WB карточка 46/48',photo_url:null,barcodes:[]}];
const summary=all.filter(x=>x.id).map((x,i)=>({product_id:x.id,quantity:i<21?4:0,reserved:i<21?4:0,available:0}));
const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
const native=window.fetch.bind(window);
window.fetch=async(input,init={})=>{const u=new URL(String(input),location.origin);if(!u.pathname.startsWith('/api/'))return native(input,init);
if((init.method||'GET')!=='GET')throw new Error('No writes in visual proof');
window.__requests.push({path:u.pathname,params:Object.fromEntries(u.searchParams)});
if(u.pathname.endsWith('/seller-catalog/page')){
if(window.__fail)return response({detail:'Не удалось загрузить товары.'},503);
let items=all;const p=u.searchParams;
if(p.get('category'))items=items.filter(r=>(r.wb_subject_name||r.category)===p.get('category'));
if(p.get('article'))items=items.filter(r=>(r.wb_vendor_code||r.vendor_code||'').toLowerCase()===p.get('article').toLowerCase());
if(p.get('size'))items=items.filter(r=>r.wb_size===p.get('size')||(r.sizes||[]).includes(p.get('size')));
if(p.get('stock_only')==='true')items=items.filter(r=>summary.some(s=>s.product_id===r.id&&s.quantity>0));
if(p.get('marketplace')&&p.get('marketplace')!=='all')items=items.filter(r=>r.marketplace===p.get('marketplace'));
if(p.get('on_fulfillment')==='yes')items=items.filter(r=>r.on_fulfillment);if(p.get('on_fulfillment')==='no')items=items.filter(r=>!r.on_fulfillment);
if(p.get('search'))items=items.filter(r=>r.name.toLowerCase().includes(p.get('search').toLowerCase()));
if(p.get('group_by'))items=[...items].sort((a,b)=>[(a.wb_subject_name||a.category||''),(a.wb_vendor_code||a.vendor_code||''),(a.wb_size||(a.sizes||[]).join(', ')),a.key].join('|').localeCompare([(b.wb_subject_name||b.category||''),(b.wb_vendor_code||b.vendor_code||''),(b.wb_size||(b.sizes||[]).join(', ')),b.key].join('|')));
return response({items:items.slice(Number(p.get('offset')||0),Number(p.get('offset')||0)+Number(p.get('limit')||50)),total:items.length,scope_total:all.length,categories:['Пуховики','Футболки']});}
if(u.pathname.endsWith('/summary'))return response(summary);if(u.pathname.endsWith('/tokens'))return response({has_content_token:false});
if(u.pathname.endsWith('/account'))return response({connected:false});return response([]);};
createRoot(document.getElementById('root')).render(React.createElement(ThemeProvider,{theme:muiTheme},React.createElement(CssBaseline),
React.createElement(MemoryRouter,null,React.createElement(SellerProductsStockScreen,{token:'synthetic',authHeaders:()=>({}),sellerId:'synthetic',sellerName:'Тестовый селлер',warehouses:[]}))));
</script></body></html>`;
async function serverFor(root,port){const server=await createServer({root:resolve(root,'frontend'),configFile:resolve(root,'frontend/vite.config.ts'),
server:{host:'127.0.0.1',port,strictPort:true},plugins:[{name:'wms669-proof',configureServer(s){s.middlewares.use(async(req,res,next)=>{
if(req.url!=='/__wms669__/')return next();res.setHeader('Content-Type','text/html');res.end(await s.transformIndexHtml(req.url,html));});}}]});await server.listen();return server;}
const browser=await chromium.launch({headless:true});report.browser=browser.version();
async function select(page,id,name){await page.getByTestId(id).getByRole('combobox').click();await page.getByRole('option',{name,exact:true}).click();}
async function save(page,name){await page.screenshot({path:resolve(dir,name+'.png'),fullPage:true});}
async function geometry(page){return page.evaluate(()=>{
const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height};};
const controls=[...document.querySelector('[data-testid="seller-catalog-filters"]').firstElementChild.children].map(e=>({text:e.textContent,rect:rect(e)}));
const overlaps=[];for(let i=0;i<controls.length;i++)for(let j=i+1;j<controls.length;j++){const a=controls[i].rect,b=controls[j].rect;if(Math.min(a.right,b.right)-Math.max(a.x,b.x)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)>1)overlaps.push([i,j]);}
const table=document.querySelector('[data-testid="seller-products-table"]');const style=getComputedStyle(table);
const rows=[...document.querySelectorAll('[data-testid="seller-product-row"]')].map(r=>({text:r.textContent,cells:[...r.cells].map(e=>({text:e.textContent,rect:rect(e),style:{font:getComputedStyle(e).font,color:getComputedStyle(e).color}})),buttons:[...r.querySelectorAll('button')].map(e=>({text:e.textContent,rect:rect(e)}))}));
return {controls,overlaps,rows,font:style.font,color:style.color,headers:[...table.querySelectorAll('thead th')].map(e=>e.textContent)};});}
async function run(server,name,fn){const base='http://127.0.0.1:'+server.config.server.port;const context=await browser.newContext({viewport:{width:1440,height:1000}});
await context.route('**/*',route=>{const u=route.request().url();if(new URL(u).origin===base)return route.continue();report.externalBlocked.push(u);return route.abort();});
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));const result={name};
try{await page.goto(base+'/__wms669__/');await page.getByTestId('seller-product-row').first().waitFor();await fn(page,result);
result.geometry=await geometry(page);assert.deepEqual(result.geometry.overlaps,[],'Filters overlap');assert.deepEqual(errors,[],'Runtime error');result.pass=true;
}catch(e){result.pass=false;result.error=e.stack;}finally{result.pageErrors=errors;result.requests=await page.evaluate(()=>window.__requests||[]);await save(page,name);await writeFile(resolve(dir,name+'.html'),await page.content());report.cases.push(result);await context.close();}}
try{const old=await serverFor('baseline',16690);try{await run(old,'baseline',async()=>{});}finally{await old.close();}
const current=await serverFor('source',16691);try{
await run(current,'candidate-initial',async(page,r)=>{r.initialRows=await page.getByTestId('seller-product-row').count();});
await run(current,'candidate-filter-pagination',async(page,r)=>{
await select(page,'seller-catalog-category-filter','Пуховики');await page.getByLabel('Артикул',{exact:true}).fill('2329блэк');await page.getByLabel('Размер',{exact:true}).fill('48');await page.getByLabel('Только с остатком').check();
await page.waitForFunction(()=>document.querySelectorAll('[data-testid="seller-product-row"]').length===21);
await page.getByTestId('seller-products-pagination').getByRole('combobox').click();await page.getByRole('option',{name:'10',exact:true}).click();
await page.waitForFunction(()=>document.querySelectorAll('[data-testid="seller-product-row"]').length===10);
assert.match(await page.getByTestId('seller-product-row').first().innerText(),/Остаток 4[\s\S]*Резерв 4[\s\S]*Доступно 0/);
await save(page,'filtered-page1');await page.getByRole('button',{name:'Go to next page'}).click();
await page.waitForFunction(()=>window.__requests.some(r=>r.params.offset==='10'&&r.params.stock_only==='true'));
await page.waitForTimeout(300);const groups=await page.locator('[data-testid="seller-products-table"] tbody tr').evaluateAll(rows=>rows.filter(r=>!r.dataset.testid).map(r=>r.textContent));
assert.deepEqual(groups.slice(0,3),['Пуховики','2329блэк','48']);r.page2Groups=groups;await save(page,'filtered-page2');
await page.getByLabel('Только с остатком').uncheck();await page.getByLabel('Артикул',{exact:true}).fill('');await page.getByLabel('Размер',{exact:true}).fill('');await select(page,'seller-catalog-category-filter','Все категории');
await page.waitForTimeout(400);r.filtersCleared=true;});
await run(current,'candidate-marketplaces-empty-error',async(page,r)=>{
await select(page,'seller-catalog-marketplace-filter','Ozon');await page.waitForFunction(()=>document.querySelectorAll('[data-testid="seller-product-row"]').length===1);assert.match(await page.getByTestId('seller-product-row').innerText(),/Ozon/i);await save(page,'ozon');
await select(page,'seller-catalog-marketplace-filter','Все маркетплейсы');await select(page,'seller-catalog-fulfillment-filter','Не на фулфилменте');await page.waitForFunction(()=>document.querySelectorAll('[data-testid="seller-product-row"]').length===1);
assert.match(await page.getByTestId('seller-product-row').innerText(),/46, 48/);await save(page,'wb-multisize');
await page.getByLabel('Только с остатком').check();await page.getByText('Ничего не найдено.',{exact:true}).waitFor();await save(page,'empty');
await page.evaluate(()=>window.__fail=true);await page.getByLabel('Артикул',{exact:true}).fill('failure');await page.getByTestId('seller-products-error').waitFor();assert.match(await page.getByTestId('seller-products-error').innerText(),/Не удалось загрузить товары/);await save(page,'error');
await page.evaluate(()=>window.__fail=false);await page.getByLabel('Артикул',{exact:true}).fill('');await page.getByLabel('Только с остатком').uncheck();await page.getByTestId('seller-product-row').waitFor();r.recovered=true;});
const ctx=await browser.newContext({viewport:{width:1440,height:1000}});const p=await ctx.newPage();await p.goto('http://127.0.0.1:16691/warehouse-map.html');await p.getByText('Ячейки',{exact:true}).first().waitFor();await save(p,'cells-reference');report.cellsReference=true;await ctx.close();
}finally{await current.close();}
}finally{await browser.close();await writeFile(resolve(dir,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));}
assert.equal(report.cases.length,4);assert.equal(report.cases.filter(c=>!c.pass).length,0,'C11 browser case failed');assert.equal(report.cellsReference,true);
