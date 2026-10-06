// Reuse frozen fixture builders without importing tests or changing product source.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
const source = readFileSync('frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx','utf8');
const builders = source.slice(source.indexOf('const SUPPLY_ID'),source.indexOf('const originalFetch'));
if (!builders.includes('function workspace()') || !builders.includes('const documentState')) throw Error('fixture boundaries changed');
const dir='frontend/.wms663-proof'; mkdirSync(dir,{recursive:true});
writeFileSync(`${dir}/index.html`,'<!doctype html><html><head><meta charset="utf-8"></head><body><div id="root"></div><script type="module" src="/main.tsx"></script></body></html>');
writeFileSync(`${dir}/main.tsx`, `import React from 'react';
import {createRoot} from 'react-dom/client';
import {ThemeProvider} from '@mui/material/styles';
import {muiTheme} from '../src/mui/theme';
import {FfFbsSupplyWorkspace} from '../src/screens/v2/FfFbsSupplyWorkspace';
import type {FbsWorkspace} from '../src/screens/v2/fbsApi';
${builders}
const longName='Очень длинное название импортного товара, подробное описание модели, размера, цвета и комплектации для проверки читаемости в существующем заказе Ozon';
const longNumber='0000/663-ABC-09/0123456789/0123456789/0123456789/0123456789/0123456789';
const w=workspace();
w.orders[0].product.name=longName; w.orders[0].positions![0].name=longName;
documentState.products[0].name=longName;
for(const p of documentState.products) for(const e of p.exemplars) { if(e.gtd_required)e.gtd=longNumber; if(e.rnpt_required)e.rnpt=longNumber; }
let durable=structuredClone(documentState);
const requests:any[]=[];
(window as any).proof={requests,longName,longNumber,fixture:{sku:2,units:3},render};
window.print=()=>{throw Error('Printing forbidden in WMS663 proof')};
window.open=()=>{throw Error('External windows forbidden in WMS663 proof')};
function json(body:unknown,status=200){return Promise.resolve(new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}}))}
window.fetch=async(input:RequestInfo|URL,init?:RequestInit)=>{
 const url=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url,location.href);
 const path=url.pathname.replace(/^\\/api/,''); const method=init?.method??'GET';
 const body=typeof init?.body==='string'?JSON.parse(init.body):null;
 requests.push({path,method,body});
 if(path===DOCUMENTS_PATH && method==='GET')return json(durable);
 if(path===DOCUMENTS_PATH && method==='PUT'){
  await new Promise(r=>setTimeout(r,250));
  durable.state='rejected';durable.version++;
  const p=durable.products.find(p=>p.product_id===body.product_id)!;
  const e=p.exemplars.find(e=>e.exemplar_id===body.exemplar_id)!;
  Object.assign(e,{gtd:body.gtd??'',rnpt:body.rnpt??'',is_gtd_absent:body.is_gtd_absent,is_rnpt_absent:body.is_rnpt_absent,state:'rejected',errors:['gtd_invalid']});
  return json(durable);
 }
 if(path.startsWith('/operations/packaging-tasks/'))return json(packagingTask);
 if(path==='/operations/fbs-supplies/'+SUPPLY_ID+'/workspace')return json(w);
 return json(null);
};
let root=createRoot(document.getElementById('root')!);let generation=0;
function render(){root.render(<ThemeProvider theme={muiTheme}><FfFbsSupplyWorkspace key={++generation} token="synthetic-only" authHeaders={()=>({})} supplyId={SUPPLY_ID} initialWorkspace={w} open onClose={()=>{}}/></ThemeProvider>)}
render();
`);
writeFileSync(`${dir}/vite.config.mjs`, `import {defineConfig} from 'vite';import react from '@vitejs/plugin-react';import {resolve} from 'node:path';export default defineConfig({root:resolve('frontend/.wms663-proof'),plugins:[react()],server:{host:'127.0.0.1',port:16663,strictPort:true,fs:{allow:[resolve('frontend')]}},build:{outDir:resolve(process.env.RUNNER_TEMP,'wms663-ui-dist'),emptyOutDir:true}});`);
