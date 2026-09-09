'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {chromium}=require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const WEB='https://web-production-9e7c1.up.railway.app',TENANT='9c31f3f4-ce62-4c1f-891a-295b278f1e69',SELLER='50110328-fa03-4604-b2e4-8ca27fc8bb41';
const output=process.argv[2];assert(output?.startsWith('/'));fs.mkdirSync(output,{recursive:true});
const token=fs.readFileSync('/Users/deniscivkunov/Projects/WMS/.secrets/staging-token.txt','utf8').trim().replace(/^Bearer\s+/i,'');
const result={source:'3f6f02c77db6ee777518f6dc55922297df907d67',started:new Date().toISOString(),web:WEB,cases:[],blockedMutations:[],pageErrors:[],intercepted:[]};
let browser,page;
const digest=rows=>crypto.createHash('sha256').update(JSON.stringify(rows.map(x=>x.id).sort())).digest('hex');
async function get(p){const r=await fetch(WEB+'/api'+p,{headers:{Authorization:`Bearer ${token}`},signal:AbortSignal.timeout(30000)});assert.equal(r.status,200,'GET '+p);return r.json();}
(async()=>{
 const me=await get('/auth/me');assert.equal(me.tenant_id,TENANT);assert.equal(me.role,'fulfillment_admin');result.auth={tenant:me.tenant_id,role:me.role};
 const sellers=await get('/sellers'),seller=sellers.find(x=>x.id===SELLER);assert(seller);
 const before=await get('/operations/inbound-intake-requests');result.documentsBefore={count:before.length,idsSha256:digest(before)};
 browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 await context.addInitScript(({origin,value})=>{if(location.origin===origin)localStorage.setItem('wms_token_ff',value)},{origin:WEB,value:token});
 let emptyWarehouse=false;
 await context.route('**/*',route=>{const r=route.request(),u=new URL(r.url());
  if(!['GET','HEAD','OPTIONS'].includes(r.method())){result.blockedMutations.push({method:r.method(),path:u.pathname});return route.abort();}
  if(emptyWarehouse&&u.origin===WEB&&u.pathname==='/api/warehouses'){result.intercepted.push({method:'GET',path:u.pathname,fixture:'empty warehouse list in browser only'});return route.fulfill({status:200,contentType:'application/json',body:'[]'});}
  return route.continue();
 });
 page=await context.newPage();page.on('pageerror',e=>result.pageErrors.push(e.message));
 await page.goto(WEB+'/app/ff/reception');await page.getByTestId('ff-reception-page').waitFor({timeout:45000});
 await page.getByTestId('ff-inbound-create').click();let dialog=page.getByTestId('ff-inbound-create-dialog');await dialog.waitFor();
 await page.getByTestId('ff-inbound-create-seller').click();await page.getByRole('option',{name:seller.name,exact:true}).click();
 assert((await page.getByTestId('ff-inbound-create-seller').innerText()).includes(seller.name));
 await page.screenshot({path:path.join(output,'01-stage-inbound-dialog.png'),animations:'disabled'});
 result.cases.push({name:'real stage inbound dialog with QA seller',pass:true});
 await page.getByTestId('ff-inbound-create-cancel').click();await dialog.waitFor({state:'hidden'});
 await page.getByTestId('ff-inbound-create-return').click();await dialog.waitFor();assert(await page.getByTestId('ff-inbound-create-marketplace').isVisible());
 await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});result.cases.push({name:'return dialog marketplace and Escape',pass:true});
 emptyWarehouse=true;
 await page.reload();await page.getByTestId('ff-reception-page').waitFor({timeout:45000});
 await page.getByTestId('ff-inbound-create').click();await dialog.waitFor();
 await page.getByTestId('ff-inbound-create-seller').click();await page.getByRole('option',{name:seller.name,exact:true}).click();
 await page.getByTestId('ff-inbound-create-confirm').click();
 await page.getByTestId('ff-inbound-create-error').filter({hasText:'Склад ФФ не найден.'}).waitFor({timeout:15000});
 assert(await dialog.isVisible());assert((await page.getByTestId('ff-inbound-create-seller').innerText()).includes(seller.name));
 await page.screenshot({path:path.join(output,'02-stage-missing-warehouse-error.png'),animations:'disabled'});
 result.cases.push({name:'deployed App handles empty warehouse GET without POST',error:await page.getByTestId('ff-inbound-create-error').innerText(),dialogOpen:true,sellerPreserved:true});
 await page.getByTestId('ff-inbound-create-cancel').click();await dialog.waitFor({state:'hidden'});
 await page.getByTestId('ff-inbound-create').click();await dialog.waitFor();assert.equal(await page.getByTestId('ff-inbound-create-error').count(),0);await page.keyboard.press('Escape');
 result.cases.push({name:'reopening clears old error',pass:true});
 const after=await get('/operations/inbound-intake-requests');result.documentsAfter={count:after.length,idsSha256:digest(after)};assert.deepEqual(result.documentsAfter,result.documentsBefore);
 assert.equal(result.blockedMutations.length,0);assert.equal(result.pageErrors.length,0);
 assert(result.intercepted.length>0);result.result='PASS';
})().catch(async e=>{result.result='INCOMPLETE';result.error=String(e);process.exitCode=1;if(page)await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});}).finally(async()=>{if(browser)await browser.close();result.finished=new Date().toISOString();fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));});
