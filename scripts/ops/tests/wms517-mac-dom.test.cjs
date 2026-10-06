'use strict';
// Exercise the product's default DOM adapter, not an injected UI substitute.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { JSDOM } = require(require.resolve('jsdom', { paths: [
  path.resolve(__dirname, '../../../frontend'), path.resolve(__dirname, '../../../../../frontend'),
] }));
const directory = process.env.WMS517_MAC_SOURCE_DIR ?? path.join(__dirname, '..');
const { createHelper } = require(path.join(directory, 'avpack-sold-kiz-filter.js'));
const historicalIds = require('./fixtures/wms517-historical80-row-ids.json');
const ORIGIN = 'https://wms.sellerfocus.pro';
const REGISTRY = '/api/operations/marking-codes/self/withdrawals';

test('SC17 default DOM adapter clears old filters, selects every page and opens only the native certificate dialog', async () => {
  const dom = new JSDOM(`<section data-testid="seller-kiz-withdrawal-page">
    <div><label for="from">Передано WB с</label><input id="from" type="date" value="2026-09-18"></div>
    <div><label for="to">по</label><input id="to" type="date" value="2026-09-25"></div>
    <div><label for="product">Товар</label><input id="product" role="combobox" value="Old product">
      <button type="button" aria-label="Clear" title="Clear">×</button></div>
    <div><label for="search">Поиск</label><input id="search" value="Old search"></div>
    <label><input id="only" type="checkbox" role="switch">Только невыведенные</label>
    <button id="refresh">Обновить</button><span id="found">Найдено: 5</span>
    <input id="all" type="checkbox" aria-label="Выбрать все доступные КИЗ по фильтрам">
    <span id="selected">Выбрано КИЗ: 0</span><button id="open" disabled>Вывести из оборота (0)</button>
  </section>`, { url: `${ORIGIN}/seller/honest-sign/withdrawals` });
  const root = dom.window, doc = root.document;
  const calls = [], selected = [], forbidden = [];
  let refreshes = 0, opened = 0;
  const rows = Array.from({ length: 305 }, (_, i) => ({ row_id: historicalIds[i] ?? `new-sale-${i}`,
    status:'not_withdrawn', operation_id:null, error:null, cis:`synthetic-cis-${i}` }));
  root.Response = Response;
  root.setTimeout = fn => setTimeout(fn, 0);
  root.localStorage.setItem('wms_token_seller', 'synthetic-token');
  root.cadesplugin = { sign() { forbidden.push('signature'); throw new Error('unexpected signature'); } };
  const filtersCleared = () => ['from','to','product','search'].every(id => doc.getElementById(id).value === '');
  doc.querySelector('[aria-label="Clear"]').onclick = () => { doc.getElementById('product').value = ''; };
  root.fetch = async (input, init = {}) => {
    const url = new URL(String(input), ORIGIN); calls.push({ url, method: init.method ?? 'GET' });
    assert.equal(init.method ?? 'GET','GET','DOM preparation cannot create/sign/submit');
    if (url.pathname === '/api/auth/me') return new Response(JSON.stringify({
      tenant_id:'d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe', seller_id:'0b8da5d8-f43a-42f5-a2ec-43173ea844bd',
      active_seller_id:'0b8da5d8-f43a-42f5-a2ec-43173ea844bd', role:'fulfillment_seller', withdrawal_enabled:true,
    }));
    assert.equal(url.pathname, REGISTRY);
    const offset = Number(url.searchParams.get('offset') ?? 0), limit = Number(url.searchParams.get('limit') ?? 50);
    const narrowed = ['date_from','date_to','product_id','search'].some(k => url.searchParams.get(k));
    const current = narrowed ? rows.slice(0,5) : rows;
    return new Response(JSON.stringify({ rows:current.slice(offset,offset+limit), total:current.length }));
  };
  const uiPage = async offset => {
    const query = new URLSearchParams({ only_not_withdrawn:String(doc.getElementById('only').checked), limit:'250', offset:String(offset) });
    for (const [key,id] of [['date_from','from'],['date_to','to'],['product_id','product'],['search','search']]) {
      if (doc.getElementById(id).value) query.set(key,doc.getElementById(id).value);
    }
    return (await root.fetch(`${ORIGIN}${REGISTRY}?${query}`)).json();
  };
  doc.getElementById('refresh').onclick = async () => {
    refreshes += 1; const body = await uiPage(0); doc.getElementById('found').textContent = `Найдено: ${body.total}`;
  };
  doc.getElementById('all').onclick = async () => {
    selected.length = 0;
    for (let offset=0; ;offset+=250) {
      const body = await uiPage(offset); selected.push(...body.rows.map(r => r.row_id));
      if (offset+body.rows.length >= body.total) break;
    }
    doc.getElementById('selected').textContent = `Выбрано КИЗ: ${selected.length}`;
    const button = doc.getElementById('open'); button.textContent = `Вывести из оборота (${selected.length})`; button.disabled = false;
  };
  doc.getElementById('open').onclick = () => {
    opened += 1;
    const dialog = doc.createElement('div'); dialog.setAttribute('role','dialog');
    dialog.innerHTML = '<span>Выберите сертификат</span><button aria-label="Закрыть">×</button><button id="submit">Подписать и отправить</button>';
    dialog.querySelector('#submit').onclick = () => forbidden.push('submit');
    dialog.querySelector('[aria-label="Закрыть"]').onclick = () => dialog.remove();
    doc.body.append(dialog);
  };
  try {
    const result = await createHelper({root}).run({mode:'execute'});
    assert.equal(result.status,'certificate_dialog_open'); assert.equal(result.targetCount,305);
    assert.equal(filtersCleared(),true,'both dates/product/search must actually be cleared in the DOM');
    assert.equal(doc.getElementById('only').checked,true);
    assert.deepEqual(selected,rows.map(r=>r.row_id)); assert.equal(opened,1); assert.ok(refreshes>=1);
    assert.deepEqual(forbidden,[]); assert.equal(result.signed,false); assert.equal(result.sent,false);
    assert.ok(!JSON.stringify(result).includes('synthetic-token'));
    assert.ok(calls.every(c=>c.method==='GET'));
  } finally { dom.window.close(); }
});
