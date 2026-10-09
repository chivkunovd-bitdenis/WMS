import {
  Box, Container, InboundDoc, InboundStatus, Order, Placement, SORTING, productById, sellerById,
} from "./data";

const collator = new Intl.Collator("ru", { numeric: true });

export const ruPlural = (n: number, one: string, few: string, many: string) => {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a >= 11 && a <= 14) return many;
  if (b === 1) return one;
  if (b >= 2 && b <= 4) return few;
  return many;
};

export const ordersLabel = (n: number) => `${n} ${ruPlural(n, "заказ", "заказа", "заказов")}`;

const MSK = new Intl.DateTimeFormat("ru-RU", { timeZone: "Europe/Moscow", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const parts = (iso: string) => Object.fromEntries(MSK.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
export const fmtShort = (iso: string) => { const q = parts(iso); return `${q.day}.${q.month} ${q.hour}:${q.minute}`; };
export const fmtFull = (iso: string) => { const q = parts(iso); return `${q.day}.${q.month}.${q.year} ${q.hour}:${q.minute}`; };
/** «Сейчас» макета зафиксировано, чтобы подсветка близкого срока была одинаковой у всех. */
export const MOCK_NOW = new Date("2026-10-09T21:00:00+03:00").getTime();
export const isDeadlineNear = (iso: string) => new Date(iso).getTime() < MOCK_NOW + 6 * 3600 * 1000;

// ---------------- Подбор (WMS-711) ----------------

export const supplyOrders = (orders: Order[], supplyIds: string[]) => orders.filter((o) => o.supplyId && supplyIds.includes(o.supplyId));

export const plannedOf = (orders: Order[], supplyIds: string[], productId: string) =>
  supplyOrders(orders, supplyIds).filter((o) => o.productId === productId).length;

export const remainingOf = (orders: Order[], supplyIds: string[], productId: string) =>
  supplyOrders(orders, supplyIds).filter((o) => o.productId === productId && !o.picked).length;

/** WMS-711 R5 / решение (а): взять = min(доступно в месте, осталось подобрать по товару). */
export const takeAt = (p: Placement, orders: Order[], supplyIds: string[]) =>
  Math.max(0, Math.min(p.qty, remainingOf(orders, supplyIds, p.productId)));

export const locLabel = (code: string) => (code === SORTING ? "Без ячейки" : `Ячейка ${code}`);

const pathKey = (p: Placement, depth: number) => `${p.locCode}:${p.path.slice(0, depth + 1).map((c) => c.code).join("/")}`;

/** Маршрут: ячейки в натуральном порядке кода, «Без ячейки» последней; внутри ячейки россыпь по артикулу, затем тара по названию. */
export function routePlacements(placements: Placement[], orders: Order[], supplyIds: string[]): Placement[] {
  const needed = new Set(supplyOrders(orders, supplyIds).map((o) => o.productId));
  return placements
    .filter((p) => needed.has(p.productId))
    .slice()
    .sort((a, b) => {
      if (a.locCode !== b.locCode) {
        if (a.locCode === SORTING) return 1;
        if (b.locCode === SORTING) return -1;
        return collator.compare(a.locCode, b.locCode);
      }
      const ak = a.path.length === 0 ? "0" : "1" + a.path.map((c) => c.label).join("/");
      const bk = b.path.length === 0 ? "0" : "1" + b.path.map((c) => c.label).join("/");
      if (ak !== bk) return collator.compare(ak, bk);
      return collator.compare(productById(a.productId).sku, productById(b.productId).sku);
    });
}

export type RouteRow =
  | { type: "loc"; key: string; code: string }
  | { type: "cont"; key: string; locCode: string; container: Container; depth: number }
  | { type: "prod"; key: string; placement: Placement };

export function routeRows(route: Placement[]): RouteRow[] {
  const rows: RouteRow[] = [];
  let lastLoc: string | null = null;
  const shown = new Set<string>();
  for (const p of route) {
    if (p.locCode !== lastLoc) {
      rows.push({ type: "loc", key: `loc:${p.locCode}`, code: p.locCode });
      lastLoc = p.locCode;
    }
    p.path.forEach((c, i) => {
      const k = pathKey(p, i);
      if (!shown.has(k)) {
        shown.add(k);
        rows.push({ type: "cont", key: `cont:${k}`, locCode: p.locCode, container: c, depth: i });
      }
    });
    rows.push({ type: "prod", key: `prod:${p.key}`, placement: p });
  }
  return rows;
}

export type Source = { kind: "location"; locCode: string } | { kind: "container"; locCode: string; container: Container; path: Container[] };

export const sourceMatches = (src: Source, p: Placement) => {
  if (p.locCode !== src.locCode) return false;
  if (src.kind === "location") return p.path.length === 0;
  return p.path.some((c) => c.code === src.container.code);
};

export function findSourceByCode(code: string, placements: Placement[]): Source | null {
  const c = code.trim();
  if (placements.some((p) => p.locCode === c)) return { kind: "location", locCode: c };
  for (const p of placements) {
    const idx = p.path.findIndex((x) => x.code === c);
    if (idx >= 0) return { kind: "container", locCode: p.locCode, container: p.path[idx], path: p.path.slice(0, idx + 1) };
  }
  return null;
}

export const sourceRowKey = (src: Source, rows: RouteRow[]) => {
  if (src.kind === "container") {
    const r = rows.find((x) => x.type === "cont" && x.container.code === src.container.code && x.locCode === src.locCode);
    if (r) return r.key;
  }
  return rows.find((x) => x.type === "loc" && x.code === src.locCode)?.key ?? null;
};

export const placementLabel = (p: Placement) => {
  const box = p.path[p.path.length - 1];
  if (p.locCode === SORTING) return "Без ячейки";
  return box ? `${p.locCode} · ${box.label}` : p.locCode;
};

// ---------------- Упаковка (WMS-737) ----------------

export type Underpick = { productId: string; name: string; sku: string; count: number };

/** Недобор по товару = сумма «план − подобрано» по заказам поставки (WB: заказ = 1 шт.). */
export function underpicks(orders: Order[], supplyId: string): Underpick[] {
  const map = new Map<string, number>();
  for (const o of orders.filter((x) => x.supplyId === supplyId && !x.picked)) {
    map.set(o.productId, (map.get(o.productId) ?? 0) + 1);
  }
  return [...map.entries()]
    .map(([productId, count]) => {
      const p = productById(productId);
      return { productId, name: `${p.name}, р. ${p.size}`, sku: p.sku, count };
    })
    .sort((a, b) => b.count - a.count || collator.compare(a.name, b.name));
}

export const pieceWord = (n: number) => ruPlural(n, "штука", "штуки", "штук");
export const notPickedVerb = (n: number) => ruPlural(n, "Не подобрана", "Не подобраны", "Не подобрано");

export const boxUnits = (b: Box) => b.orderIds.length;

// ---------------- Приёмка (WMS-736) ----------------

export const inboundStatusRu = (s: InboundStatus) =>
  s === "draft" ? "Черновик" : s === "submitted" ? "Передано на склад" : s === "receiving" ? "Приёмка" : s === "sorting" ? "В сортировке" : "Оприходовано";

export const inboundStatusColor = (s: InboundStatus) =>
  s === "submitted" ? "var(--primary)" : s === "receiving" ? "var(--warning)" : s === "sorting" ? "var(--primary)" : s === "done" ? "var(--success)" : "var(--text2)";

export type InboundFilters = { status: InboundStatus | "all"; sellerId: string | "all"; search: string };
export const noFilters: InboundFilters = { status: "all", sellerId: "all", search: "" };
export const activeFilterCount = (f: InboundFilters) => (f.status !== "all" ? 1 : 0) + (f.sellerId !== "all" ? 1 : 0) + (f.search.trim() ? 1 : 0);

export function matchesSearch(doc: InboundDoc, q: string) {
  const n = q.trim().toLowerCase();
  if (!n) return true;
  const hay = [
    doc.displayNumber, doc.documentNumber, doc.waybill ?? "", sellerById(doc.sellerId).name,
    ...doc.lines.flatMap((l) => [productById(l.productId).name, productById(l.productId).sku]),
  ].join(" ").toLowerCase();
  return hay.includes(n);
}

/** Веб: все документы, новые сверху (дата привоза, иначе дата создания). */
export function filterInbound(docs: InboundDoc[], f: InboundFilters) {
  return docs
    .filter((x) => f.status === "all" || x.status === f.status)
    .filter((x) => f.sellerId === "all" || x.sellerId === f.sellerId)
    .filter((x) => matchesSearch(x, f.search))
    .slice()
    .sort((a, b) => collator.compare(b.plannedDate ?? b.createdAt, a.plannedDate ?? a.createdAt));
}

export const inboundOpenMode = (d: InboundDoc): "draft" | "receiving" | "sorting" | "view" => {
  if (d.status === "draft") return d.createdBySeller ? "view" : "draft";
  if (d.status === "submitted" || d.status === "receiving") return "receiving";
  if (d.status === "sorting" && d.sortingRemaining > 0) return "sorting";
  return "view";
};
