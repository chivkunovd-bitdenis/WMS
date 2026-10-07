// Exact Git blobs compiled in memory; no product files or dependencies modified.
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../../..');
const source = 'ef154664e365644f4ba002c6e8affc5607fae725';
const ts = require(path.join(root, '../night1007-integration/frontend/node_modules/typescript'));
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file).exports;
  const raw = cp.execFileSync('git', ['show', source + ':' + file], { cwd: root, encoding: 'utf8' });
  const code = ts.transpileModule(raw, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  const module = { exports: {} }; cache.set(file, module);
  const localRequire = name => name.startsWith('.') ? load(path.posix.normalize(path.posix.join(path.posix.dirname(file), name)) + '.ts') : require(name);
  new Function('require', 'module', 'exports', code)(localRequire, module, module.exports);
  return module.exports;
}
const ux = load('frontend/src/screens/v2/fbsUx.ts');
const assembly = load('frontend/src/screens/v2/fbsSupplyAssembly.ts');
function order(id, color) {
  return { id, wb_order_id: 42 + id, tape_order_index: id, deadline_at: '2026-10-07',
    marketplace: 'wb', product: { id: 'same-product', name: 'Product', seller_article: 'ART-680',
      size: 'XL', color, barcode: '460000', image_url: null, wb_article: null },
    positions: [], pick: { status: 'picked' }, metadata: { required: [] },
    inventory: { locations: [] }, sticker: { code: null } };
}
const wb = [order(1, null), order(2, 'Blue')];
const wbSnapshot = JSON.stringify(wb);
const wbRows = ux.fbsBuildPickingRows(wb, false).rows;
assert.equal(wbRows[0].color, 'Blue'); assert.equal(wbRows[0].article, 'ART-680');
assert.equal(wbRows[0].size, 'XL'); assert.deepEqual(wbRows[0].wbOrders, [43, 44]);
assert.equal(JSON.stringify(wb), wbSnapshot);
const receipts = [{ scenario: 'WB grouped fallback preserves article/size/color/order and input', passed: true }];
for (const external of ['000673-POSTING', undefined, null]) {
  const o = order(1, null); o.marketplace = 'ozon'; o.external_order_id = external;
  o.positions = [{ id: 'p', product_id: 'same-product', name: 'Ozon product', seller_article: 'ART-OZ',
    size: 'M', color: 'Green', quantity: 2, picked_quantity: 1, barcode: '460001', image_url: null }];
  const snapshot = JSON.stringify(o);
  const row = ux.fbsBuildPickingRows([o], true).rows[0];
  assert.deepEqual(row.wbOrders, [external ?? 43]);
  assert.deepEqual([row.article, row.size, row.color], ['ART-OZ', 'M', 'Green']);
  const grouped = assembly.fbsAssemblyPickingRows([{ orders: [o] }])[0];
  assert.deepEqual(grouped.wbOrders, [external ?? '43']);
  assert.deepEqual([grouped.article, grouped.size, grouped.color], ['ART-OZ', 'M', 'Green']);
  assert.equal(JSON.stringify(o), snapshot);
  const html = ux.buildFbsPickingListPrintHtml({ supplyName: 'Ozon', marketplace: 'ozon', wbSupplyId: 'OZ-680',
    sellerName: 'Seller', wmsWarehouseName: 'Warehouse', routeLabel: 'Route', deadlineLabel: 'Date', printedAtLabel: 'Date', rows: [row] });
  assert.match(html, /<th>Артикул<\/th><th>Цвет<\/th><th class="size">Размер<\/th>/);
  assert.match(html, /Заказы Ozon/); assert.match(html, /ART-OZ/); assert.match(html, /Green/);
  if (external) assert.match(html, /000673-POSTING/);
  receipts.push({ scenario: 'Ozon external identifier ' + String(external), passed: true });
}
const groupWB = assembly.fbsAssemblyPickingRows([{ orders: wb }])[0];
assert.equal(groupWB.color, 'Blue');
receipts.push({ scenario: 'assembly WB current.color fallback', passed: true });
fs.writeFileSync(path.join(__dirname, 'integration-probe.json'), JSON.stringify({ source, receipts }, null, 2) + '\n');
process.stdout.write('PASS five addressed executable integration probes\n');
