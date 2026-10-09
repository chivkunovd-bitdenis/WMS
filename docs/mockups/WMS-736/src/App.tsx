import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Order } from "./data";
import { Route, ScanHint, Store, StoreCtx, World, freshWorld } from "./store";
import { HomeScreen, InboundDocScreen, InboundListScreen } from "./screensInbound";
import { FbsOrdersScreen, PackGroupScreen, SupplyScreen, TODAY } from "./screensFbs";
import { PickScreen } from "./screenPick";
import { PackScreen } from "./screenPack";

// ---------------- сценарии (готовые исходные состояния) ----------------

const SUP_A = "sup-belova";
const SUP_B = "sup-moda";

function withSupplies(w: World): World {
  const a = ["o1", "o2", "o3", "o4", "o5", "o6"];
  const b = ["o8", "o9", "o10"];
  return {
    ...w,
    supplies: [
      { id: SUP_A, name: `FBS ${TODAY}`, sellerId: "s-belova", delivered: false, taskId: "task-17" },
      { id: SUP_B, name: `FBS ${TODAY}`, sellerId: "s-moda", delivered: false, taskId: "task-17" },
    ],
    tasks: [{ id: "task-17", number: "17", createdAt: "2026-10-09T14:05:00+03:00", supplyIds: [SUP_A, SUP_B] }],
    orders: w.orders.map((o): Order => a.includes(o.id) ? { ...o, supplyId: SUP_A } : b.includes(o.id) ? { ...o, supplyId: SUP_B } : o),
    fbsTab: "work",
  };
}

/** Подобрать всё, кроме указанных заказов, с правильным движением по местам. */
function pickAllExcept(w: World, except: string[]): World {
  let placements = w.placements;
  const orders = w.orders.map((o) => {
    if (!o.supplyId || except.includes(o.id)) return o;
    const pl = placements.filter((p) => p.productId === o.productId && p.qty > 0).sort((x, y) => x.locCode.localeCompare(y.locCode, "ru", { numeric: true }))[0];
    placements = placements.map((p) => p.key === pl.key ? { ...p, qty: p.qty - 1, pickedHere: p.pickedHere + 1 } : p);
    return { ...o, picked: true, pickedFrom: pl.key };
  });
  return { ...w, orders, placements };
}

type Scenario = { id: string; title: string; tasks: string; steps: string[]; start: () => { w: World; stack: Route[] } };

const scenarios: Scenario[] = [
  {
    id: "all", title: "Весь путь FBS с начала", tasks: "713 · 711 · 737 · 738 · 739",
    steps: ["FBS → «Выбрать все» → «Создать поставки (10)»", "Группа «Мода Плюс» несовместима: видно, какой заказ мешает (WMS-713)", "«Создать» → поставка Беловой; «Открыть общий подбор» или «Закрыть», снять галку с WB 5911384333 и создать вторую", "Подбор по маршруту → «К упаковке» → поставка → короба → упаковать → «Передать поставку в WB»"],
    start: () => ({ w: freshWorld(), stack: [{ name: "home" }] }),
  },
  {
    id: "inbound", title: "Приёмка: фильтры и поиск", tasks: "WMS-736",
    steps: ["«Фильтры» справа над списком", "Статус «Приёмка» → селлер «ИП Белова» → «Показать»", "Снять один фильтр крестиком на чипе, затем «Сбросить»", "Поиск «блузка» или «НК-4402» (накладная)", "Открыть «Оприходовано» — только просмотр; скан даёт ошибку", "Открыть «В сортировке» с остатком — экран сортировки; назад — фильтры на месте"],
    start: () => ({ w: freshWorld(), stack: [{ name: "home" }, { name: "inbound" }] }),
  },
  {
    id: "create", title: "Создание поставок: отказ группы", tasks: "WMS-713 · расследование 741",
    steps: ["«Выбрать все» → «Создать поставки (10)»", "Группы проверяются по одной, окно занято (так сейчас — WMS-741)", "У «Мода Плюс»: «Заказ WB 5911384333: Заказ отменён или брак.»", "«Создать» — создаётся только Белова; повторное «Создать» — звук успеха без действия (находка WMS-741)", "«Закрыть», снять галку с WB 5911384333, «Создать поставки (3)» → создано → общий подбор"],
    start: () => ({ w: freshWorld(), stack: [{ name: "home" }, { name: "fbs" }] }),
  },
  {
    id: "pick", title: "Подбор по ячейкам", tasks: "WMS-711 (в работе) · 740",
    steps: ["Скан ячейки «Д-1-9» → полоса «Ячейка», блок юбки, маршрут встал на ячейку", "Скан ШК юбки → числа меняются, экран не двигается", "Скан короба «INB-000398» → «Короб», блок платья и бархата; скан ШК платья 46", "Скан короба «INB-000431» (Ж-1-14) → у платья «Взять 0»; скан ШК платья → «уже подобран» (случай 08.10, WMS-740)", "Тап по строке → ручной подбор; «Отменить последний»", "Лонгслив — «Без ячейки» внизу маршрута; после всего — «К упаковке» / «Завершить подбор»"],
    start: () => { const w = withSupplies(freshWorld()); return { w, stack: [{ name: "home" }, { name: "fbs" }, { name: "pick", supplyIds: [SUP_A, SUP_B], single: false }] }; },
  },
  {
    id: "under", title: "Недобор на упаковке", tasks: "WMS-737",
    steps: ["«В работе» → карточка поставки «ИП Белова» → «Упаковка и этикетки»", "Сверху жёлтое: «Не подобрана 1 штука: Лонгслив…» — всё остальное доступно", "Назад → «Подбор» → скан ШК лонгслива (место одно — «Без ячейки»)", "«К упаковке» → предупреждения нет; «Назад» ведёт на поставку, а не в подбор (WMS-739)"],
    start: () => { const w = pickAllExcept(withSupplies(freshWorld()), ["o2"]); return { w, stack: [{ name: "home" }, { name: "fbs" }] }; },
  },
  {
    id: "boxes", title: "Отменить короб", tasks: "WMS-738",
    steps: ["Тап по строке «Короб №1 · 2 шт» → короб открыт → «Очистить короб» → подтвердить", "Короб пуст — кнопка стала «Удалить короб» → подтвердить → короба нет", "Открыть «Короб №2» (пустой) → «Удалить короб» или «Отмена»", "«Создать короб» → сканировать ШК блузки / QR заказа — кладётся в открытый короб"],
    start: () => {
      const w0 = pickAllExcept(withSupplies(freshWorld()), []);
      const w: World = { ...w0, boxes: [
        { id: "box-1", supplyId: SUP_A, number: 1, barcode: "FBS-7A1C2E90-001", orderIds: ["o3", "o4"] },
        { id: "box-2", supplyId: SUP_A, number: 2, barcode: "FBS-7A1C2E90-002", orderIds: [] },
      ] };
      return { w, stack: [{ name: "home" }, { name: "fbs" }, { name: "pack-group", supplyIds: [SUP_A, SUP_B] }, { name: "pack", supplyId: SUP_A, groupIds: [SUP_A, SUP_B] }] };
    },
  },
  {
    id: "deliver", title: "Передача без кругов", tasks: "WMS-739",
    steps: ["Упакованы 5 из 6 — внизу кнопки передачи ещё нет", "Последний заказ (внизу) → «Отметить упакованным» → внизу «Передать поставку в WB»", "Подтверждение → «Передать в WB» → «Поставка передана в WB»", "Назад → в списке задания у Беловой «Передана в WB»"],
    start: () => {
      const w0 = pickAllExcept(withSupplies(freshWorld()), []);
      const w: World = { ...w0, orders: w0.orders.map((o) => o.supplyId === SUP_A && o.id !== "o6" ? { ...o, packed: true } : o) };
      return { w, stack: [{ name: "home" }, { name: "fbs" }, { name: "pack-group", supplyIds: [SUP_A, SUP_B] }, { name: "pack", supplyId: SUP_A, groupIds: [SUP_A, SUP_B] }] };
    },
  },
];

// ---------------- звук ----------------
let audio: AudioContext | null = null;
function beep(ok: boolean, on: boolean) {
  if (!on) return;
  try {
    audio = audio ?? new AudioContext();
    const seq = ok ? [[1320, 0, 0.08]] : [[300, 0, 0.18], [240, 0.22, 0.25]];
    for (const [f, t, d] of seq) {
      const o = audio.createOscillator(); const g = audio.createGain();
      o.frequency.value = f; o.type = ok ? "sine" : "square"; g.gain.value = 0.06;
      o.connect(g); g.connect(audio.destination);
      o.start(audio.currentTime + t); o.stop(audio.currentTime + t + d);
    }
  } catch { /* звук необязателен */ }
}

export default function App() {
  const [w, setW] = useState<World>(freshWorld);
  const [stack, setStack] = useState<Route[]>([{ name: "home" }]);
  const [flash, setFlash] = useState<null | { ok: boolean; msg?: string; stamp: number }>(null);
  const [snackMsg, setSnack] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [hints, setHints] = useState<ScanHint[]>([]);
  const [scenario, setScenario] = useState<string>("all");
  const [sound, setSound] = useState(true);
  const [scale, setScale] = useState<number | "auto">("auto");
  const [vh, setVh] = useState(window.innerHeight);
  const [scanText, setScanText] = useState("");
  const scanHandler = useRef<((c: string) => void) | null>(null);
  const backHandler = useRef<(() => boolean) | null>(null);
  const timers = useRef<{ f?: number; s?: number }>({});
  const soundRef = useRef(sound); soundRef.current = sound;

  useEffect(() => { const h = () => setVh(window.innerHeight); window.addEventListener("resize", h); return () => window.removeEventListener("resize", h); }, []);

  const log = useCallback((m: string) => {
    const t = new Date(); const p = (x: number) => String(x).padStart(2, "0");
    setLogs((l) => [`${p(t.getHours())}:${p(t.getMinutes())}:${p(t.getSeconds())} ${m}`, ...l].slice(0, 60));
  }, []);
  const showFlash = useCallback((ok: boolean, msg?: string) => {
    clearTimeout(timers.current.f);
    setFlash({ ok, msg, stamp: Date.now() });
    beep(ok, soundRef.current);
    timers.current.f = window.setTimeout(() => setFlash(null), ok ? 700 : 3500);
  }, []);
  const snack = useCallback((m: string) => {
    clearTimeout(timers.current.s);
    setSnack(m);
    timers.current.s = window.setTimeout(() => setSnack(null), 2600);
  }, []);

  const store: Store = useMemo(() => ({
    w,
    update: (fn) => setW((x) => fn(x)),
    route: stack[stack.length - 1],
    depth: stack.length,
    push: (r) => setStack((st) => [...st, r]),
    replace: (r) => setStack((st) => [...st.slice(0, -1), r]),
    back: () => setStack((st) => (st.length > 1 ? st.slice(0, -1) : st)),
    resetTo: (rs) => setStack(rs),
    flashOk: () => showFlash(true),
    flashErr: (m) => { showFlash(false, m); log(`Ошибка на экране: «${m}»`); },
    snack,
    log,
    setHints,
    scanHandler,
    backHandler,
  }), [w, stack, showFlash, snack, log]);

  const doScan = (code: string) => {
    if (!code.trim()) return;
    log(`СКАН «${code.trim()}»`);
    if (scanHandler.current) scanHandler.current(code.trim());
  };
  const systemBack = () => { if (backHandler.current?.()) return; store.back(); };

  const startScenario = (sc: Scenario) => {
    const { w: nw, stack: ns } = sc.start();
    setW(nw); setStack(ns); setScenario(sc.id); setFlash(null); setSnack(null);
    setLogs([]); log(`Сценарий «${sc.title}»: исходное состояние загружено`);
  };

  const r = store.route;
  const screen = (() => {
    switch (r.name) {
      case "home": return <HomeScreen />;
      case "inbound": return <InboundListScreen />;
      case "inbound-doc": return <InboundDocScreen key={r.id} id={r.id} mode={r.mode} />;
      case "fbs": return <FbsOrdersScreen />;
      case "supply": return <SupplyScreen key={r.id} id={r.id} />;
      case "pick": return <PickScreen key={r.supplyIds.join(",")} supplyIds={r.supplyIds} single={r.single} />;
      case "pack-group": return <PackGroupScreen supplyIds={r.supplyIds} />;
      case "pack": return <PackScreen key={r.supplyId} supplyId={r.supplyId} />;
    }
  })();

  const autoScale = Math.max(0.7, Math.min(1.5, (vh - 60) / 690));
  const k = scale === "auto" ? autoScale : scale;

  return (
    <StoreCtx.Provider value={store}>
      <div className="stand">
        <div className="device-wrap" style={{ transform: `scale(${k})`, marginBottom: (k - 1) * 690 }}>
          <div className="device">
            <div className="screen" data-testid="tsd-screen">
              <div className="statusbar"><span>21:00</span><span>Wi-Fi ▾ 87%</span></div>
              <div className="app">
                {screen}
                {flash ? (
                  <div key={flash.stamp} className={`flash ${flash.ok ? "ok" : "err"}`}>
                    {!flash.ok && flash.msg ? <div className="msg" data-testid="scan-error">{flash.msg}</div> : null}
                  </div>
                ) : null}
                <div id="app-overlay" />
                {snackMsg ? <div className="snackbar">{snackMsg}</div> : null}
              </div>
              <div className="navbar">
                <button onClick={systemBack} aria-label="Системная Назад">◁</button>
                <button onClick={() => setStack([{ name: "home" }])} aria-label="Домой">○</button>
                <button aria-label="Недавние">□</button>
              </div>
            </div>
          </div>
          <div className="device-caption">ТСД 360 × 640 dp, портрет · масштаб {Math.round(k * 100)}%</div>
        </div>

        <aside className="panel">
          <h1>Макет ТСД · пакет ArtMaks 08.10</h1>
          <div className="muted">WMS-736…741 и связанные WMS-711, WMS-713. Данные вымышленные, сервер не вызывается. Слева — экран ТСД, нажимайте пальцем (мышью). Сканер — кнопками ниже.</div>

          <div className="scanner-box">
          <h2>Сканер</h2>
          {hints.length ? (
            <div className="scan-codes">
              {hints.map((h) => <button key={h.code} className="scan-code" onClick={() => doScan(h.code)}>{h.code}<small>{h.label}</small></button>)}
            </div>
          ) : <div className="muted">Этот экран сканы не принимает (как в приложении).</div>}
          <form className="scan-input" onSubmit={(e) => { e.preventDefault(); doScan(scanText); setScanText(""); }}>
            <input placeholder="Любой код + Enter" value={scanText} onChange={(e) => setScanText(e.target.value)} />
            <button className="pbtn primary" type="submit">Скан</button>
          </form>
          </div>

          <h2>Сценарии</h2>
          {scenarios.map((sc) => (
            <div key={sc.id} className={`scen${scenario === sc.id ? " active" : ""}`}>
              <div className="scen-head">
                <b>{sc.title}</b><span className="tag">{sc.tasks}</span>
                <button className="pbtn" onClick={() => startScenario(sc)}>{scenario === sc.id ? "Заново" : "Начать"}</button>
              </div>
              {scenario === sc.id ? <ol>{sc.steps.map((st) => <li key={st}>{st}</li>)}</ol> : null}
            </div>
          ))}

          <h2>Что делает система</h2>
          <div className="log" data-testid="log">{logs.length ? logs.map((l, i) => <div key={i}>{l}</div>) : <span className="muted">пока пусто</span>}</div>

          <h2>Настройки макета</h2>
          <div className="row-gap">
            <label><input type="checkbox" checked={sound} onChange={(e) => setSound(e.target.checked)} /> звук сканера</label>
            <span className="muted">масштаб:</span>
            {(["auto", 1, 1.25] as const).map((v) => <button key={String(v)} className={`pbtn${scale === v ? " primary" : ""}`} onClick={() => setScale(v)}>{v === "auto" ? "по окну" : `${v * 100}%`}</button>)}
          </div>
        </aside>
      </div>
    </StoreCtx.Provider>
  );
}
