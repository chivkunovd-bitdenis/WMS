export type Unit = { id: string; productId: string; barcode: string; kiz: string | null; intakeId: string | null; originBoxId?: string; codeGroupId?: string };
export type DemoBox = { id: string; code: string; cell: string; units: Unit[]; closed: boolean; shipmentId?: string; prepared?: boolean; packingDone?: boolean };
export type ShipmentMeta = {
  departureDate: string; wbSlot: string; deliveredByFf: boolean; passFilename: string;
  instructions: string; pickInstructions: string; packingInstructions: string; services: string[];
};
export type UncertainCode = { code: string; productId: string; sourceBoxId: string; intakeId: string | null };
export type DemoEvent = { id: number; text: string; codes: string[]; shipmentId: string };
export type DemoState = {
  sourceBoxes: DemoBox[]; shipmentBoxes: DemoBox[]; stockTotal: number; selectedBoxId: string | null;
  activeShipmentId: string; uncertainCodes: UncertainCode[]; metadata: Record<string, ShipmentMeta>; events: DemoEvent[];
  kizHistory: Record<string, { unitId: string | null; intakeId: string | null; shipmentId: string | null; boxCode?: string | null }>;
  picked: number;
};
export type DemoAction =
  | { type: "pickWholeBox"; boxId: string }
  | { type: "pickWholeCell"; cell: string }
  | { type: "pickPartial"; boxId: string; productId: string; quantity: number; kizCodes: string[]; targetBoxId?: string }
  | { type: "verifyKiz"; boxId: string; kiz: string; productId?: string }
  | { type: "recordKiz"; boxId: string; productId: string; kiz: string }
  | { type: "createBox" }
  | { type: "selectBox"; boxId: string }
  | { type: "addUnit"; boxId: string; unit: Unit }
  | { type: "closeBox"; boxId: string; next?: boolean }
  | { type: "reset" }
  | { type: "openBox"; boxId: string }
  | { type: "removeUnit"; boxId: string; unitId: string }
  | { type: "removeQuantity"; boxId: string; productId: string; quantity: number; kizCodes: string[] }
  | { type: "moveUnit"; boxId: string; unitId: string; targetBoxId: string }
  | { type: "packingDone"; boxId: string }
  | { type: "switchShipment"; shipmentId: string }
  | { type: "patchMeta"; patch: Partial<ShipmentMeta> };
export const storageKey = "wms686-picking-kiz";
export const primaryShipment = "demo-shipment";
export const secondaryShipment = "demo-shipment-kazan";
export function createDemoState(): DemoState {
  const units: Unit[] = Array.from({ length: 12 }, (_, i) => ({
    id: "u" + (i + 1), productId: i < 6 || i >= 10 ? "p1" : "p2", barcode: i < 6 || i >= 10 ? "DEMO-P1" : "DEMO-P2",
    kiz: i === 11 ? null : "DEMO-KIZ-" + (i + 1), intakeId: i === 11 ? null : "demo-intake", originBoxId: i < 10 ? "source1" : "source2", codeGroupId: i < 10 ? "source1" : "source2",
  }));
  const meta: ShipmentMeta = {
    departureDate: "2026-10-09", wbSlot: "2026-10-10T10:00", deliveredByFf: true, passFilename: "",
    instructions: "Готовые короба не вскрывать. При разборе учитывать КИЗ выбранных единиц, если заказана услуга учёта.",
    pickInstructions: "Размеры 48 и 50 собирать раздельно. КИЗ вносить при извлечении товара из исходного короба.",
    packingInstructions: "Готовые этикетки сохранить. Переклеивать только повреждённые; дополнительная упаковка по необходимости.",
    services: ["Учёт КИЗ"],
  };
  const state: DemoState = {
    sourceBoxes: [
      { id: "source1", code: "INB-DEMO-001", cell: "А-1-1", units: units.slice(0, 10), closed: true, prepared: true },
      { id: "source2", code: "INB-DEMO-002", cell: "А-1-1", units: units.slice(10), closed: true, prepared: true },
    ],
    shipmentBoxes: [], stockTotal: 12, selectedBoxId: null, activeShipmentId: primaryShipment, picked: 0,
    uncertainCodes: [], events: [], metadata: {
      [primaryShipment]: meta,
      [secondaryShipment]: { ...meta, services: [...meta.services], instructions: "Часть общего запаса — на WB Казань. Готовые этикетки сохранить." },
    }, kizHistory: {},
  };
  refresh(state); return state;
}
export function activeBoxes(s: DemoState) { return s.shipmentBoxes.filter((b) => (b.shipmentId ?? primaryShipment) === s.activeShipmentId); }
export function packingReady(s: DemoState, b: DemoBox) {
  return !!b.packingDone || !s.metadata[b.shipmentId ?? primaryShipment].services.some((v) => v === 'Упаковка' || v === 'Переклейка ШК');
}
export function canRecordExternal(s: DemoState, u: Unit) {
  const group = u.codeGroupId ?? u.originBoxId;
  const unbound = [...s.sourceBoxes, ...s.shipmentBoxes].flatMap((b) => b.units).filter((v) => !v.kiz && v.productId === u.productId && (v.codeGroupId ?? v.originBoxId) === group).length;
  return unbound > s.uncertainCodes.filter((c) => c.productId === u.productId && c.sourceBoxId === group).length;
}
export function saveDemoState(state: DemoState, storage: Pick<Storage, "setItem">) { storage.setItem(storageKey, JSON.stringify(state)); }
export function loadDemoState(storage: Pick<Storage, "getItem">): DemoState {
  try {
    const s = JSON.parse(storage.getItem(storageKey) || "null");
    return s && Array.isArray(s.sourceBoxes) && Array.isArray(s.shipmentBoxes) && Array.isArray(s.uncertainCodes) && s.metadata && Array.isArray(s.events) ? s : createDemoState();
  } catch { return createDemoState(); }
}
function refresh(s: DemoState) {
  // If all unresolved members of a recorded group now occupy one box, its
  // complete set of labels is known again. This infers box membership only.
  // No order-based distribution across different boxes is ever inferred.
  for (const key of new Set(s.uncertainCodes.map((c) => c.sourceBoxId + ':' + c.productId))) {
    const records = s.uncertainCodes.filter((c) => c.sourceBoxId + ':' + c.productId === key);
    const locations = [...s.sourceBoxes, ...s.shipmentBoxes].map((box) => ({ box, units: box.units.filter((u) => !u.kiz && (u.codeGroupId ?? u.originBoxId) + ':' + u.productId === key) })).filter((v) => v.units.length);
    if (locations.length === 1 && locations[0].units.length >= records.length) {
      records.forEach((c, i) => { locations[0].units[i].kiz = c.code; locations[0].units[i].intakeId = c.intakeId; });
      s.uncertainCodes = s.uncertainCodes.filter((c) => !records.includes(c));
    }
  }
  for (const b of [...s.sourceBoxes, ...s.shipmentBoxes]) for (const u of b.units) if (u.kiz) s.kizHistory[u.kiz] = {
    unitId: u.id, intakeId: u.intakeId, shipmentId: b.shipmentId ?? null, boxCode: b.code,
  };
  for (const c of s.uncertainCodes) s.kizHistory[c.code] = { unitId: null, intakeId: c.intakeId, shipmentId: null, boxCode: null };
  s.picked = activeBoxes(s).reduce((n, b) => n + b.units.length, 0);
}
function codeForNewBox(s: DemoState) {
  let n = 1;
  while ([...s.sourceBoxes, ...s.shipmentBoxes].some((b) => b.code === "WHB-DEMO-" + String(n).padStart(3, "0"))) n++;
  return { id: "new" + n, code: "WHB-DEMO-" + String(n).padStart(3, "0") };
}
function newBox(s: DemoState) {
  const b: DemoBox = { ...codeForNewBox(s), cell: "Сортировка", units: [], closed: false, shipmentId: s.activeShipmentId };
  s.shipmentBoxes.push(b); s.selectedBoxId = b.id; return b;
}
function event(s: DemoState, text: string, units: Unit[] = []) {
  s.events.push({ id: s.events.length + 1, text, codes: units.flatMap((u) => u.kiz ? [u.kiz] : []), shipmentId: s.activeShipmentId });
}
function unsetKnownCodes(s: DemoState, units: Unit[], sourceId: string) {
  // A quantity does not identify physical marking labels. Retain the recorded
  // codes in an unresolved pool; do not invent which labels were removed.
  for (const u of units) if (u.kiz) {
    u.codeGroupId ??= sourceId;
    s.uncertainCodes.push({ code: u.kiz, productId: u.productId, sourceBoxId: u.codeGroupId, intakeId: u.intakeId }); u.kiz = null;
  }
}
function returnUnits(s: DemoState, units: Unit[]) {
  for (const u of units) {
    let source = s.sourceBoxes.find((b) => b.id === u.originBoxId);
    if (!source || s.shipmentBoxes.some((b) => b.code === source!.code && b.units.length)) {
      source = s.sourceBoxes.find((b) => b.id === "returned");
      if (!source) {
        source = { ...codeForNewBox(s), id: "returned", cell: "А-1-1", units: [], closed: false }; s.sourceBoxes.push(source);
      }
    }
    u.originBoxId = source.id; source.units.push(u);
  }
}
export function reduceDemo(state: DemoState, action: DemoAction): { state: DemoState; error?: string } {
  if (action.type === "reset") return { state: createDemoState() };
  const s = structuredClone(state);
  const reject = (error: string) => ({ state, error });
  const finish = () => { refresh(s); return { state: s }; };
  const findBox = (id: string) => activeBoxes(s).find((b) => b.id === id);
  if (action.type === "switchShipment") {
    if (!s.metadata[action.shipmentId]) return reject("Отгрузка не найдена");
    s.activeShipmentId = action.shipmentId; s.selectedBoxId = activeBoxes(s).find((b) => !b.closed)?.id ?? activeBoxes(s)[0]?.id ?? null; return finish();
  }
  if (action.type === "patchMeta") { Object.assign(s.metadata[s.activeShipmentId], action.patch); return finish(); }
  if (action.type === "createBox") { newBox(s); return finish(); }
  if (action.type === "selectBox") {
    if (!action.boxId) { s.selectedBoxId = null; return finish(); }
    if (!findBox(action.boxId)) return reject("Короб этой отгрузки не найден");
    s.selectedBoxId = action.boxId; return finish();
  }
  if (action.type === "pickWholeBox") {
    const source = s.sourceBoxes.find((b) => b.id === action.boxId);
    if (!source) return reject("Короб не найден");
    if (!source.units.length) return { state };
    if (s.shipmentBoxes.some((b) => b.code === source.code && b.units.length)) return reject("Короб уже находится в отгрузке");
    const target: DemoBox = { ...source, shipmentId: s.activeShipmentId, cell: "Сортировка", units: [...source.units], packingDone: true };
    s.shipmentBoxes = s.shipmentBoxes.filter((b) => b.id !== source.id);
    s.shipmentBoxes.push(target); source.units = []; s.selectedBoxId = target.id;
    event(s, `${target.code}: перенесён целиком, ${target.units.length} шт.`, target.units); return finish();
  }
  if (action.type === "pickWholeCell") {
    let current = s;
    for (const b of s.sourceBoxes.filter((b) => b.cell === action.cell && b.units.length)) {
      const r = reduceDemo(current, { type: "pickWholeBox", boxId: b.id }); if (r.error) return reject(r.error); current = r.state;
    }
    return { state: current };
  }
  if (action.type === "pickPartial") {
    const box = s.sourceBoxes.find((b) => b.id === action.boxId);
    if (!box) return reject("Исходный короб не найден");
    if (!Number.isInteger(action.quantity) || action.quantity < 1) return reject("Укажите целое положительное количество");
    const candidates = box.units.filter((u) => u.productId === action.productId);
    if (action.quantity > candidates.length) return reject("В исходном коробе недостаточно выбранного товара");
    const codes = action.kizCodes.map((c) => c.trim()).filter(Boolean);
    if (new Set(codes).size !== codes.length) return reject("Этот КИЗ уже отсканирован");
    if (codes.length > action.quantity) return reject("Количество меньше числа отсканированных КИЗ");
    const selected: Unit[] = [];
    for (const code of codes) {
      let unit = candidates.find((u) => u.kiz === code);
      const uncertain = s.uncertainCodes.find((c) => c.code === code && c.productId === action.productId && candidates.some((u) => (u.codeGroupId ?? u.originBoxId) === c.sourceBoxId));
      if (!unit && (uncertain || (!s.kizHistory[code] && /^DEMO-(?:NEW-)?KIZ(?:-[A-Z0-9]+)*$/.test(code)))) {
        unit = candidates.find((u) => !u.kiz && !selected.includes(u) && (uncertain ? (u.codeGroupId ?? u.originBoxId) === uncertain.sourceBoxId : canRecordExternal(s, u)));
        if (unit) { unit.kiz = code; unit.intakeId = uncertain?.intakeId ?? null; s.uncertainCodes = s.uncertainCodes.filter((c) => c.code !== code); }
      }
      if (!unit || selected.includes(unit)) return reject("КИЗ не относится к выбранному товару и исходному коробу");
      selected.push(unit);
    }
    const remainder = candidates.filter((u) => !selected.includes(u));
    const unidentifiedCount = action.quantity - selected.length;
    if (unidentifiedCount && unidentifiedCount < remainder.length) unsetKnownCodes(s, remainder, box.id);
    // Moving the complete remaining composition retains its known codes.
    selected.push(...remainder.slice(0, unidentifiedCount));
    const target = action.targetBoxId ? findBox(action.targetBoxId) : findBox(s.selectedBoxId ?? "");
    if (action.targetBoxId && !target) return reject("Выберите короб этой отгрузки");
    if (target?.closed) return reject("Откройте состав короба назначения или выберите открытый короб");
    const destination = target ?? newBox(s);
    for (const u of selected) u.originBoxId = box.id;
    destination.units.push(...selected); destination.packingDone = false;
    box.units = box.units.filter((u) => !selected.includes(u)); s.selectedBoxId = destination.id;
    event(s, `${box.code} → ${destination.code}: взято ${selected.length} шт.; КИЗ учтено ${selected.filter((u) => u.kiz).length}`, selected); return finish();
  }
  if (action.type === "verifyKiz") {
    const unit = findBox(action.boxId)?.units.find((u) => u.kiz === action.kiz);
    if (!unit || (action.productId && unit.productId !== action.productId)) return reject("КИЗ не относится к выбранному товару и коробу");
    event(s, `Проверен ${action.kiz}; количество не изменено`, [unit]); return finish();
  }
  if (action.type === "recordKiz") {
    const box = findBox(action.boxId); if (!box) return reject("Выберите короб этой отгрузки");
    const existing = box.units.find((u) => u.kiz === action.kiz && u.productId === action.productId);
    if (existing) return reduceDemo(state, { type: "verifyKiz", boxId: box.id, kiz: action.kiz, productId: action.productId });
    if ([...s.sourceBoxes, ...s.shipmentBoxes].some((b) => b.units.some((u) => u.kiz === action.kiz))) return reject("Этот КИЗ учтён в другом товаре или коробе");
    const pool = s.uncertainCodes.find((c) => c.code === action.kiz && c.productId === action.productId);
    const unit = box.units.find((u) => u.productId === action.productId && !u.kiz && (pool ? (u.codeGroupId ?? u.originBoxId) === pool.sourceBoxId : canRecordExternal(s, u)));
    if (!unit) return reject("В коробе нет выбранного товара без учтённого КИЗ");
    if (!pool && (s.kizHistory[action.kiz] || !/^DEMO-(?:NEW-)?KIZ(?:-[A-Z0-9]+)*$/.test(action.kiz))) return reject("КИЗ не относится к выбранному товару");
    unit.kiz = action.kiz; unit.intakeId = pool?.intakeId ?? null; s.uncertainCodes = s.uncertainCodes.filter((c) => c.code !== action.kiz);
    event(s, `${box.code}: КИЗ ${action.kiz} внесён в уже подобранную единицу`, [unit]); return finish();
  }
  if (action.type === "addUnit") {
    const box = findBox(action.boxId); if (!box) return reject("Выберите короб этой отгрузки");
    const prior = s.shipmentBoxes.flatMap((b) => b.units).find((u) => u.id === action.unit.id);
    const history = action.unit.kiz ? s.kizHistory[action.unit.kiz] : null;
    if (history?.unitId && history.unitId !== action.unit.id) return reject("Этот КИЗ уже принадлежит другой единице");
    if (prior) return prior.kiz === action.unit.kiz && box.units.includes(prior) ? { state } : reject("Единица уже находится в другом коробе либо имеет другой КИЗ");
    const source = s.sourceBoxes.find((b) => b.units.some((u) => u.id === action.unit.id));
    if (!source) return reject("Единица не найдена в доступном товаре; новый остаток не создаётся");
    return reduceDemo(state, { type: "pickPartial", boxId: source.id, productId: action.unit.productId, quantity: 1, kizCodes: action.unit.kiz ? [action.unit.kiz] : [], targetBoxId: box.id });
  }
  if (action.type === "removeUnit" || action.type === "removeQuantity") {
    const box = findBox(action.boxId); if (!box) return reject("Короб не найден");
    let selected: Unit[] = [];
    if (action.type === "removeUnit") {
      selected = box.units.filter((u) => u.id === action.unitId); if (!selected.length) return { state };
    } else {
      const candidates = box.units.filter((u) => u.productId === action.productId);
      if (!Number.isInteger(action.quantity) || action.quantity < 1 || action.quantity > candidates.length) return reject("Укажите количество в пределах состава короба");
      if (new Set(action.kizCodes).size !== action.kizCodes.length || action.kizCodes.length > action.quantity) return reject("Проверьте количество и КИЗ возвращаемых единиц");
      for (const code of action.kizCodes) {
        const u = candidates.find((u) => u.kiz === code); if (!u) return reject("КИЗ отсутствует в этом товаре и коробе"); selected.push(u);
      }
      const rest = candidates.filter((u) => !selected.includes(u)); const n = action.quantity - selected.length;
      if (n && n < rest.length) for (const origin of new Set(rest.map((u) => u.originBoxId ?? ""))) unsetKnownCodes(s, rest.filter((u) => u.originBoxId === origin), origin);
      selected.push(...rest.slice(0, n));
    }
    box.units = box.units.filter((u) => !selected.includes(u)); returnUnits(s, selected); box.closed = false; box.packingDone = false;
    event(s, `${box.code} → А-1-1: возвращено ${selected.length} шт.`, selected); return finish();
  }
  if (action.type === "moveUnit") {
    const box = findBox(action.boxId), target = findBox(action.targetBoxId); const unit = box?.units.find((u) => u.id === action.unitId);
    if (!box || !target || !unit) return reject("Выберите единицу и короб этой отгрузки");
    if (box.id === target.id) return { state };
    box.units = box.units.filter((u) => u.id !== unit.id); target.units.push(unit); box.closed = false; target.closed = false; target.packingDone = false;
    event(s, `${box.code} → ${target.code}: переложена 1 шт.`, [unit]); return finish();
  }
  if (action.type === "closeBox" || action.type === "openBox" || action.type === "packingDone") {
    const box = findBox(action.boxId); if (!box) return reject("Короб не найден");
    if (action.type === "packingDone") box.packingDone = true; else box.closed = action.type === "closeBox";
    if (action.type === "closeBox" && action.next !== false) {
      const next = activeBoxes(s).find((b) => !b.closed && b.id !== box.id); if (next) s.selectedBoxId = next.id; else newBox(s);
    } else s.selectedBoxId = box.id;
    return finish();
  }
  return reject("Действие не поддерживается макетом");
}
