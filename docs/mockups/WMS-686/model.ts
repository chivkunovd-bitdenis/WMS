export type Unit = {
  id: string;
  productId: string;
  barcode: string;
  kiz: string | null;
  intakeId: string | null;
};
export type DemoBox = {
  id: string;
  code: string;
  cell: string;
  units: Unit[];
  closed: boolean;
};
export type DemoState = {
  sourceBoxes: DemoBox[];
  shipmentBoxes: DemoBox[];
  stockTotal: number;
  selectedBoxId: string | null;
  kizHistory: Record<
    string,
    { unitId: string; intakeId: string | null; shipmentId: string | null }
  >;
  picked: number;
};
export type DemoAction =
  | { type: "pickWholeBox"; boxId: string }
  | { type: "pickWholeCell"; cell: string }
  | {
      type: "pickPartial";
      boxId: string;
      productId: string;
      quantity: number;
      kizCodes: string[];
    }
  | { type: "verifyKiz"; boxId: string; kiz: string; productId?: string }
  | { type: "createBox" }
  | { type: "addUnit"; boxId: string; unit: Unit }
  | { type: "closeBox"; boxId: string }
  | { type: "reset" }
  | { type: "openBox"; boxId: string }
  | { type: "removeUnit"; boxId: string; unitId: string };
export const storageKey = "wms686-demo-v1";
export function createDemoState(): DemoState {
  const units = Array.from({ length: 12 }, (_, i) => ({
    id: "u" + (i + 1),
    productId: i < 6 || i >= 10 ? "p1" : "p2",
    barcode: i < 6 || i >= 10 ? "DEMO-P1" : "DEMO-P2",
    kiz: "DEMO-KIZ-" + (i + 1),
    intakeId: "demo-intake",
  }));
  return {
    sourceBoxes: [
      {
        id: "source1",
        code: "INB-DEMO-001",
        cell: "А-1-1",
        units: units.slice(0, 10),
        closed: true,
      },
      {
        id: "source2",
        code: "INB-DEMO-002",
        cell: "А-1-1",
        units: units.slice(10),
        closed: true,
      },
    ],
    shipmentBoxes: [],
    stockTotal: 12,
    selectedBoxId: null,
    picked: 0,
    kizHistory: Object.fromEntries(
      units.map((u) => [
        u.kiz,
        { unitId: u.id, intakeId: u.intakeId, shipmentId: null },
      ]),
    ),
  };
}
export function saveDemoState(
  state: DemoState,
  storage: Pick<Storage, "setItem">,
) {
  storage.setItem(storageKey, JSON.stringify(state));
}
export function loadDemoState(storage: Pick<Storage, "getItem">): DemoState {
  try {
    const state = JSON.parse(storage.getItem(storageKey) || "null");
    return state &&
      Array.isArray(state.sourceBoxes) &&
      Array.isArray(state.shipmentBoxes) &&
      state.kizHistory
      ? state
      : createDemoState();
  } catch {
    return createDemoState();
  }
}
function newBox(s: DemoState) {
  let n = s.shipmentBoxes.length + 1;
  while (s.shipmentBoxes.some((b) => b.id === "new" + n)) n++;
  const b = {
    id: "new" + n,
    code: "WHB-DEMO-" + String(n).padStart(3, "0"),
    cell: "Сортировка",
    units: [] as Unit[],
    closed: false,
  };
  s.shipmentBoxes.push(b);
  s.selectedBoxId = b.id;
  return b;
}
function track(s: DemoState, units: Unit[]) {
  for (const u of units)
    if (u.kiz)
      s.kizHistory[u.kiz] = {
        unitId: u.id,
        intakeId: u.intakeId,
        shipmentId: "demo-shipment",
      };
  s.picked = s.shipmentBoxes.reduce((n, b) => n + b.units.length, 0);
}
export function reduceDemo(
  state: DemoState,
  action: DemoAction,
): { state: DemoState; error?: string } {
  if (action.type === "reset") return { state: createDemoState() };
  const s = structuredClone(state);
  const reject = (error: string) => ({ state, error });
  if (action.type === "createBox") {
    newBox(s);
    return { state: s };
  }
  if (action.type === "pickWholeBox") {
    const source = s.sourceBoxes.find((b) => b.id === action.boxId);
    if (!source) return reject("Короб не найден");
    if (!source.units.length) return { state };
    let target = s.shipmentBoxes.find((b) => b.id === source.id);
    if (target) {
      target.units.push(...source.units);
    } else {
      target = { ...source, cell: "Сортировка", units: [...source.units] };
      s.shipmentBoxes.push(target);
    }
    source.units = [];
    s.selectedBoxId = target.id;
    track(s, target.units);
    return { state: s };
  }
  if (action.type === "pickWholeCell") {
    let current = s;
    for (const b of s.sourceBoxes.filter((b) => b.cell === action.cell)) {
      const r = reduceDemo(current, { type: "pickWholeBox", boxId: b.id });
      if (r.error) return reject(r.error);
      current = r.state;
    }
    return { state: current };
  }
  if (action.type === "pickPartial") {
    const box = s.sourceBoxes.find((b) => b.id === action.boxId);
    if (!box) return reject("Исходный короб не найден");
    if (!Number.isInteger(action.quantity) || action.quantity < 1)
      return reject("Укажите целое положительное количество");
    const candidates = box.units.filter(
      (u) => u.productId === action.productId,
    );
    if (action.quantity > candidates.length)
      return reject("В коробе недостаточно выбранного товара");
    const marked = candidates.filter((u) => u.kiz);
    if (marked.length && new Set(action.kizCodes).size !== action.quantity)
      return reject("Отсканируйте конкретные КИЗ выбранных единиц");
    let selected = marked.length
      ? candidates.filter((u) => u.kiz && action.kizCodes.includes(u.kiz))
      : candidates.slice(0, action.quantity);
    if (selected.length !== action.quantity)
      return reject("КИЗ не относится к выбранному товару и коробу");
    const target =
      s.shipmentBoxes.find((b) => b.id === s.selectedBoxId && !b.closed) ||
      newBox(s);
    target.units.push(...selected);
    box.units = box.units.filter((u) => !selected.some((x) => x.id === u.id));
    track(s, selected);
    return { state: s };
  }
  if (action.type === "verifyKiz") {
    const b = s.shipmentBoxes.find((x) => x.id === action.boxId),
      u = b?.units.find((x) => x.kiz === action.kiz);
    if (!u || (action.productId && u.productId !== action.productId))
      return reject("КИЗ не относится к выбранному товару и коробу");
    return { state };
  }
  if (action.type === "addUnit") {
    const box = s.shipmentBoxes.find((b) => b.id === action.boxId);
    if (!box) return reject("Выберите короб отгрузки");
    const all = s.shipmentBoxes.flatMap((b) => b.units);
    const prior = all.find((u) => u.id === action.unit.id);
    if (prior) return { state };
    const h = action.unit.kiz ? s.kizHistory[action.unit.kiz] : null;
    if (h && h.unitId !== action.unit.id)
      return reject("Этот КИЗ уже принадлежит другой единице");
    if (box.closed)
      return reject("Короб закрыт: откройте его состав для изменения");
    for (const b of s.sourceBoxes)
      b.units = b.units.filter((u) => u.id !== action.unit.id);
    box.units.push(action.unit);
    track(s, [action.unit]);
    return { state: s };
  }
  if (action.type === "openBox") {
    const box = s.shipmentBoxes.find((b) => b.id === action.boxId);
    if (!box) return reject("Короб не найден");
    box.closed = false;
    s.selectedBoxId = box.id;
    return { state: s };
  }
  if (action.type === "removeUnit") {
    const box = s.shipmentBoxes.find((b) => b.id === action.boxId);
    const unit = box?.units.find((u) => u.id === action.unitId);
    if (!box || !unit) return reject("Единица не найдена");
    box.units = box.units.filter((u) => u.id !== unit.id);
    const source = s.sourceBoxes.find((b) => b.id === "source1")!;
    source.units.push(unit);
    if (unit.kiz)
      s.kizHistory[unit.kiz] = {
        unitId: unit.id,
        intakeId: unit.intakeId,
        shipmentId: null,
      };
    track(s, []);
    return { state: s };
  }
  if (action.type === "closeBox") {
    const box = s.shipmentBoxes.find((b) => b.id === action.boxId);
    if (!box) return reject("Короб не найден");
    box.closed = true;
    const next = s.shipmentBoxes.find((b) => b.id !== box.id && !b.closed);
    s.selectedBoxId = next?.id ?? newBox(s).id;
    return { state: s };
  }
  return reject("Неизвестное действие");
}
