import { activeBoxes, createDemoState, loadDemoState, saveDemoState, reduceDemo, packingReady, primaryShipment, secondaryShipment, type DemoAction, type DemoState } from './model.ts';
export const products = [
  { id: 'p1', sku_code: 'DEMO-TS-48', name: 'Футболка хлопковая с длинным названием · демонстрационный товар', wb_barcodes: ['DEMO-P1'], wb_size: '48', wb_color: 'Синий', wb_vendor_code: 'DEMO-TS' },
  { id: 'p2', sku_code: 'DEMO-TS-50', name: 'Футболка хлопковая', wb_barcodes: ['DEMO-P2'], wb_size: '50', wb_color: 'Серый', wb_vendor_code: 'DEMO-TS' },
];
let state: DemoState = createDemoState();
let nextPickKiz: string | null = null;
export function queuePickKiz(code: string | null) { nextPickKiz = code; }
const sourceCount = (productId: string, boxId: string, id = state.activeShipmentId) => boxesFor(id).flatMap(b => b.units).filter(u => u.productId === productId && u.originBoxId === boxId).length;
export const isBaseline = () => typeof location !== 'undefined' && new URLSearchParams(location.search).has('baseline');
export const getDemo = () => state;
export function dispatchDemo(action: DemoAction) {
  const r = reduceDemo(state, action);
  if (!r.error) {
    state = r.state;
    if (typeof localStorage !== 'undefined' && !isBaseline()) saveDemoState(state, localStorage);
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('wms686-change'));
  }
  return r;
}
export const detail = {
  id: primaryShipment, document_number: '000086', display_number: '000086', warehouse_id: 'demo-wh', warehouse_name: 'Демо склад', status: 'collecting',
  seller_id: 'demo-seller', seller_name: 'Демо селлер', marketplace: 'wb', wb_mp_warehouse_id: 1,
  planned_shipment_date: '2026-10-09', created_at: '2026-10-06T12:00:00Z',
  lines: products.map((p, i) => ({ id: 'l' + i, product_id: p.id, sku_code: p.sku_code, product_name: p.name, quantity: i ? 4 : 8, picked_qty: 0 })),
};
export const secondaryDetail = { ...detail, id: secondaryShipment, document_number: '000087', display_number: '000087', wb_mp_warehouse_id: 2,
  lines: detail.lines.map((l) => ({ ...l, quantity: 2 })) };
export const shipmentDetail = (id = state.activeShipmentId) => id === secondaryShipment ? secondaryDetail : detail;
const boxesFor = (id: string) => state.shipmentBoxes.filter((b) => (b.shipmentId ?? primaryShipment) === id);
const count = (productId: string, id = state.activeShipmentId) => boxesFor(id).flatMap((b) => b.units).filter((u) => u.productId === productId).length;
export const taskIdFor = (id: string) => id === secondaryShipment ? 'demo-pack-kazan' : 'demo-pack';
export function getTask(id = state.activeShipmentId) {
  const d = shipmentDetail(id), boxes = boxesFor(id), total = boxes.reduce((n, b) => n + b.units.length, 0);
  const ready = boxes.filter((b) => packingReady(state, b)), done = ready.reduce((n, b) => n + b.units.length, 0);
  return {
    id: taskIdFor(id), document_number: d.document_number, display_number: d.display_number,
    warehouse_id: d.warehouse_id, warehouse_name: d.warehouse_name, seller_id: d.seller_id, seller_name: d.seller_name,
    status: total > 0 && boxes.every((b) => b.packingDone) ? 'done' : 'in_progress', marketplace_unload_request_id: id, inbound_intake_request_id: null,
    is_complete: total > 0 && done === total, events: [],
    lines: products.map((p, i) => ({
      id: 'pl' + i, product_id: p.id, seller_id: d.seller_id, seller_name: d.seller_name, sku_code: p.sku_code, product_name: p.name,
      storage_location_id: 'cell1', storage_location_code: 'А-1-1', packaging_instructions: state.metadata[id].packingInstructions,
      requires_honest_sign: true, qty_total: count(p.id, id), qty_suggested_packed: count(p.id, id), qty_confirmed_packed: count(p.id, id),
      qty_need_pack: count(p.id, id), qty_packed_in_task: ready.flatMap((b) => b.units).filter((u) => u.productId === p.id).length,
      qty_done: ready.flatMap((b) => b.units).filter((u) => u.productId === p.id).length, qty_marking_printed: 0,
      qty_marking_external: count(p.id, id), qty_product_label_printed: 0, marking_available_count: 0, is_complete: true,
    })),
  };
}
export function getDetail(id = state.activeShipmentId) {
  const d = shipmentDetail(id), boxes = boxesFor(id), task = getTask(id);
  return {
    ...d, planned_shipment_date: state.metadata[id].departureDate,
    lines: d.lines.map((l) => ({ ...l, picked_qty: count(l.product_id, id) })),
    boxes: boxes.map((b) => ({ id: b.id, box_preset: '60_40_40', internal_barcode: b.code, closed_at: b.closed ? '2026-10-07T12:00:00Z' : null,
      lines: products.map((p) => ({ id: b.id + '-' + p.id, product_id: p.id, sku_code: p.sku_code, product_name: p.name,
        quantity: b.units.filter((u) => u.productId === p.id).length })).filter((l) => l.quantity) })),
    pick_allocations: products.map((p) => ({ id: 'a' + p.id, product_id: p.id, sku_code: p.sku_code, product_name: p.name,
      storage_location_id: 'cell1', location_code: 'А-1-1', quantity: count(p.id, id) })),
    linked_packaging_task: { task_id: task.id, status: task.status, qty_done: boxes.filter((b) => packingReady(state, b)).reduce((n, b) => n + b.units.length, 0),
      qty_total: boxes.reduce((n, b) => n + b.units.length, 0), is_complete: task.is_complete },
  };
}
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
export function createMockFetch(): typeof fetch {
  return async (input, init) => {
    const path = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://wms686.local').pathname;
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const id = path.includes(secondaryShipment) || path.includes('demo-pack-kazan') ? secondaryShipment : primaryShipment;
    const base = '/api/operations/marketplace-unload-requests/' + id;
    const known = new Set([
      'GET /api/products/linked-wb-catalog', 'GET /api/operations/wb-mp-warehouses', 'GET /api/operations/marketplace-unload-requests/available-products',
      'GET ' + base, 'PATCH ' + base, 'GET ' + base + '/pick-options',
      'GET /api/operations/packaging-tasks/' + taskIdFor(id), 'GET /api/operations/packaging-tasks/by-unload/' + id,
      'POST /api/operations/packaging-tasks/' + taskIdFor(id) + '/complete',
      ...['pick/scan', 'pick/set', 'boxes/batch', 'boxes/attach', 'ship', 'cancel'].map((a) => 'POST ' + base + '/' + a),
    ]);
    // Deliberately no fallback to the real fetch, even for a known production host.
    if (!known.has(method + ' ' + path)) return json({ detail: 'Неизвестный маршрут локального макета: ' + method + ' ' + path }, 400);
    let body: Record<string, unknown> = {};
    try { body = init?.body ? JSON.parse(String(init.body)) : {}; } catch { return json({ detail: 'Некорректный JSON в запросе макета' }, 400); }
    if (path.includes('linked-wb-catalog')) return json(products);
    if (path.endsWith('/wb-mp-warehouses')) return json([{ wb_warehouse_id: 1, name: 'Демо · Краснодар' }, { wb_warehouse_id: 2, name: 'Демо · Казань' }]);
    if (path.includes('available-products')) return json(products.map((p) => ({ product_id: p.id, sku_code: p.sku_code, product_name: p.name,
      available: state.sourceBoxes.flatMap((b) => b.units).filter((u) => u.productId === p.id).length })));
    if (state.activeShipmentId !== id && (path === base || method !== 'GET')) state = reduceDemo(state, { type: 'switchShipment', shipmentId: id }).state;
    if (path.endsWith('/pick-options')) return json(products.map((p, i) => ({ product_id: p.id, sku_code: p.sku_code, product_name: p.name,
      planned_qty: shipmentDetail(id).lines[i].quantity, picked_qty: count(p.id, id), locations: [{ storage_location_id: 'cell1', location_code: 'А-1-1',
        quantity: state.sourceBoxes.flatMap((b) => b.units).filter((u) => u.productId === p.id).length, reserved: 0,
        available: state.sourceBoxes.flatMap((b) => b.units).filter((u) => u.productId === p.id).length, picked: count(p.id, id),
        sources: state.sourceBoxes.map((b) => ({ quantity: b.units.filter((u) => u.productId === p.id).length, is_loose: false,
          source_label: 'Короб ' + b.code, available: b.units.filter(u => u.productId === p.id).length, picked: sourceCount(p.id,b.id,id), container_path: [{ kind: 'box', id: b.id, code: b.code, label: 'Короб ' + b.code }] })).filter((b) => b.quantity || b.picked),
      }] })));
    if (path.endsWith('/pick/scan')) {
      const code = String(body.barcode ?? '');
      if (code === 'А-1-1') return json({ kind: 'location', storage_location_id: 'cell1', location_code: 'А-1-1' });
      const box = state.sourceBoxes.find((b) => b.code === code);
      if (box) return json({ kind: 'container', container_id: box.id, container_kind: 'box', container_code: box.code, storage_location_id: 'cell1', location_code: box.cell });
      const product = products.find((p) => p.wb_barcodes.includes(code) || p.sku_code === code);
      const kiz = nextPickKiz; nextPickKiz = null;
      const source = state.sourceBoxes.find((b) => (!body.container_id || b.id === body.container_id) && b.units.some((u) => u.productId === product?.id));
      if (!product || !source) return json({ detail: 'Товар не найден в выбранном месте' }, 400);
      const r = dispatchDemo({ type: 'pickPartial', boxId: source.id, productId: product.id, quantity: 1, kizCodes: kiz ? [kiz] : [] });
      return r.error ? json({ detail: r.error }, 400) : json({ kind: 'product', product_id: product.id, sku_code: product.sku_code, product_name: product.name, picked_qty: count(product.id), allocation_quantity: sourceCount(product.id,source.id), storage_location_id: 'cell1', location_code: source.cell, kiz });
    }
    if (path.endsWith('/pick/set')) {
      const productId = String(body.product_id), wanted = Number(body.quantity ?? body.picked_qty ?? 0), delta = wanted - (body.container_id ? sourceCount(productId,String(body.container_id)) : count(productId));
      if (delta > 0) {
        const b = state.sourceBoxes.find((b) => (!body.container_id || b.id === body.container_id) && b.units.filter((u) => u.productId === productId).length >= delta);
        if (!b) return json({ detail: 'В выбранном месте недостаточно товара' }, 400);
        const r = dispatchDemo({ type: 'pickPartial', boxId: b.id, productId, quantity: delta, kizCodes: [] });
        if (r.error) return json({ detail: r.error }, 400);
      } else if (delta < 0) {
        const units = activeBoxes(state).flatMap((b) => b.units.map((u) => ({ b, u }))).filter(({ u }) => u.productId === productId && (!body.container_id || u.originBoxId === body.container_id)).slice(0, -delta);
        for (const { b, u } of units) dispatchDemo({ type: 'removeUnit', boxId: b.id, unitId: u.id });
      }
      return json(getDetail());
    }
    if (path.endsWith('/boxes/batch')) {
      for (let i = 0; i < Math.min(50, Number(body.count ?? 1)); i++) dispatchDemo({ type: 'createBox' }); return json(getDetail());
    }
    if (path.endsWith('/boxes/attach')) {
      const b = state.sourceBoxes.find((b) => b.code === body.barcode);
      if (!b) return json({ detail: 'Короб не найден в демо' }, 400);
      const r = dispatchDemo({ type: 'pickWholeBox', boxId: b.id }); return r.error ? json({ detail: r.error }, 400) : json(getDetail());
    }
    if (path.endsWith('/ship') || path.endsWith('/cancel')) return json({ detail: 'Макет: рабочий документ не проводится и не отменяется.' }, 400);
    if (path === base && method === 'PATCH') {
      if (typeof body.planned_shipment_date === 'string') dispatchDemo({ type: 'patchMeta', patch: { departureDate: body.planned_shipment_date } });
      return json(getDetail(id));
    }
    if (path.includes('/packaging-tasks/') && path.endsWith('/complete')) {
      for (const b of boxesFor(id)) dispatchDemo({ type: 'packingDone', boxId: b.id });
      return json(getTask(id));
    }
    if (path.includes('/packaging-tasks/')) return json(getTask(id));
    if (path === base) return json(getDetail(id));
    return json({ detail: 'Действие локального макета не реализовано' }, 400);
  };
}
export function installMockApi() {
  if (typeof localStorage !== 'undefined' && !isBaseline()) {
    const params = new URLSearchParams(location.search);
    if (params.has('reset')) { localStorage.removeItem('wms686-picking-kiz'); params.delete('reset'); history.replaceState(null, '', '?' + params.toString()); }
    state = loadDemoState(localStorage);
    state = reduceDemo(state, { type: 'switchShipment', shipmentId: params.get('open_mp') === secondaryShipment ? secondaryShipment : primaryShipment }).state;
    saveDemoState(state, localStorage);
  }
  globalThis.fetch = createMockFetch();
}
