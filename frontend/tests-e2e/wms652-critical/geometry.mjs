// WMS652 C59 real Chrome geometry. Existing product components remain unmocked.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {workspace,selectionFixtures} from './fixtures.mjs';
const longName=' — длинное название товара, коллекция осень, комплект повседневной одежды с подробным описанием';
const longSeller='Синтетический селлер с очень длинным названием для проверки читаемости и принадлежности';
const longRoute='Склад / сортировочный центр — длинный маршрут сдачи с проверкой читаемости';
const longSize='44/46/48/50/52/54';
export const packingEntries=[
 ['wb-single','supply_id=wb-a',['wb-a']],['wb-group-one','supply_ids=wb-a',['wb-a']],
 ['wb-group-many','supply_ids=wb-a,wb-b',['wb-a','wb-b']],
 ['ozon-single','supply_id=ozon-a',['ozon-a']],['ozon-group-one','supply_ids=ozon-a',['ozon-a']],
 ['ozon-group-many','supply_ids=ozon-a,ozon-b',['ozon-a','ozon-b']],
 ['mixed-group-many','supply_ids=wb-a,ozon-a',['wb-a','ozon-a']],
];
export const geometryIds=packingEntries.map(([id])=>`WMS652.geometry[${id};1600x1000-long]`)
 .concat(['WMS652.geometry[orders-expired;1600x1000-long]','WMS652.geometry[orders-cancelled;1600x1000-long]','WMS652.geometry[selection;1600x1000-long]']);
function longOrder(o){o.product.name+=longName;o.product.size=longSize;o.seller.name=longSeller;
 o.delivery_route=longRoute;o.deadline_at='2026-10-31T23:59:00Z';
 for(const p of o.positions){p.name+=longName;p.size=longSize;}return o;}
function packingData(ids){return Object.fromEntries(ids.map(id=>{const w=workspace(id,id.startsWith('ozon')?'ozon':'wb');
 w.supply.seller.name=longSeller;w.supply.name+=' — длинное имя поставки';w.supply.nearest_deadline_at='2026-10-31T23:59:00Z';
 w.orders.forEach(o=>{longOrder(o);o.metadata.required=['sgtin'];o.pack.status='packed'});w.progress.packed=1;
 return[id,w];}));}
function selectionData(){const d=selectionFixtures();d.orders.forEach(longOrder);return d;}
const metrics=`(()=>{
 const b=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}};
 const overlap=(a,c)=>a.x<c.right-1&&c.x<a.right-1&&a.y<c.bottom-1&&c.y<a.bottom-1;
 const rowList=[...document.querySelectorAll('[data-order-id]')];
 const label=(row,text)=>[...row.querySelectorAll('span,p')].find(e=>e.textContent.trim()===text);
 const named=e=>({text:e.textContent,bounds:b(e),scrollWidth:e.scrollWidth,clientWidth:e.clientWidth});
 const rows=rowList.map(row=>{const size=row.querySelector('[data-testid="fbs-packing-size"]'),mark=row.querySelector('[data-testid="fbs-packing-marking-available"]'),sticker=label(row,'Стикер')?.parentElement,cis=label(row,'ЧЗ')?.parentElement,actions=row.lastElementChild;
 const columns={size:size&&b(size),marking:mark&&b(mark),sticker:sticker&&b(sticker),cis:cis&&b(cis),actions:b(actions)};
 return {id:row.dataset.orderId,text:row.innerText,bounds:b(row),columns,
 sizeCells:[...row.querySelectorAll('[data-testid="fbs-packing-size"]')].map(named),
 names:[...row.querySelectorAll('[data-testid="fbs-packing-size"]')].map(s=>named(s.previousElementSibling)),
 buttons:[...actions.querySelectorAll('button')].map(e=>({text:e.innerText,aria:e.getAttribute('aria-label'),disabled:e.disabled,bounds:b(e)}))};});
 const bar=document.querySelector('[data-testid="fbs-unified-scan"]');
 const controls=bar?[bar.querySelector('[data-packing-scan]')?.closest('.MuiFormControl-root'),
 ...bar.querySelectorAll('label[data-testid]'),bar.querySelector('[data-testid="label-size-select"]'),bar.querySelector('[data-testid="fbs-scan-undo"]')].filter(Boolean):[];
 const controlBounds=controls.map(b),qr=bar?.querySelector('[data-testid="fbs-scan-print-qr-toggle"] input');
 return {viewport:{width:innerWidth,height:innerHeight},rows,bar:bar&&b(bar),controls:controls.map(named),
 controlOverlap:controlBounds.some((a,i)=>controlBounds.slice(i+1).some(c=>overlap(a,c))),
 rowOverlap:rows.some((a,i)=>rows.slice(i+1).some(c=>overlap(a.bounds,c.bounds))),
 bars:document.querySelectorAll('[data-testid="fbs-unified-scan"]').length,
 lists:document.querySelectorAll('[data-testid="fbs-unified-packing-rows"]').length,
 qr:qr&&{checked:qr.checked,disabled:qr.disabled},
 text:document.body.innerText};})()`;
export async function geometryContracts(ctx){
 const {cdp,evaluate,until,click,clickElement,report,dir,origin,startPacking,startSelection,logs,isolate}=ctx;
 let lastMeasurement;
 const pause=ms=>new Promise(r=>setTimeout(r,ms));
 async function save(id,measurements){const stem=id.replaceAll(/[^a-zA-Z0-9_-]/g,'-');
  await writeFile(`${dir}/${stem}.json`,JSON.stringify({measurements,...logs()},null,2));
  const png=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  await writeFile(`${dir}/${stem}.png`,Buffer.from(png.data,'base64'));}
 async function run(id,fn){await isolate(id);report.currentCase=id;lastMeasurement=undefined;let result;
  try{result=await fn();assert.equal(logs().blocked.length,0);assert.equal(logs().errors.length,0);report.cases.push({id,status:'PASS'});console.log(`${id}: PASS`);}
  catch(e){report.cases.push({id,status:'FAIL',failure:String(e)});console.error(`${id}: ${e}`);}
  await save(id,result??lastMeasurement??await evaluate(metrics));
 }
 const stageButton=(root,name)=>`[...document.querySelectorAll('${root} [role=tab]')].find(e=>e.textContent.startsWith('${name}'))`;
 for(const [name,query,ids] of packingEntries)await run(`WMS652.geometry[${name};1600x1000-long]`,async()=>{
  startPacking(packingData(ids));await cdp.send('Page.navigate',{url:`${origin}/app/ff/fbs?${query}&flag=qr`});
  await until(`document.querySelectorAll('[data-order-id]').length===${ids.length}&&[...document.querySelectorAll('[data-order-id]')].every(r=>r.querySelector('[data-testid="fbs-packing-size"]')&&r.querySelector('[data-testid="fbs-packing-marking-available"]'))`);
  await evaluate('document.fonts.ready.then(()=>true)');await pause(200);
  const m=await evaluate(metrics);lastMeasurement=m;assert.deepEqual(m.viewport,{width:1600,height:1000});
  assert.equal(m.bars,1,'one reachable common scan bar');assert.equal(m.lists,1);assert.equal(m.controlOverlap,false,'scan controls must not overlap');assert.equal(m.rowOverlap,false,'packing rows must not overlap');
  assert(!/Начать работу с поставкой|Завершить работу с поставкой/.test(m.text),'no returned assembly activation gate');
  const ozonOnly=ids.every(id=>id.startsWith('ozon'));assert.equal(m.qr.disabled,ozonOnly);assert.equal(m.qr.checked,!ozonOnly);
  if(query.startsWith('supply_id='))assert(m.text.includes('упаковано 1 из 1'),'existing standalone packed counter remains visible');
  else assert(new RegExp('из '+ids.length+' подготовлено к отгрузке').test(m.text),'existing group readiness summary remains visible');
  for(const row of m.rows){const c=row.columns;assert(c.size&&c.marking&&c.sticker&&c.cis,'size/sticker/CIS columns exist');
   assert(c.size.right<=c.marking.x+1&&c.marking.right<=c.sticker.x+1&&c.sticker.right<=c.cis.x+1&&c.cis.right<=c.actions.x+1,'packing columns must not overlap');
   assert(row.text.includes('Размер')&&row.text.includes(longSize)&&row.text.includes('Доступно ЧЗ')&&row.text.includes('Стикер'),'named size/sticker/CIS columns remain readable');
   for(const cell of row.sizeCells)assert(cell.bounds.width>0&&cell.bounds.height>0&&cell.scrollWidth<=cell.clientWidth+1,'long size remains within its column');
   for(const cell of row.names)assert(cell.bounds.width>0&&cell.bounds.height>0&&cell.text.includes(longName)&&cell.scrollWidth<=cell.clientWidth+1,'long product name does not overflow into size');
   const wb=row.id.startsWith('wb');assert.equal(row.buttons.filter(b=>b.text==='QR').length,wb?1:0,'row QR action belongs only to WB');
   assert.equal(row.buttons.filter(b=>b.aria==='Печать ЧЗ и ШК').length,1);
   const expr=`document.querySelector('[data-order-id="${row.id}"] button[aria-label="Печать ЧЗ и ШК"]')`;
   await clickElement(expr,`${row.id} print action`);await until(`document.querySelector('[data-testid="marking-print-confirm"]')`);
   const before=logs().requestLog.filter(r=>r.path.endsWith('/order-print-tape')).length;
   await click('[data-testid="marking-print-confirm"]');
   for(let i=0;i<50&&logs().requestLog.filter(r=>r.path.endsWith('/order-print-tape')).length===before;i++)await pause(100);
   const intent=logs().requestLog.filter(r=>r.path.endsWith('/order-print-tape')).at(-1);
   assert(intent&&intent.body.order_ids.includes(row.id));assert.equal(intent.body.include_order_qr,false,'manual CIS/barcode action excludes order QR; WB has its separate QR action');
   await until(`document.querySelector('[data-testid="marking-print-error"]')`);
   await clickElement(`[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent==='Отмена')`,'print cancel');
   await until(`!document.querySelector('[data-testid="marking-print-confirm"]')`);
   if(wb){const prior=logs().requestLog.filter(r=>r.path.endsWith('/print-assets')).length;
    await clickElement(`[...document.querySelectorAll('[data-order-id="${row.id}"] button')].find(e=>e.textContent==='QR')`,`${row.id} QR action`);
    for(let i=0;i<50&&logs().requestLog.filter(r=>r.path.endsWith('/print-assets')).length===prior;i++)await pause(100);
    const qrIntent=logs().requestLog.filter(r=>r.path.endsWith('/print-assets')).at(-1);
    assert(qrIntent&&qrIntent.path===`/operations/fbs-supplies/${row.id.replace(/-order$/,'')}/print-assets`);
    assert.deepEqual(qrIntent.body,{kind:'order_sticker',order_ids:[row.id],retry_missing:false});
   }
  }
  if(m.rows.length>1){for(const key of ['size','marking','sticker','cis','actions'])assert(Math.max(...m.rows.map(r=>r.columns[key].x))-Math.min(...m.rows.map(r=>r.columns[key].x))<=1,`mixed/common ${key} columns stay aligned`);}
  // Input reachability by the same real pointer helper; no synthetic scan/printer job needed.
  await click('[data-testid="fbs-unified-scan"] [data-packing-scan]');
  assert(await evaluate(`document.activeElement?.matches('[data-packing-scan]')`));
  const root=ids.length===1&&query.startsWith('supply_id=')?'[data-testid="fbs-workspace"]':'[data-testid="fbs-assembly"]';
  for(const tab of ['Подбор','Короба','Упаковка и маркировка']){const expression=stageButton(root,tab);await clickElement(expression,`${name} ${tab}`);
   await until(`(${expression})?.getAttribute('aria-selected')==='true'`);
  }
  await until(`document.querySelector('[data-testid="fbs-unified-scan"] [data-packing-scan]')&&!document.querySelector('[data-testid="fbs-unified-scan"] [data-packing-scan]').disabled`);
  assert.equal(logs().printLog.length,0,'synthetic no-asset print must not dispatch native jobs');return m;
 });
 for(const [group,label] of [['expired','Просрочены'],['cancelled','Отменённые']])await run(`WMS652.geometry[orders-${group};1600x1000-long]`,async()=>{
  const d=selectionData();d.orders=d.orders.slice(0,2);d.orders.forEach(o=>{o.status=group==='cancelled'?'cancelled':'assembling';o.supply_id=null;});
  startSelection(d,true);await cdp.send('Page.navigate',{url:`${origin}/app/ff/fbs`});
  await until(`document.querySelector('[data-testid="fbs-worklist-table"]')`);
  await clickElement(`[...document.querySelectorAll('[role=tab]')].find(e=>e.textContent==='${label}')`,label);
  await until(`document.querySelector('[data-testid="fbs-worklist-table"] thead').innerText.includes('Статус')&&document.querySelector('[data-testid="fbs-order-order-a"]')`);
  const m=await evaluate(`(()=>{const table=document.querySelector('[data-testid="fbs-worklist-table"]'),b=e=>{const r=e.getBoundingClientRect();return{x:r.x,right:r.right,y:r.y,bottom:r.bottom,width:r.width,height:r.height}};
   return{headers:[...table.querySelectorAll('thead th')].map(e=>({text:e.innerText,bounds:b(e)})),rows:[...table.querySelectorAll('tbody tr')].map(r=>({id:r.dataset.testid,cells:[...r.children].map(e=>({text:e.innerText,bounds:b(e)}))}))};})()`);
  lastMeasurement=m;assert.deepEqual(m.headers.map(h=>h.text),['','Товар','Артикул продавца','Размер','ШК','Селлер','Маршрут сдачи','Прошло с заказа','Статус']);
  for(const cells of [m.headers,...m.rows.map(r=>r.cells)])for(let i=1;i<cells.length;i++)assert(cells[i-1].bounds.right<=cells[i].bounds.x+1,'order table columns must not overlap');
  const route='[data-testid="fbs-order-order-a-delivery-route"]';await clickElement(`document.querySelector('${route}')`,'long route');
  await until(`document.querySelector('[role=tooltip]')?.textContent===${JSON.stringify(longRoute)}`);
  assert(logs().requestLog.some(r=>r.path.includes('/fbs-orders/worklist?')&&r.path.includes(`status_group=${group}`)));
  return m;
 });
 await run('WMS652.geometry[selection;1600x1000-long]',async()=>{
  startSelection(selectionData());await cdp.send('Page.navigate',{url:`${origin}/app/ff/fbs`});
  await until(`document.querySelector('[data-testid="fbs-order-order-a2"]')`);
  for(const id of ['order-a2','order-a'])await clickElement(`document.querySelector('[data-testid="fbs-order-${id}"] input').closest('[class*="MuiCheckbox-root"]')`,`long select ${id}`);
  const m=await evaluate(`(()=>{const bar=document.querySelector('[data-testid="fbs-selection-bar"]'),b=e=>{const r=e.getBoundingClientRect();return{x:r.x,right:r.right,y:r.y,bottom:r.bottom}};
   return{controls:[...bar.firstElementChild.children].map(e=>({text:e.innerText,bounds:b(e)}))};})()`);
  lastMeasurement=m;for(let i=1;i<m.controls.length;i++)assert(m.controls[i-1].bounds.right<=m.controls[i].bounds.x+1,'long selection text/buttons must not overlap');
  await click('[data-testid="fbs-selected-open"]');await until(`document.querySelector('[data-testid="fbs-selected-list"]')`);
  assert(await evaluate(`document.querySelector('[data-testid="fbs-selected-list"]').textContent.includes(${JSON.stringify(longName)})`));
  await clickElement(`[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent==='Закрыть')`,'selected close');
  await clickElement(`[...document.querySelectorAll('[data-testid="fbs-selection-bar"] button')].find(e=>e.textContent==='Сформировать поставку')`,'long create');
  await until(`document.querySelector('[data-testid="fbs-create-submit"]')&&!document.querySelector('[data-testid="fbs-create-submit"]').disabled`);
  assert.deepEqual(logs().requestLog.filter(r=>r.path.endsWith('/preflight')).at(-1).body.order_ids,['order-a2','order-a']);
  await clickElement(`[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent==='Отмена')`,'create cancel');
  await click('[data-testid="fbs-05-add-existing-open"]');await until(`document.querySelector('[data-testid="fbs-05-existing-supply-select"]')`);
  await clickElement(`[...document.querySelectorAll('[role=dialog] button')].find(e=>e.textContent==='Отмена')`,'add cancel');
  return m;
 });
}
