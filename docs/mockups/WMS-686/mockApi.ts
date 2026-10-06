import {
  createDemoState,
  loadDemoState,
  saveDemoState,
  reduceDemo,
  type DemoAction,
  type DemoState,
} from "./model.ts";
export const products = [
  {
    id: "p1",
    sku_code: "DEMO-TS-48",
    name: "Футболка хлопковая с длинным названием · демонстрационный товар",
    wb_barcodes: ["DEMO-P1"],
    wb_size: "48",
    wb_color: "Синий",
    wb_vendor_code: "DEMO-TS",
  },
  {
    id: "p2",
    sku_code: "DEMO-TS-50",
    name: "Футболка хлопковая",
    wb_barcodes: ["DEMO-P2"],
    wb_size: "50",
    wb_color: "Серый",
    wb_vendor_code: "DEMO-TS",
  },
];
let state: DemoState = createDemoState();
export const isBaseline = () =>
  typeof location !== "undefined" &&
  new URLSearchParams(location.search).has("baseline");
export const getDemo = () => state;
export function dispatchDemo(action: DemoAction) {
  const result = reduceDemo(state, action);
  if (!result.error) {
    state = result.state;
    if (typeof localStorage !== "undefined" && !isBaseline())
      saveDemoState(state, localStorage);
    if (typeof window !== "undefined")
      window.dispatchEvent(new Event("wms686-change"));
  }
  return result;
}
export const detail = {
  id: "demo-shipment",
  document_number: "000086",
  display_number: "000086",
  warehouse_id: "demo-wh",
  warehouse_name: "Демо склад",
  status: "collecting",
  seller_id: "demo-seller",
  seller_name: "Демо селлер",
  marketplace: "wb",
  wb_mp_warehouse_id: 1,
  planned_shipment_date: "2026-10-09",
  created_at: "2026-10-06T12:00:00Z",
  lines: products.map((p, i) => ({
    id: "l" + i,
    product_id: p.id,
    sku_code: p.sku_code,
    product_name: p.name,
    quantity: i ? 4 : 8,
    picked_qty: 0,
  })),
};
const count = (productId: string) =>
  state.shipmentBoxes
    .flatMap((b) => b.units)
    .filter((u) => u.productId === productId).length;
const boxLines = (b: DemoState["shipmentBoxes"][number]) =>
  products
    .map((p) => ({
      id: b.id + "-" + p.id,
      product_id: p.id,
      sku_code: p.sku_code,
      product_name: p.name,
      quantity: b.units.filter((u) => u.productId === p.id).length,
    }))
    .filter((l) => l.quantity);
export function getTask() {
  return {
    id: "demo-pack",
    document_number: "000086",
    display_number: "000086",
    warehouse_id: "demo-wh",
    warehouse_name: "Демо склад",
    seller_id: "demo-seller",
    seller_name: "Демо селлер",
    status: "in_progress",
    marketplace_unload_request_id: detail.id,
    inbound_intake_request_id: null,
    is_complete: state.picked >= 12,
    events: [],
    lines: products.map((p, i) => ({
      id: "pl" + i,
      product_id: p.id,
      seller_id: "demo-seller",
      seller_name: "Демо селлер",
      sku_code: p.sku_code,
      product_name: p.name,
      storage_location_id: "cell1",
      storage_location_code: "А-1-1",
      packaging_instructions:
        "Проверить этикетку; готовые короба не вскрывать без необходимости.",
      requires_honest_sign: false,
      qty_total: count(p.id),
      qty_suggested_packed: count(p.id),
      qty_confirmed_packed: count(p.id),
      qty_need_pack: count(p.id),
      qty_packed_in_task: count(p.id),
      qty_done: count(p.id),
      qty_marking_printed: 0,
      qty_marking_external: count(p.id),
      qty_product_label_printed: 0,
      marking_available_count: 0,
      is_complete: true,
    })),
  };
}
export function getDetail() {
  return {
    ...detail,
    lines: detail.lines.map((l) => ({ ...l, picked_qty: count(l.product_id) })),
    boxes: state.shipmentBoxes.map((b) => ({
      id: b.id,
      box_preset: "60_40_40",
      internal_barcode: b.code,
      closed_at: b.closed ? "2026-10-06T12:00:00Z" : null,
      lines: boxLines(b),
    })),
    pick_allocations: products.map((p) => ({
      id: "a" + p.id,
      product_id: p.id,
      sku_code: p.sku_code,
      product_name: p.name,
      storage_location_id: "cell1",
      location_code: "А-1-1",
      quantity: count(p.id),
    })),
    linked_packaging_task: {
      task_id: "demo-pack",
      status: "in_progress",
      qty_done: state.picked,
      qty_total: state.picked,
      is_complete: state.picked >= 12,
    },
  };
}
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
export function createMockFetch(): typeof fetch {
  return async (input, init) => {
    const path = new URL(
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : input.url,
      "http://wms686.local",
    ).pathname;
    const method = (
      init?.method ?? (input instanceof Request ? input.method : "GET")
    ).toUpperCase();
    const base = "/api/operations/marketplace-unload-requests/demo-shipment";
    const known = new Set([
      "GET /api/products/linked-wb-catalog",
      "GET /api/operations/wb-mp-warehouses",
      "GET /api/operations/marketplace-unload-requests/available-products",
      `GET ${base}`,
      `GET ${base}/pick-options`,
      "GET /api/operations/packaging-tasks/demo-pack",
      "GET /api/operations/packaging-tasks/by-unload/demo-shipment",
      ...[
        "pick/scan",
        "pick/set",
        "boxes/batch",
        "boxes/attach",
        "ship",
        "cancel",
      ].map((action) => `POST ${base}/${action}`),
    ]);
    if (!known.has(`${method} ${path}`))
      return json(
        { detail: `Неизвестный маршрут локального макета: ${method} ${path}` },
        400,
      );
    let body: Record<string, unknown> = {};
    try {
      body = init?.body ? JSON.parse(String(init.body)) : {};
    } catch {
      return json({ detail: "Некорректный JSON в запросе макета" }, 400);
    }
    if (path.includes("linked-wb-catalog")) return json(products);
    if (path.endsWith("/wb-mp-warehouses"))
      return json([{ wb_warehouse_id: 1, name: "Демо · Краснодар" }]);
    if (path.includes("available"))
      return json(
        products.map((p) => ({
          product_id: p.id,
          sku_code: p.sku_code,
          product_name: p.name,
          available: 12 - count(p.id),
        })),
      );
    if (path.endsWith("/pick-options")) {
      const initial = createDemoState();
      return json(
        products.map((p, i) => ({
          product_id: p.id,
          sku_code: p.sku_code,
          product_name: p.name,
          planned_qty: i ? 4 : 8,
          picked_qty: count(p.id),
          locations: [
            {
              storage_location_id: "cell1",
              location_code: "А-1-1",
              quantity: (i ? 4 : 8) - count(p.id),
              reserved: 0,
              available: (i ? 4 : 8) - count(p.id),
              picked: count(p.id),
              sources: state.sourceBoxes
                .map((b) => {
                  const initBox = initial.sourceBoxes.find(
                    (x) => x.id === b.id,
                  )!;
                  const initialQuantity = initBox.units.filter(
                    (u) => u.productId === p.id,
                  ).length;
                  const quantity = b.units.filter(
                    (u) => u.productId === p.id,
                  ).length;
                  return {
                    quantity,
                    is_loose: false,
                    source_label: "Короб " + b.code,
                    picked: initialQuantity - quantity,
                    container_path: [
                      {
                        kind: "box",
                        id: b.id,
                        code: b.code,
                        label: "Короб " + b.code,
                      },
                    ],
                  };
                })
                .filter((s) => s.quantity || s.picked),
            },
          ],
        })),
      );
    }
    if (path.endsWith("/pick/scan")) {
      if (body.barcode === "А-1-1")
        return json({
          kind: "location",
          storage_location_id: "cell1",
          location_code: "А-1-1",
        });
      const box = state.sourceBoxes.find((b) => b.code === body.barcode);
      if (box)
        return json({
          kind: "container",
          container_id: box.id,
          container_kind: "box",
          container_code: box.code,
          storage_location_id: "cell1",
          location_code: box.cell,
        });
      return json(
        {
          detail:
            "Для частичного подбора выберите количество и отсканируйте конкретные КИЗ ниже.",
        },
        400,
      );
    }
    if (path.endsWith("/pick/set"))
      return json(
        {
          detail:
            "Для маркированных единиц укажите конкретные КИЗ в панели частичного подбора.",
        },
        400,
      );
    if (path.endsWith("/boxes/batch") && method === "POST") {
      for (let i = 0; i < Number(body.count ?? 1); i++)
        dispatchDemo({ type: "createBox" });
      return json(getDetail());
    }
    if (path.endsWith("/boxes/attach") && method === "POST") {
      const b = state.sourceBoxes.find((x) => x.code === body.barcode);
      if (!b) return json({ detail: "Короб не найден в демо" }, 400);
      const r = dispatchDemo({ type: "pickWholeBox", boxId: b.id });
      return r.error ? json({ detail: r.error }, 400) : json(getDetail());
    }
    if (path.endsWith("/ship") || path.endsWith("/cancel"))
      return json(
        {
          detail:
            "Это макет. Проведение и отмена рабочего документа не выполняются.",
        },
        400,
      );
    if (path.includes("/packaging-tasks/") && method === "GET")
      return json(getTask());
    if (
      path === "/api/operations/marketplace-unload-requests/demo-shipment" &&
      method === "GET"
    )
      return json(getDetail());
    return json(
      { detail: "Маршрут не реализован в локальном макете: " + path },
      400,
    );
  };
}
export function installMockApi() {
  if (typeof localStorage !== "undefined" && !isBaseline()) {
    const reset = new URLSearchParams(location.search).has("reset");
    const fresh = reset || !localStorage.getItem("wms686-demo-v1");
    state = fresh ? createDemoState() : loadDemoState(localStorage);
    if (fresh) {
      // The last physical unit is known as stock, but its individual marking
      // was never scanned on intake. Recording its label must not add stock.
      const unit = state.sourceBoxes[1].units[1];
      if (unit.kiz) delete state.kizHistory[unit.kiz];
      unit.kiz = null;
      unit.intakeId = null;
    }
    saveDemoState(state, localStorage);
  }
  globalThis.fetch = createMockFetch();
}
