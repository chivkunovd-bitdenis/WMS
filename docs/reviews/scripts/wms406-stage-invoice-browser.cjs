'use strict';
// WMS-406/407 one-off actual Chrome QA; no mocked data or warehouse writes.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const WEB = 'https://web-production-9e7c1.up.railway.app';
const TENANT = '9c31f3f4-ce62-4c1f-891a-295b278f1e69';
const SELLER = '50110328-fa03-4604-b2e4-8ca27fc8bb41';
const execute = process.argv[2] === '--execute-root-ready';
const sha = execute ? process.argv[3] : null;
assert(!execute || /^[a-f0-9]{40}$/.test(sha), 'Full root-confirmed stage SHA required');
const output = process.argv[execute ? 4 : 2];
assert(output?.startsWith('/'), 'Absolute evidence directory required');
fs.mkdirSync(output, { recursive: true });
const token = fs.readFileSync('/Users/deniscivkunov/Projects/WMS/.secrets/staging-token.txt','utf8').trim().replace(/^Bearer\s+/i,'');
const evidence = { mode: execute ? 'actual_invoice' : 'read_only_preparation', sha, started: new Date().toISOString(), requests: [], pageErrors: [], blocked: [] };
let ownInvoice, browser, activePage;
const save = () => fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(evidence,null,2));
async function api(p) {
  const response = await fetch(`${WEB}/api${p}`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(45000) });
  assert(response.ok, `GET ${p}: ${response.status}`);
  return response.json();
}
async function main() {
  const me = await api('/auth/me'); assert.equal(me.tenant_id,TENANT); assert.equal(me.role,'fulfillment_admin');
  evidence.auth = { tenant: me.tenant_id, role: me.role };
  const sellers = await api('/sellers'); const seller = sellers.find(s=>s.id===SELLER); assert(seller);
  evidence.seller = { id: seller.id, name: seller.name };
  evidence.beforeInvoices = await api(`/billing/invoices-v2?seller_id=${SELLER}&limit=200`);
  const params = new URLSearchParams({date_from:'2026-08-01',date_to:'2026-09-09',include_finance:'true',limit:'100'});
  const entries=[];
  do {
    const page = await api(`/billing/seller-report/sellers/${SELLER}/details?${params}`);
    entries.push(...page.entries);
    if (!page.next_cursor) break;
    params.set('cursor',page.next_cursor);
  } while (true);
  evidence.available = entries.filter(e=>e.source_type==='fbs_order').map(e=>({id:e.id,source_id:e.source_id,service:e.service_code,result:e.result,ledger:e.billing_ledger_entry_id,amount:e.amount_kopecks}));
  save();
  browser = await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:1050},reducedMotion:'reduce'});
  await context.addInitScript(({origin,value})=>{if(location.origin===origin)localStorage.setItem('wms_token_ff',value)}, {origin:WEB,value:token});
  await context.route('**/*',async route=>{
    const r=route.request(),url=new URL(r.url());
    if(!['GET','HEAD','OPTIONS'].includes(r.method())) {
      const body=r.postData() ? r.postDataJSON() : null;
      const allowed=execute && url.origin===WEB && r.method()==='POST' && (
        (['/api/billing/invoices-v2/preview','/api/billing/invoices-v2'].includes(url.pathname) && body?.seller_id===SELLER)
        || (ownInvoice && url.pathname===`/api/billing/invoices-v2/${ownInvoice}/cancel`));
      if(!allowed){evidence.blocked.push({method:r.method(),path:url.pathname});return route.abort();}
      evidence.requests.push({method:r.method(),path:url.pathname,body});
    }
    return route.continue();
  });
  const page=await context.newPage(); activePage=page; page.on('pageerror',e=>evidence.pageErrors.push(e.message));
  await page.goto(`${WEB}/app/ff/billing`);
  await page.getByTestId('ff-billing-screen').waitFor({timeout:45000});
  await page.getByRole('button',{name:'30 дней',exact:true}).click();
  // Read current operator controls before choosing the one exact QA seller.
  await page.getByTestId('billing-seller').selectOption(SELLER);
  await page.getByTestId(`billing-seller-summary-expand-${SELLER}`).click();
  await page.getByTestId('billing-pick-section-fbs').waitFor({timeout:60000});
  await page.screenshot({path:path.join(output,'01-seller-fbs.png'),animations:'disabled'});
  evidence.visibleBefore=await page.getByTestId('ff-billing-screen').innerText(); save();
  if(!execute) return;
  await page.getByTestId('billing-pick-section-fbs').check();
  const firstPreview=page.waitForResponse(r=>r.url().endsWith('/billing/invoices-v2/preview')&&r.request().method()==='POST');
  await page.getByTestId('billing-issue-invoice').click();
  const first=await firstPreview; assert.equal(first.status(),200); evidence.initialPreview=await first.json();
  await page.getByTestId('billing-invoice-preview').waitFor();
  await page.screenshot({path:path.join(output,'02-original-preview.png'),animations:'disabled'});
  const finalAmount='407.23';
  await page.getByTestId('billing-invoice-final-amount').fill(finalAmount);
  const amendedResponse=page.waitForResponse(r=>r.url().endsWith('/billing/invoices-v2/preview')&&r.request().method()==='POST');
  await page.getByTestId('billing-invoice-apply-final').click();
  const amended=await amendedResponse; assert.equal(amended.status(),200); evidence.adjustedPreview=await amended.json();
  assert.equal(evidence.adjustedPreview.total_amount_kopecks,40723);
  assert.deepEqual(evidence.adjustedPreview.lines.slice(0,evidence.initialPreview.lines.length).map(l=>[l.description,l.total_amount_kopecks]),evidence.initialPreview.lines.map(l=>[l.description,l.total_amount_kopecks]),'Original calculation must remain unchanged');
  await page.screenshot({path:path.join(output,'03-explicit-total.png'),animations:'disabled'});
  const createdResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/billing/invoices-v2'&&r.request().method()==='POST');
  await page.getByTestId('billing-invoice-save').click();
  const created=await createdResponse; assert.equal(created.status(),201); evidence.created=await created.json(); ownInvoice=evidence.created.id; save();
  assert.equal(evidence.created.total_amount_kopecks,40723);
  await page.screenshot({path:path.join(output,'04-issued.png'),animations:'disabled'});
  await page.getByTestId('billing-invoice-preview').getByRole('button',{name:'Закрыть',exact:true}).click();
  await page.getByTestId('billing-tab-invoices').click();
  await page.getByTestId(`billing-invoice-open-${ownInvoice}`).click();
  await page.getByTestId('billing-invoice-dialog').waitFor();
  evidence.reopened=await api(`/billing/invoices-v2/${ownInvoice}`);
  assert.deepEqual(evidence.reopened.lines,evidence.created.lines);
  const popupPromise=page.waitForEvent('popup'); await page.getByTestId('billing-invoice-print').click();
  const popup=await popupPromise; await popup.waitForLoadState('domcontentloaded');
  evidence.printText=await popup.locator('body').innerText();
  assert(evidence.printText.includes('407') && evidence.printText.includes('23'));
  await popup.screenshot({path:path.join(output,'05-print.png')}); await popup.close();
  await page.getByTestId('billing-invoice-cancel').click();
  const cancellation=page.waitForResponse(r=>r.url().endsWith(`/billing/invoices-v2/${ownInvoice}/cancel`));
  await page.getByTestId('billing-invoice-cancel-confirm').click();
  assert.equal((await cancellation).status(),200);
  evidence.cancelled=await api(`/billing/invoices-v2/${ownInvoice}`); assert.equal(evidence.cancelled.status,'cancelled');
  await page.screenshot({path:path.join(output,'06-cancelled.png'),animations:'disabled'});
  assert.equal(evidence.pageErrors.length,0); assert.equal(evidence.blocked.length,0);
  evidence.result='PASS';
}
main().catch(async error=>{evidence.error=String(error); process.exitCode=1; if(activePage){evidence.failureText=await activePage.locator('body').innerText().catch(()=>null);await activePage.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});}}).finally(async()=>{
  if(ownInvoice && evidence.cancelled?.status!=='cancelled') {
    const r=await fetch(`${WEB}/api/billing/invoices-v2/${ownInvoice}/cancel`,{method:'POST',headers:{Authorization:`Bearer ${token}`},signal:AbortSignal.timeout(30000)}).catch(()=>null);
    evidence.cleanupFallback={invoiceId:ownInvoice,httpStatus:r?.status??null};
    if(r?.ok)evidence.cancelled=await r.json();
  }
  if(browser)await browser.close(); evidence.finished=new Date().toISOString(); save(); console.log(JSON.stringify({result:evidence.error?'INCOMPLETE':(evidence.result??(execute?'INCOMPLETE':'READ_ONLY_PREPARED')),error:evidence.error,ownInvoice,output}));});
