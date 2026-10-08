'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const directory = path.join(__dirname, '..');
const { launch } = require(path.join(directory, 'avpack-macos-launcher.js'));
const { createHelper } = require(path.join(directory, 'avpack-sold-kiz-filter.js'));
const url = 'https://wms.sellerfocus.pro/seller/honest-sign/withdrawals';
const ready = { status:'certificate_dialog_open', targetCount:1, noSend:true, signed:false, sent:false };
const identity = { tenant_id:'d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe', seller_id:'0b8da5d8-f43a-42f5-a2ec-43173ea844bd', active_seller_id:'0b8da5d8-f43a-42f5-a2ec-43173ea844bd', role:'fulfillment_seller', withdrawal_enabled:true };

test('SC21 default native launcher waits through cold 144 second registry using virtual clock', () => {
  let elapsed = 0, injected = 0;
  const chrome = { running:()=>true, tabs:()=>[{id:1,url}], evaluate(_id, source) {
    if (source.includes('cold-test-helper')) injected++;
    if (source.includes('WMS665_PROBE')) return 'null';
    return JSON.stringify(elapsed >= 144000 ? ready : {status:'running',signed:false,sent:false});
  }};
  const result = launch({chrome, helperSource:'/* cold-test-helper */', wait:()=>{elapsed+=250;}});
  assert.equal(result.status, 'certificate_dialog_open');
  assert.equal(elapsed, 144000);
  assert.equal(injected, 1);
});

test('SC21 generated native command uses a finite ten minute polling budget', () => {
  const command = fs.readFileSync(path.join(directory,'avpack-sold-kiz.command'),'utf8');
  assert.match(command, /maxPolls: 2400,/);
  assert.match(command, /sleepForTimeInterval\(0\.25\)/);
});

test('SC21 timeout cancels browser run and late completion cannot overwrite it with dialog success', () => {
  const context = vm.createContext({location:new URL(url)}, {microtaskMode:'afterEvaluate'});
  context.globalThis = context;
  const helperSource = `globalThis.AvpackSoldKizFilter={createHelper(options){ globalThis.helperOptions=options;return {run(){return new Promise(resolve=>{globalThis.finish=()=>resolve(${JSON.stringify(ready)})})}}}};`;
  let injections=0;
  const chrome={running:()=>true,tabs:()=>[{id:1,url}],evaluate(_id,source){
    if(source.includes(helperSource))injections++;
    return vm.runInContext(source,context);
  }};
  assert.throws(()=>launch({chrome,helperSource,maxPolls:3,wait:()=>{}}));
  assert.equal(context.__WMS665_MAC_RUN__.status, 'error');
  assert.equal(typeof context.helperOptions.assertActive, 'function');
  assert.throws(()=>context.helperOptions.assertActive());
  vm.runInContext('finish()',context);
  assert.equal(context.__WMS665_MAC_RUN__.status, 'error');
  assert.throws(()=>launch({chrome,helperSource,maxPolls:3,wait:()=>{}}));
  assert.equal(injections,1);
});

test('SC21 late registry response after cancellation cannot start DOM preparation', async () => {
  let active=true, resolveRegistry, domActions=0;
  const pending=new Promise(resolve=>{resolveRegistry=resolve;});
  const root={location:new URL(url),localStorage:{getItem:()=> 'synthetic-token'},Response,
    fetch:async (input)=>String(input).includes('/auth/me')?new Response(JSON.stringify(identity)):pending};
  const helper=createHelper({root,assertActive(){if(!active)throw Error('cancelled');},ui:{
    inspectSelection:async()=>({selectedCount:0}),clearFilters:async()=>{domActions++;},
    refreshSelectAllAndOpen:async()=>{domActions++;return{selectedCount:1,dialogOpen:true};},
  }});
  const outcome=helper.run({mode:'execute'});
  await new Promise(resolve=>setImmediate(resolve));
  active=false;
  resolveRegistry(new Response(JSON.stringify({rows:[{row_id:'one',status:'not_withdrawn',operation_id:null,error:null}],total:1})));
  await assert.rejects(outcome,/cancelled/);
  assert.equal(domActions,0);
});

test('SC21 default DOM adapter waits through cold 144 second filter refresh with virtual clock', async () => {
  const {JSDOM}=require(require.resolve('jsdom',{paths:[path.resolve(__dirname,'../../../frontend')]}));
  const dom=new JSDOM(`<section data-testid="seller-kiz-withdrawal-page">
    <label for="from">Передано WB с</label><input id="from"><label for="to">по</label><input id="to">
    <label for="product">Товар</label><input id="product"><label for="search">Поиск</label><input id="search">
    <label><input role="switch" type="checkbox" checked>Только невыведенные</label>
    <button id="refresh" disabled>Обновить</button><span>Найдено: 1</span>
    <input id="all" aria-label="Выбрать все доступные КИЗ по фильтрам" type="checkbox">
    <span>Выбрано КИЗ: 0</span><button id="action" disabled>Вывести из оборота (0)</button>
    </section>`,{url});
  const root=dom.window, doc=root.document;
  let elapsed=0,opened=0;
  root.setTimeout=(fn,ms)=>setImmediate(()=>{elapsed+=ms;if(elapsed>=144000)doc.getElementById('refresh').disabled=false;fn();});
  root.Response=Response;
  root.localStorage.setItem('wms_token_seller','synthetic-token');
  root.fetch=async input=>new Response(JSON.stringify(String(input).includes('/auth/me')?identity:{rows:[{row_id:'one',status:'not_withdrawn',operation_id:null,error:null}],total:1}));
  doc.getElementById('all').onclick=()=>{const b=doc.getElementById('action');b.textContent='Вывести из оборота (1)';b.disabled=false;};
  doc.getElementById('action').onclick=()=>{opened++;const dialog=doc.createElement('div');dialog.setAttribute('role','dialog');dialog.textContent='Выберите сертификат';doc.body.append(dialog);};
  try{
    const result=await createHelper({root}).run({mode:'execute'});
    assert.equal(result.status,'certificate_dialog_open');
    assert.equal(opened,1);
    assert.ok(elapsed>=144000&&elapsed<300000);
  }finally{dom.window.close();}
});
