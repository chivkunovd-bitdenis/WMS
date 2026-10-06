// One public-only browser attempt on GitHub Linux; no login, seller or credentials.
import {spawn} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
if(process.env.GITHUB_ACTIONS!=='true'||process.platform!=='linux')throw Error('GitHub Linux only');
const dir=process.env.C17_OUTPUT;await mkdir(dir,{recursive:true});
const report={fetched_at_utc:new Date().toISOString(),probe_sha:process.env.GITHUB_SHA,source_url:'https://docs.ozon.ru/api/seller/',result:'UNKNOWN',network:[]};
const allowed=new Set(['docs.ozon.ru','st.ozone.ru']);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let ws,chrome,sequence=0;const pending=new Map();let ready;
function send(method,params={}){return ready.then(()=>new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},8000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));}));}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error('Public-page evaluation failed');return r.result.value;}
try{
 chrome=spawn('google-chrome',['--headless=new','--no-sandbox','--disable-gpu','--disable-background-networking','--disable-component-update','--no-first-run','--remote-debugging-port=16665',`--user-data-dir=${process.env.RUNNER_TEMP}/wms663-public-profile`,'about:blank'],{stdio:'ignore'});
 let tabs;for(let i=0;i<100;i++){try{tabs=await(await fetch('http://127.0.0.1:16665/json/list')).json();break;}catch{await sleep(100);}}
 if(!tabs?.length)throw Error('Browser did not start');
 ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);ready=new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
 ws.onmessage=async e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(p){clearTimeout(p.timer);m.error?p.reject(Error('CDP error')):p.resolve(m.result);}return;}
  if(m.method==='Fetch.requestPaused'){const {requestId,request}=m.params;let permit=false;try{const u=new URL(request.url);permit=u.protocol==='https:'&&allowed.has(u.hostname)&&!u.username&&!u.password&&(request.method==='GET'||request.method==='HEAD'||(request.method==='POST'&&u.hostname==='docs.ozon.ru'&&u.pathname.startsWith('/abt/')));}catch{}try{await send(permit?'Fetch.continueRequest':'Fetch.failRequest',permit?{requestId}:{requestId,errorReason:'BlockedByClient'});}catch{} }
  if(m.method==='Network.responseReceived'){const r=m.params.response;try{const u=new URL(r.url);if(allowed.has(u.hostname))report.network.push({url:r.url,http_status:r.status,mime_type:r.mimeType});}catch{}}
 };
 await send('Page.enable');await send('Network.enable');await send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
 report.browser=await send('Browser.getVersion');await send('Page.navigate',{url:report.source_url});
 // Let the site's own scripts run once. No captcha solving, retries or login.
 await sleep(35000);
 report.page=await evaluate('({url:location.href,title:document.title,text:document.body.innerText.slice(0,700)})');
 const result=await evaluate(`(async()=>{try{const r=await fetch('/api/seller/swagger.json');const raw=await r.text();return{status:r.status,url:r.url,content_type:r.headers.get('content-type'),raw:r.ok?raw:null};}catch(e){return{error:String(e)}}})()`);
 report.schema_response={http_status:result.status,url:result.url,content_type:result.content_type,error:result.error};
 if(result.raw){const spec=JSON.parse(result.raw);const paths={};for(const p of ['/v6/fbs/posting/product/exemplar/set','/v5/fbs/posting/product/exemplar/status']){if(!spec.paths?.[p])throw Error('Required official path missing');paths[p]=spec.paths[p];}
  const schemas=spec.components?.schemas??{},kept={},refs=new Set();function collect(v){if(Array.isArray(v))v.forEach(collect);else if(v&&typeof v==='object'){if(v.$ref?.startsWith('#/components/schemas/'))refs.add(v.$ref.split('/').pop());Object.values(v).forEach(collect);}}
  collect(paths);while([...refs].some(n=>!Object.hasOwn(kept,n))){const n=[...refs].find(n=>!Object.hasOwn(kept,n));if(!Object.hasOwn(schemas,n))throw Error('Unresolved official schema');kept[n]=schemas[n];collect(kept[n]);}
  await writeFile(`${dir}/browser-official-schema-excerpt.json`,JSON.stringify({openapi:spec.openapi,info:spec.info,paths,components:{schemas:kept}},null,2)+'\n');report.result='OFFICIAL_SCHEMA_FETCHED_NOT_ACCEPTANCE';
 }
}catch(e){report.failure=String(e);}
finally{ws?.close();chrome?.kill();await writeFile(`${dir}/browser-metadata.json`,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({result:report.result,failure:report.failure,page:report.page,schema_response:report.schema_response}));}
