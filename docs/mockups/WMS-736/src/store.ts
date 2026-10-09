import { createContext, useContext, useEffect, useRef } from "react";
import {
  AssemblyTask, Box, InboundDoc, Order, Placement, Supply, initialInbound, initialOrders, initialPlacements,
} from "./data";
import { InboundFilters, noFilters } from "./logic";

export type Route =
  | { name: "home" }
  | { name: "inbound" }
  | { name: "inbound-doc"; id: string; mode: "draft" | "receiving" | "sorting" | "view" }
  | { name: "fbs" }
  | { name: "supply"; id: string }
  | { name: "pick"; supplyIds: string[]; single: boolean }
  | { name: "pack-group"; supplyIds: string[] }
  | { name: "pack"; supplyId: string; groupIds?: string[] };

export type LastPick = { orderId: string; placementKey: string };

export type World = {
  orders: Order[];
  placements: Placement[];
  supplies: Supply[];
  tasks: AssemblyTask[];
  boxes: Box[];
  inbound: InboundDoc[];
  inboundFilters: InboundFilters;
  fbsTab: "new" | "work";
  marketplace: "wb" | "ozon";
  sellerFilter: string | null;
  selected: string[];
  lastPicks: LastPick[];
  /** Ключи удаления коробов, сохранённые до подтверждённого результата (WMS-738 R5). */
  boxDeleteKeys: Record<string, string>;
};

export const freshWorld = (): World => ({
  orders: initialOrders(),
  placements: initialPlacements(),
  supplies: [],
  tasks: [],
  boxes: [],
  inbound: initialInbound(),
  inboundFilters: noFilters,
  fbsTab: "new",
  marketplace: "wb",
  sellerFilter: null,
  selected: [],
  lastPicks: [],
  boxDeleteKeys: {},
});

export type ScanHint = { code: string; label: string };

export type Store = {
  w: World;
  update: (fn: (w: World) => World) => void;
  route: Route;
  depth: number;
  push: (r: Route) => void;
  replace: (r: Route) => void;
  back: () => void;
  resetTo: (rs: Route[]) => void;
  flashOk: () => void;
  flashErr: (msg: string) => void;
  snack: (msg: string) => void;
  log: (msg: string) => void;
  setHints: (h: ScanHint[]) => void;
  scanHandler: React.MutableRefObject<((code: string) => void) | null>;
  backHandler: React.MutableRefObject<(() => boolean) | null>;
};

export const StoreCtx = createContext<Store | null>(null);
export const useStore = () => useContext(StoreCtx)!;

/** Экран подписывается на сканер, пока он на переднем плане (как LaunchedEffect + scannerManager.scans). */
export function useScan(handler: (code: string) => void, hints: ScanHint[]) {
  const s = useStore();
  const ref = useRef(handler);
  ref.current = handler;
  const hintsKey = JSON.stringify(hints);
  useEffect(() => {
    s.scanHandler.current = (c) => ref.current(c);
    s.setHints(hints);
    return () => { s.scanHandler.current = null; s.setHints([]); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hintsKey]);
}

/** Перехват системной «Назад» (BackHandler): вернуть true, если экран обработал сам. */
export function useBackHandler(handler: () => boolean) {
  const s = useStore();
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    s.backHandler.current = () => ref.current();
    return () => { s.backHandler.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

let seq = 100;
export const newId = (prefix: string) => `${prefix}-${++seq}`;
