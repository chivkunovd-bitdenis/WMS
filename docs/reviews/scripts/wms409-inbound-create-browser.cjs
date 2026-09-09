'use strict';
// One-off local actual Chrome component check; synthetic callbacks, no API writes.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'../../..'),front=path.join(root,'frontend');
const output=process.argv[2];assert(output?.startsWith('/'));fs.mkdirSync(output,{recursive:true});
const harness=path.join(front,'wms409-qa.html');
const html=`<html><body><div id="root"></div><script type="module">
import React from 'react';import {createRoot} from 'react-dom/client';
import {ThemeProvider,CssBaseline} from '@mui/material';import {muiTheme} from '/src/mui/theme';
import {FfInboundQueuePage} from '/src/screens/ff/FfInboundQueuePage';
const h=React.createElement;
function App(){const [mode,setMode]=React.useState('warehouse');return h(ThemeProvider,{theme:muiTheme},h(CssBaseline),
 h('select',{'data-testid':'qa-mode',value:mode,onChange:e=>setMode(e.target.value)},['warehouse','server','null','success'].map(v=>h('option',{key:v,value:v},v))),
 h(FfInboundQueuePage,{workspace:'reception',rows:[],sellers:[{id:'synthetic-seller',name:'QA WMS409'}],onOpen:()=>{},onCreateDraft:async()=>{if(mode==='warehouse')throw new Error('Склад ФФ не найден.');if(mode==='server')throw new Error('seller_not_found');if(mode==='null')return null;return {id:'synthetic-document'};}}));}
createRoot(document.getElementById('root')).render(h(App));</script></body></html>`;
let browser,server;const evidence={scope:'local real component; synthetic failure/success callbacks; no warehouse/API mutations',cases:[],pageErrors:[],requests:[]};
(async()=>{
 fs.writeFileSync(harness,html,{flag:'wx'});
 server=spawn(process.execPath,[path.join(front,'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5197','--strictPort'],{cwd:front,stdio:'ignore'});
 for(let n=0;n<50;n++){if(await fetch('http://127.0.0.1:5197/wms409-qa.html').then(r=>r.ok).catch(()=>false))break;await new Promise(r=>setTimeout(r,200));}
 browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:900}});page.on('pageerror',e=>evidence.pageErrors.push(e.message));
 await page.route('**/*',route=>{const r=route.request();if(!['GET','HEAD'].includes(r.method())||new URL(r.url()).hostname!=='127.0.0.1'){evidence.requests.push({method:r.method(),url:r.url()});return route.abort();}return route.continue();});
 await page.goto('http://127.0.0.1:5197/wms409-qa.html');
 await page.getByRole('button',{name:'Создать приёмку',exact:true}).click();
 const dialog=page.getByTestId('ff-inbound-create-dialog');await dialog.waitFor();
 await page.getByTestId('ff-inbound-create-confirm').click();
 await page.getByTestId('ff-inbound-create-error').filter({hasText:'Склад ФФ не найден.'}).waitFor();assert(await dialog.isVisible());
 evidence.cases.push({name:'missing warehouse',error:await page.getByTestId('ff-inbound-create-error').innerText(),dialogOpen:true});
 await page.screenshot({path:path.join(output,'missing-warehouse.png'),animations:'disabled'});
 // Change only the synthetic backend result; the selected seller stays in the real dialog.
 await page.getByTestId('qa-mode').selectOption('server',{force:true});await page.getByTestId('ff-inbound-create-confirm').click();
 await page.getByTestId('ff-inbound-create-error').filter({hasText:'seller_not_found'}).waitFor();assert(await dialog.isVisible());
 evidence.cases.push({name:'API failure',error:await page.getByTestId('ff-inbound-create-error').innerText(),dialogOpen:true});
 await page.getByTestId('qa-mode').selectOption('null',{force:true});await page.getByTestId('ff-inbound-create-confirm').click();
 await page.getByTestId('ff-inbound-create-error').filter({hasText:'Документ не создан.'}).waitFor();assert(await dialog.isVisible());
 evidence.cases.push({name:'null result',dialogOpen:true});
 await page.getByTestId('qa-mode').selectOption('success',{force:true});await page.getByTestId('ff-inbound-create-confirm').click();await dialog.waitFor({state:'hidden'});evidence.cases.push({name:'successful create',dialogOpen:false});
 await page.getByRole('button',{name:'Создать приёмку',exact:true}).click();await dialog.waitFor();assert.equal(await page.getByTestId('ff-inbound-create-error').count(),0);await page.getByTestId('ff-inbound-create-cancel').click();
 assert.equal(evidence.pageErrors.length,0);assert.equal(evidence.requests.length,0);evidence.result='PASS';
})().catch(async e=>{evidence.error=String(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill('SIGTERM');if(fs.existsSync(harness))fs.unlinkSync(harness);evidence.finished=new Date().toISOString();fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));});
