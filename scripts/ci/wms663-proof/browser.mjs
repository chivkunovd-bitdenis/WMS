// GitHub Linux only; Chrome CDP reuses WMS666 runner pattern, no browser library.
import {spawn,execFileSync} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
if(process.env.GITHUB_ACTIONS!=='true'||process.platform!=='linux')throw Error('Only GitHub Linux runner is authorized');
const dir=process.env.WMS663_EVIDENCE;await mkdir(dir,{recursive:true});
const report={product:'1fd2d92dc30eb376c1d8a8e27238e52d963a196e',fixture:'d9e022697e098a2f9c0feee6a5bf03f99cac5945',probe:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),scope:'Real unchanged workspace/theme, synthetic fetch only; no deployed backend, live API, printer or external cycle',cases:[]};
const errors=[];let cdp,chromeLog='';
class CDP{
 constructor(url){this.ws=new WebSocket(url);this.next=0;this.pending=new Map();this.listeners=new Map();this.ready=new Promise((r,j)=>{this.ws.onopen=r;this.ws.onerror=j});this.ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=this.pending.get(m.id);this.pending.delete(m.id);if(p){clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}}else for(const f of this.listeners.get(m.method)??[])Promise.resolve(f(m.params)).catch(e=>errors.push(String(e)))}}
 async send(method,params={}){await this.ready;const id=++this.next;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{this.pending.delete(id);reject(Error('CDP timeout '+method))},12000);this.pending.set(id,{resolve,reject,timer});this.ws.send(JSON.stringify({id,method,params}))})}
 on(method,f){this.listeners.set(method,[...this.listeners.get(method)??[],f])}
}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function evaluate(expression){const r=await cdp.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function until(expr){const end=Date.now()+25000;while(Date.now()<end){if(await evaluate(`Boolean(${expr})`))return;await sleep(100)}throw Error('UI timeout '+expr)}
const button=name=>`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(name)})`;
const input=label=>`document.querySelector('input[aria-label="${label}"]')`;
async function click(expr){await until(expr);await evaluate(`(${expr}).click()`);await sleep(400)}
async function capture(name){await writeFile(`${dir}/${name}.png`,Buffer.from((await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true})).data,'base64'));await writeFile(`${dir}/${name}.html`,await evaluate('document.documentElement.outerHTML'));await writeFile(`${dir}/${name}.ax.json`,JSON.stringify(await cdp.send('Accessibility.getFullAXTree'),null,2))}
async function openDocuments(){await click(button('ГТД / РНПТ'));await until(input('Номер ГТД · SKU 663001 · экземпляр 1'));await evaluate('document.fonts.ready.then(()=>true)');await sleep(350)}
const chrome=spawn('google-chrome',['--headless=new','--no-sandbox','--disable-gpu','--disable-background-networking','--disable-component-update','--no-first-run','--remote-debugging-port=16664',`--user-data-dir=${process.env.RUNNER_TEMP}/wms663-chrome-profile`,'about:blank'],{stdio:['ignore','pipe','pipe']});
chrome.stderr.on('data',d=>chromeLog+=d);chrome.stdout.on('data',d=>chromeLog+=d);chrome.on('error',e=>chromeLog+=String(e));
try{
 let tabs;for(let i=0;i<150;i++){try{tabs=await(await fetch('http://127.0.0.1:16664/json/list')).json();break}catch{await sleep(100)}}assert(tabs?.length,'Chrome did not start');
 cdp=new CDP(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
 cdp.on('Runtime.exceptionThrown',e=>errors.push(e.exceptionDetails));
 // Fail all browser network outside local static Vite assets. Product fetch is synthetic.
 cdp.on('Fetch.requestPaused',async({requestId,request})=>{const u=new URL(request.url);if(u.origin==='http://127.0.0.1:16663'&&!u.pathname.startsWith('/api/'))return cdp.send('Fetch.continueRequest',{requestId});errors.push('Unexpected network '+request.url);return cdp.send('Fetch.failRequest',{requestId,errorReason:'BlockedByClient'})});
 await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Accessibility.enable');await cdp.send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
 report.browser=await cdp.send('Browser.getVersion');
 for(const width of [1280,390]){
  await cdp.send('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:false});
  await cdp.send('Page.navigate',{url:'http://127.0.0.1:16663/'});await openDocuments();
  const geometry=await evaluate(`(()=>{
   const block=document.querySelector('[data-testid="ozon-documents-order-wms663"]');
   const bounds=e=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}};
   const rows=[...block.querySelectorAll('input:not([type="checkbox"])')].map(e=>{const field=e.closest('.MuiTextField-root');const row=field.parentElement;const label=row.querySelector('label.MuiFormControlLabel-root');const a=bounds(field),b=bounds(label);return{aria:e.getAttribute('aria-label'),value:e.value,input:bounds(e),field:a,checkboxLabel:b,overlap:a.x<b.right-1&&b.x<a.right-1&&a.y<b.bottom-1&&b.y<a.bottom-1,labelOverflow:label.scrollWidth>label.clientWidth+2,fieldOverflow:field.scrollWidth>field.clientWidth+2}});
   const controls=[...block.querySelectorAll('button')].map(e=>({label:e.getAttribute('aria-label')||e.textContent,bounds:bounds(e)}));
   return{width:innerWidth,block:bounds(block),rows,controls,text:block.innerText,fixture:window.proof.fixture,windowOverflow:document.documentElement.scrollWidth>innerWidth,context:document.body.innerText.includes('Ozon')};
  })()`);
  await writeFile(`${dir}/c18-${width}.geometry.json`,JSON.stringify(geometry,null,2));await capture(`c18-${width}`);
  assert.equal(geometry.fixture.sku,2);assert.equal(geometry.fixture.units,3);assert.equal(geometry.rows.length,3);assert(geometry.context);
  assert(geometry.text.includes(await evaluate('window.proof.longName')),'long product name absent');
  for(const row of geometry.rows){assert(row.value.startsWith('0000/')&&row.value.length>=60);assert(!row.overlap,`${width}: field/checkbox overlap`);assert(!row.labelOverflow,`${width}: checkbox label clipped`);assert(row.input.width>60,`${width}: input too narrow`)}
  assert(geometry.controls.every(c=>c.bounds.width>0&&c.bounds.height>0),'unreadable action');
  report.cases.push({case:'C18',width,status:'PASS',fixture:geometry.fixture,windowOverflow:geometry.windowOverflow});
 }
 // C16 supplemental original scenario: rejected -> correction -> refresh -> tab -> remount.
 const label='Номер ГТД · SKU 663001 · экземпляр 1';const field=input(label);
 const save=`document.querySelector('button[aria-label="Сохранить ГТД / РНПТ · SKU 663001 · экземпляр 1"]')`;
 async function enter(text){await evaluate(`(${field}).focus();(${field}).select()`);await cdp.send('Input.insertText',{text});await sleep(100)}
 await enter('001/ABC-09');await until(`!(${save}).disabled`);
 await evaluate(`(${save}).click();(${save}).click()`);await until(`document.body.textContent.includes('gtd_invalid')`);
 assert.equal(await evaluate(`window.proof.requests.filter(r=>r.method==='PUT').length`),1,'C10 UI double click must emit one PUT');
 await enter('001/ABC-10');await click(save);await until(`(${field}).value==='001/ABC-10'`);
 await click(button('Проверить в Ozon'));assert.equal(await evaluate(`(${field}).value`),'001/ABC-10');assert(await evaluate(`document.body.textContent.includes('gtd_invalid')`));
 // Actual keyboard navigation focus, then keyboard activate the existing tab.
 await evaluate(`document.querySelector('button[aria-label="Закрыть"]').focus()`);
 assert.equal(await evaluate(`document.activeElement.getAttribute('aria-label')`),'Закрыть');
 await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
 await evaluate(`(${button('Состав')}).focus()`);await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await sleep(400);
 await click(button('Упаковка и маркировка'));await until(button('ГТД / РНПТ'));
 if(!await evaluate(`${field} && (${field}).getBoundingClientRect().height>0`))await openDocuments();
 assert.equal(await evaluate(`(${field}).value`),'001/ABC-10');assert(await evaluate(`document.body.textContent.includes('gtd_invalid')`));
 await evaluate('window.proof.render()');await sleep(500);await openDocuments();
 assert.equal(await evaluate(`(${field}).value`),'001/ABC-10');assert(await evaluate(`document.body.textContent.includes('gtd_invalid')`));
 await capture('c16-refresh-tab-remount');
 report.cases.push({case:'C16 supplemental',status:'PASS',scope:'rejected/correct/save/GET refresh/keyboard tab/remount synthetic readback; order B remains untested'});
 report.cases.push({case:'C10 double UI click',status:'PASS',putCount:1});
 assert.equal(errors.length,0,'browser exceptions or forbidden network');report.status='PASS';
}catch(e){report.status='FAIL';report.failure=String(e);report.stack=e.stack;console.error(e);process.exitCode=1;if(cdp)try{await capture('failure')}catch{}}
finally{if(cdp)try{await writeFile(`${dir}/requests.json`,JSON.stringify(await evaluate('window.proof?.requests'),null,2))}catch{}await writeFile(`${dir}/result.json`,JSON.stringify({...report,errors},null,2));await writeFile(`${dir}/chrome.log`,chromeLog);cdp?.ws.close();chrome.kill()}
