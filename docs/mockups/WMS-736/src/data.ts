// Вымышленные, но реалистичные данные макета. Никаких обращений к API.

export type GarmentKind = "dress" | "longsleeve" | "blouse" | "skirt" | "trousers" | "turtleneck";

export type Product = {
  id: string;
  name: string;
  size: string;
  sku: string; // артикул продавца
  barcode: string;
  color: string;
  accent?: string;
  kind: GarmentKind;
};

export type Seller = { id: string; name: string };

export type Order = {
  id: string;
  wbId: number;
  productId: string;
  sellerId: string;
  createdAt: string; // ISO
  deadlineAt: string; // ISO
  supplyId: string | null;
  picked: boolean;
  pickedFrom?: string;
  packed: boolean;
  /** Заказ отменён на стороне WB уже после загрузки списка (для сценария WMS-713). */
  cancelledAtWb?: boolean;
  kizSaved?: boolean;
};

export type Supply = {
  id: string;
  name: string;
  sellerId: string;
  delivered: boolean;
  taskId: string | null;
};

export type AssemblyTask = { id: string; number: string; createdAt: string; supplyIds: string[] };

export type Box = { id: string; supplyId: string; number: number; barcode: string; orderIds: string[] };

export type Container = { kind: "box" | "pallet"; code: string; label: string };

/** Место, где лежит товар: ячейка → (палета →) короб, либо россыпь в ячейке, либо сортировка. */
export type Placement = {
  key: string;
  productId: string;
  locCode: string; // "__SORTING__" — сортировка («Без ячейки»)
  path: Container[];
  qty: number; // физически в этом месте (остаток в коробе/ячейке)
  pickedHere: number; // сколько снято отсюда в текущем подборе
};

export type InboundStatus = "draft" | "submitted" | "receiving" | "sorting" | "done";

export type InboundDoc = {
  id: string;
  displayNumber: string;
  documentNumber: string;
  waybill: string | null;
  sellerId: string;
  status: InboundStatus;
  createdBySeller: boolean;
  plannedDate: string | null; // YYYY-MM-DD
  createdAt: string;
  lines: { productId: string; planned: number; accepted: number }[];
  plannedBoxes: number | null;
  boxes: number;
  sortingRemaining: number;
  discrepancy?: boolean;
};

export const SORTING = "__SORTING__";

export const sellers: Seller[] = [
  { id: "s-belova", name: "ИП Белова А. С." },
  { id: "s-moda", name: "ООО «Мода Плюс»" },
  { id: "s-karimov", name: "ИП Каримов Р. Р." },
];

export const products: Product[] = [
  { id: "p-dress46", name: "Платье-пиджак чёрное мини приталенное офисное", size: "46", sku: "56800-001/46", barcode: "2045680000146", color: "#1f1f22", accent: "#3a3a40", kind: "dress" },
  { id: "p-long46", name: "Лонгслив со змеиным принтом облегающий приталенный", size: "46", sku: "МОД202/052/46", barcode: "2045202005246", color: "#8b7d55", accent: "#4a3f26", kind: "longsleeve" },
  { id: "p-blouse44", name: "Блузка молочная со стойкой и рукавом-фонариком", size: "44", sku: "78700-002/44", barcode: "2047870000244", color: "#f2e8d2", accent: "#d9cbb0", kind: "blouse" },
  { id: "p-velvet54", name: "Платье бархатное синее мини с запахом", size: "54", sku: "70100-003/54", barcode: "2047010000354", color: "#22408f", accent: "#162c66", kind: "dress" },
  { id: "p-skirt44", name: "Юбка плиссе зелёная миди", size: "44", sku: "61200-005/44", barcode: "2046120000544", color: "#2e7d4f", accent: "#1d5636", kind: "skirt" },
  { id: "p-turtle54", name: "Водолазка с принтом трикотажная", size: "54", sku: "МОД17/064/54", barcode: "2041706405400", color: "#a9a9b2", accent: "#6d6d78", kind: "turtleneck" },
  { id: "p-palazzo48", name: "Брюки палаццо бежевые с высокой посадкой", size: "48", sku: "33100-002/48", barcode: "2043310000248", color: "#d6bf98", accent: "#b39b72", kind: "trousers" },
];

export const productById = (id: string): Product => products.find((p) => p.id === id)!;
export const sellerById = (id: string): Seller => sellers.find((s) => s.id === id)!;

// ---- FBS: новые заказы WB -------------------------------------------------

const d = (s: string) => new Date(s).toISOString();

export function initialOrders(): Order[] {
  const base: Omit<Order, "supplyId" | "picked" | "packed">[] = [
    { id: "o1", wbId: 5938127734, productId: "p-dress46", sellerId: "s-belova", createdAt: d("2026-10-09T06:12:00+03:00"), deadlineAt: d("2026-10-11T06:12:00+03:00") },
    { id: "o2", wbId: 5938140215, productId: "p-long46", sellerId: "s-belova", createdAt: d("2026-10-09T06:40:00+03:00"), deadlineAt: d("2026-10-11T06:40:00+03:00") },
    { id: "o3", wbId: 5938161107, productId: "p-blouse44", sellerId: "s-belova", createdAt: d("2026-10-09T07:02:00+03:00"), deadlineAt: d("2026-10-11T07:02:00+03:00") },
    { id: "o4", wbId: 5938177390, productId: "p-blouse44", sellerId: "s-belova", createdAt: d("2026-10-09T07:15:00+03:00"), deadlineAt: d("2026-10-11T07:15:00+03:00") },
    { id: "o5", wbId: 5938190082, productId: "p-skirt44", sellerId: "s-belova", createdAt: d("2026-10-09T08:31:00+03:00"), deadlineAt: d("2026-10-10T02:31:00+03:00") },
    { id: "o6", wbId: 5938205561, productId: "p-palazzo48", sellerId: "s-belova", createdAt: d("2026-10-09T09:05:00+03:00"), deadlineAt: d("2026-10-11T09:05:00+03:00") },
    { id: "o7", wbId: 5911384333, productId: "p-turtle54", sellerId: "s-moda", createdAt: d("2026-10-08T21:10:00+03:00"), deadlineAt: d("2026-10-10T21:10:00+03:00"), cancelledAtWb: true },
    { id: "o8", wbId: 5938214470, productId: "p-velvet54", sellerId: "s-moda", createdAt: d("2026-10-09T09:20:00+03:00"), deadlineAt: d("2026-10-11T09:20:00+03:00") },
    { id: "o9", wbId: 5938230018, productId: "p-velvet54", sellerId: "s-moda", createdAt: d("2026-10-09T09:44:00+03:00"), deadlineAt: d("2026-10-11T09:44:00+03:00") },
    { id: "o10", wbId: 5938251906, productId: "p-turtle54", sellerId: "s-moda", createdAt: d("2026-10-09T10:02:00+03:00"), deadlineAt: d("2026-10-11T10:02:00+03:00") },
  ];
  return base.map((o) => ({ ...o, supplyId: null, picked: false, packed: false }));
}

/** Места товара на складе — дерево «ячейка → палета → короб → товар». */
export function initialPlacements(): Placement[] {
  const box = (code: string, n: number): Container => ({ kind: "box", code, label: `Короб № ${n}` });
  const pallet: Container = { kind: "pallet", code: "PAL-000007", label: "Палета № 7" };
  return [
    { key: "pl-d19-skirt", productId: "p-skirt44", locCode: "Д-1-9", path: [], qty: 3, pickedHere: 0 },
    { key: "pl-d19-blouse", productId: "p-blouse44", locCode: "Д-1-9", path: [box("INB-000412", 12)], qty: 5, pickedHere: 0 },
    { key: "pl-zh17-dress", productId: "p-dress46", locCode: "Ж-1-7", path: [box("INB-000398", 8)], qty: 12, pickedHere: 0 },
    { key: "pl-zh17-velvet", productId: "p-velvet54", locCode: "Ж-1-7", path: [box("INB-000398", 8)], qty: 4, pickedHere: 0 },
    { key: "pl-zh114-dress", productId: "p-dress46", locCode: "Ж-1-14", path: [box("INB-000431", 21)], qty: 1, pickedHere: 0 },
    { key: "pl-zh118-turtle", productId: "p-turtle54", locCode: "Ж-1-18", path: [], qty: 2, pickedHere: 0 },
    { key: "pl-zh118-palazzo", productId: "p-palazzo48", locCode: "Ж-1-18", path: [pallet, box("INB-000440", 30)], qty: 6, pickedHere: 0 },
    { key: "pl-sort-long", productId: "p-long46", locCode: SORTING, path: [], qty: 1, pickedHere: 0 },
  ];
}

// ---- Приёмка ---------------------------------------------------------------

export function initialInbound(): InboundDoc[] {
  const L = (productId: string, planned: number, accepted: number) => ({ productId, planned, accepted });
  return [
    { id: "i31", displayNumber: "№000031", documentNumber: "ПРИЕМ-26-10-09-2", waybill: "НК-4471", sellerId: "s-moda", status: "submitted", createdBySeller: true, plannedDate: "2026-10-11", createdAt: "2026-10-09T10:20:00+03:00", lines: [L("p-velvet54", 40, 0), L("p-turtle54", 60, 0)], plannedBoxes: 6, boxes: 0, sortingRemaining: 0 },
    { id: "i30", displayNumber: "№000030", documentNumber: "ПРИЕМ-26-10-09-1", waybill: null, sellerId: "s-belova", status: "draft", createdBySeller: false, plannedDate: "2026-10-10", createdAt: "2026-10-09T09:05:00+03:00", lines: [L("p-dress46", 24, 0)], plannedBoxes: null, boxes: 0, sortingRemaining: 0 },
    { id: "i29", displayNumber: "№000029", documentNumber: "ПРИЕМ-26-10-08-4", waybill: "ТТН 118204", sellerId: "s-karimov", status: "receiving", createdBySeller: true, plannedDate: "2026-10-09", createdAt: "2026-10-08T18:40:00+03:00", lines: [L("p-palazzo48", 30, 18), L("p-blouse44", 20, 20)], plannedBoxes: 4, boxes: 3, sortingRemaining: 0 },
    { id: "i28", displayNumber: "№000028", documentNumber: "ПРИЕМ-26-10-08-3", waybill: null, sellerId: "s-moda", status: "draft", createdBySeller: true, plannedDate: "2026-10-12", createdAt: "2026-10-08T16:02:00+03:00", lines: [L("p-turtle54", 80, 0)], plannedBoxes: 8, boxes: 0, sortingRemaining: 0 },
    { id: "i27", displayNumber: "№000027", documentNumber: "ПРИЕМ-26-10-08-2", waybill: "НК-4402", sellerId: "s-belova", status: "submitted", createdBySeller: true, plannedDate: "2026-10-09", createdAt: "2026-10-08T12:30:00+03:00", lines: [L("p-long46", 36, 0), L("p-dress46", 24, 0), L("p-skirt44", 18, 0)], plannedBoxes: 5, boxes: 0, sortingRemaining: 0 },
    { id: "i26", displayNumber: "№000026", documentNumber: "ПРИЕМ-26-10-07-3", waybill: null, sellerId: "s-karimov", status: "submitted", createdBySeller: true, plannedDate: "2026-10-09", createdAt: "2026-10-07T17:45:00+03:00", lines: [L("p-palazzo48", 50, 0)], plannedBoxes: 5, boxes: 0, sortingRemaining: 0 },
    { id: "i25", displayNumber: "№000025", documentNumber: "ПРИЕМ-26-10-07-2", waybill: "ТТН 117960", sellerId: "s-belova", status: "receiving", createdBySeller: true, plannedDate: "2026-10-08", createdAt: "2026-10-07T11:10:00+03:00", lines: [L("p-blouse44", 30, 30), L("p-skirt44", 12, 9)], plannedBoxes: 3, boxes: 3, sortingRemaining: 0, discrepancy: true },
    { id: "i24", displayNumber: "№000024", documentNumber: "ПРИЕМ-26-10-06-1", waybill: null, sellerId: "s-moda", status: "sorting", createdBySeller: true, plannedDate: "2026-10-07", createdAt: "2026-10-06T15:00:00+03:00", lines: [L("p-velvet54", 20, 20), L("p-turtle54", 40, 40)], plannedBoxes: 4, boxes: 4, sortingRemaining: 22 },
    { id: "i23", displayNumber: "№000023", documentNumber: "ПРИЕМ-26-10-05-2", waybill: "НК-4310", sellerId: "s-belova", status: "sorting", createdBySeller: true, plannedDate: "2026-10-06", createdAt: "2026-10-05T13:20:00+03:00", lines: [L("p-dress46", 30, 30)], plannedBoxes: 3, boxes: 3, sortingRemaining: 0 },
    { id: "i22", displayNumber: "№000022", documentNumber: "ПРИЕМ-26-10-03-1", waybill: null, sellerId: "s-karimov", status: "done", createdBySeller: true, plannedDate: "2026-10-04", createdAt: "2026-10-03T10:00:00+03:00", lines: [L("p-palazzo48", 40, 40)], plannedBoxes: 4, boxes: 4, sortingRemaining: 0 },
    { id: "i21", displayNumber: "№000021", documentNumber: "ПРИЕМ-26-10-01-2", waybill: "НК-4188", sellerId: "s-belova", status: "done", createdBySeller: true, plannedDate: "2026-10-02", createdAt: "2026-10-01T09:30:00+03:00", lines: [L("p-long46", 24, 24), L("p-blouse44", 30, 29)], plannedBoxes: 4, boxes: 4, sortingRemaining: 0, discrepancy: true },
    { id: "i20", displayNumber: "№000020", documentNumber: "ПРИЕМ-26-09-29-1", waybill: null, sellerId: "s-moda", status: "done", createdBySeller: true, plannedDate: "2026-09-30", createdAt: "2026-09-29T14:15:00+03:00", lines: [L("p-velvet54", 30, 30)], plannedBoxes: 3, boxes: 3, sortingRemaining: 0 },
  ];
}
