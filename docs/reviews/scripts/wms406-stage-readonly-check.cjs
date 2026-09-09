'use strict';
// Read-only release check: exact existing QA tenant/seller/invoice; no POSTs.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const WEB='https://web-production-9e7c1.up.railway.app';
const TENANT='9c31f3f4-ce62-4c1f-891a-295b278f1e69';
const SELLER='50110328-fa03-4604-b2e4-8ca27fc8bb41';
const INVOICE='325b20ca-30d8-4e15-a2e1-a3d34b49d906';
const output=process.argv[2],sha=process.argv[3];
assert(output?.startsWith('/')&&/^[a-f0-9]{40}$/.test(sha));
const token=fs.readFileSync('/Users/deniscivkunov/Projects/WMS/.secrets/staging-token.txt','utf8').trim().replace(/^Bearer\s+/i,'');
async function get(p){const r=await fetch(WEB+'/api'+p,{headers:{Authorization:`Bearer ${token}`},signal:AbortSignal.timeout(30000)});assert.equal(r.status,200,`GET ${p}`);return r.json();}
(async()=>{
 const me=await get('/auth/me');assert.equal(me.tenant_id,TENANT);assert.equal(me.role,'fulfillment_admin');
 const invoice=await get('/billing/invoices-v2/'+INVOICE);assert.equal(invoice.seller_id,SELLER);assert.equal(invoice.status,'cancelled');assert.equal(invoice.total_amount_kopecks,40723);
 assert.deepEqual(invoice.lines.map(l=>l.total_amount_kopecks),[12500,100,28123]);
 const report=await get(`/billing/seller-report/sellers/${SELLER}/details?date_from=2026-08-11&date_to=2026-09-09&include_finance=true&limit=1`);
 assert(Array.isArray(report.entries));
 const health=await fetch('https://wms-production-780c.up.railway.app/health',{signal:AbortSignal.timeout(30000)});assert.equal(health.status,200);
 const web=await fetch(WEB,{signal:AbortSignal.timeout(30000)});assert.equal(web.status,200);
 const evidence={sha,checkedAt:new Date().toISOString(),result:'PASS',methods:['GET'],auth:{tenant:me.tenant_id,role:me.role},backendHealth:health.status,webHealth:web.status,invoice:{id:invoice.id,status:invoice.status,total:invoice.total_amount_kopecks,lines:invoice.lines},report:{seller:SELLER,http:200,returnedRows:report.entries.length,hasNext:!!report.next_cursor}};
 fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,JSON.stringify(evidence,null,2)+'\n');console.log(JSON.stringify({result:evidence.result,invoice:invoice.id,status:invoice.status,output}));
})().catch(e=>{console.error(String(e));process.exitCode=1});
