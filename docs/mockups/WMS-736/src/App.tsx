import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Order } from "./data";
import { Orientation, Route, ScanHint, Store, StoreCtx, World, freshWorld, isLandscape, orientationLabel } from "./store";
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

type Scenario = { id: string; title: string; tasks: string; steps: string[]; start: () => { w: World; stack: Route[] }; orientation?: Orientation };

const scenarios: Scenario[] = [
  {
    id: "all", title: "Весь путь FBS с начала", tasks: "713 · 711 · 737 · 738 · 739",
    steps: ["FBS → «Выбрать все» → «Создать поставки (10)»", "«Создать» → Белова создана; у «Мода Плюс» — «Создать без WB 5911384333» → создана → «Готово»", "Общий подбор двух поставок по маршруту → «К упаковке»", "Поставка → «Открыть» короб / «+ Создать короб» → сканы → «Упаковать» → «Передать поставку в WB»"],
    start: () => ({ w: freshWorld(), stack: [{ name: "home" }] }),
  },
  {
    id: "inbound", title: "Приёмка: фильтры и поиск", tasks: "WMS-736",
    steps: ["«Фильтры» справа над списком", "Статус «Приёмка» → селлер «ИП Белова» → «Показать»", "Снять один фильтр крестиком на чипе, затем «Сбросить»", "Поиск «блузка» или «НК-4402» (накладная)", "Открыть «Оприходовано» — только просмотр; скан даёт ошибку", "Открыть «В сортировке» с остатком — экран сортировки; назад — фильтры на месте"],
    start: () => ({ w: freshWorld(), stack: [{ name: "home" }, { name: "inbound" }] }),
  },
  {
    id: "create", title: "Создание поставок: отказ группы", tasks: "WMS-713 · расследование 741",
    steps: ["«Выбрать все» → «Создать поставки (10)»", "Группы проверяются по одной (так сейчас, замер — WMS-741)", "У «Мода Плюс»: причина с номером заказа и кнопка «Создать без WB 5911384333»", "«Создать» — создана Белова, кнопка «Создать» не стала немой: у «Мода Плюс» своя кнопка", "«Создать без WB 5911384333» → создано → главная кнопка «Готово» → общий подбор двух поставок"],
    start: () => ({ w: freshWorld(), stack: [{ name: "home" }, { name: "fbs" }] }),
  },
  {
    id: "pick", title: "Подбор по ячейкам", tasks: "WMS-711 (в работе) · 740",
    steps: ["Скан «Д-1-9» → одна строка места и одна строка товара, маршрут встал на ячейку", "Скан ШК юбки → числа меняются, экран не двигается", "Скан «Ж-1-18» → скан ШК брюк: короб в ячейке один (№ 30) — взято из него", "Скан «Ж-1-7» → скан ШК платья 46: «в коробах № 8, № 9 — отсканируйте короб» → скан «INB-000398» → скан ШК платья", "Ж-1-14: «Не нужно — взято из Ж-1-7»; ещё раз ШК платья → «уже подобран полностью» (держится до следующего действия)", "ШК лонгслива при любом месте → взят «Без ячейки» сразу; ↶ вверху — отменить последний; в конце «К упаковке»"],
    start: () => { const w = withSupplies(freshWorld()); return { w, stack: [{ name: "home" }, { name: "fbs" }, { name: "pick", supplyIds: [SUP_A, SUP_B], single: false }] }; },
  },
  {
    id: "under", title: "Недобор на упаковке", tasks: "WMS-737",
    steps: ["«В работе» → поставка «ИП Белова»: недобор виден уже на экране поставки", "«Упаковка» → жёлтая строка «Не подобрана 1 штука: Лонгслив…», у заказа пометка «Не подобран» — всё доступно", "Назад → «Подбор» → скан ШК лонгслива (взят «Без ячейки» сразу)", "«К упаковке» → предупреждения нет; «Назад» ведёт на поставку, а не в подбор"],
    start: () => { const w = pickAllExcept(withSupplies(freshWorld()), ["o2"]); return { w, stack: [{ name: "home" }, { name: "fbs" }] }; },
  },
  {
    id: "boxes", title: "Отменить короб", tasks: "WMS-738",
    steps: ["«Короб №1 · 2 шт» → «Открыть» → «Очистить короб» → подтвердить", "Короб пуст — кнопка стала «Удалить короб» → подтвердить → короба нет", "«Короб №2» (пустой) → «Открыть» → «Удалить короб» или «Отмена»", "«+ Создать короб» → скан ШК блузки / QR заказа — кладётся в открытый короб"],
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
    steps: ["Упакованы 5 из 6 — «Передать поставку в WB» внизу уже есть", "Нажать: в подтверждении предупреждение «Не упаковано: 1 заказ — WB …», передать можно", "Или сначала «Упаковать» у последнего заказа — предупреждения нет", "«Передать в WB» → «Поставка передана в WB»; назад — в списке задания «Передана в WB»"],
    start: () => {
      const w0 = pickAllExcept(withSupplies(freshWorld()), []);
      const w: World = { ...w0, orders: w0.orders.map((o) => o.supplyId === SUP_A && o.id !== "o6" ? { ...o, packed: true } : o) };
      return { w, stack: [{ name: "home" }, { name: "fbs" }, { name: "pack-group", supplyIds: [SUP_A, SUP_B] }, { name: "pack", supplyId: SUP_A, groupIds: [SUP_A, SUP_B] }] };
    },
  },
  {
    id: "orient", title: "Положение экрана", tasks: "WMS-707", orientation: "portrait",
    steps: ["На главном внизу «Вертикально» → выбрать «Горизонтально»: экран сразу горизонтальный, плитки 2×2", "Обновить страницу браузера (как перезапуск приложения) — положение то же", "FBS → «В работе» → задание → подбор: слева место и товар, справа маршрут; сканы как обычно", "«К упаковке» → поставка → упаковка; приёмка и окна фильтров — ничего не наезжает, кнопка внизу видна", "«Горизонтально, перевёрнуто» / «Вертикально, перевёрнуто» — метка «▲ сканер» на корпусе с другой стороны, изображение прямое"],
    start: () => ({ w: withSupplies(freshWorld()), stack: [{ name: "home" }] }),
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
  const [banner, setBanner] = useState<null | { kind: "error" | "hint"; text: string }>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [hints, setHints] = useState<ScanHint[]>([]);
  const [scenario, setScenario] = useState<string>("all");
  const [sound, setSound] = useState(true);
  const [supplyLayout, setSupplyLayout] = useState<"variant" | "r8">("variant");
  // WMS-707: положение сохраняется «на устройстве» — в макете в localStorage, переживает перезагрузку страницы.
  const [orientation, setOrientationState] = useState<Orientation>(() => {
    try { return (localStorage.getItem("wms707-orientation") as Orientation) || "portrait"; } catch { return "portrait"; }
  });
  const setOrientation = (o: Orientation) => {
    setOrientationState(o);
    try { localStorage.setItem("wms707-orientation", o); } catch { /* нет хранилища — только на сеанс */ }
  };
  const [scale, setScale] = useState<number | "auto">("auto");
  const [vh, setVh] = useState(window.innerHeight);
  const [vw, setVw] = useState(window.innerWidth);
  const [scanText, setScanText] = useState("");
  const scanHandler = useRef<((c: string) => void) | null>(null);
  const backHandler = useRef<(() => boolean) | null>(null);
  const timers = useRef<{ f?: number; s?: number }>({});
  const soundRef = useRef(sound); soundRef.current = sound;

  useEffect(() => { const h = () => { setVh(window.innerHeight); setVw(window.innerWidth); }; window.addEventListener("resize", h); return () => window.removeEventListener("resize", h); }, []);

  const log = useCallback((m: string) => {
    const t = new Date(); const p = (x: number) => String(x).padStart(2, "0");
    setLogs((l) => [`${p(t.getHours())}:${p(t.getMinutes())}:${p(t.getSeconds())} ${m}`, ...l].slice(0, 60));
  }, []);
  const showFlash = useCallback((ok: boolean, msg?: string) => {
    clearTimeout(timers.current.f);
    setFlash({ ok, msg, stamp: Date.now() });
    beep(ok, soundRef.current);
    timers.current.f = window.setTimeout(() => setFlash(null), ok ? 700 : 900);
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
    flashErr: (m) => { showFlash(false); setBanner({ kind: "error", text: m }); log(`Ошибка на экране: «${m}»`); },
    hint: (m) => { beep(false, soundRef.current); setBanner({ kind: "hint", text: m }); log(`Подсказка на экране: «${m}»`); },
    snack,
    log,
    setHints,
    supplyLayout,
    orientation,
    setOrientation: (o) => { setOrientation(o); log(`Положение экрана закреплено: ${orientationLabel[o]} (сохранено на устройстве)`); },
    scanHandler,
    backHandler,
  }), [w, stack, showFlash, snack, log, supplyLayout, orientation]);
  // Плашка ошибки относится к экрану, на котором случилась: переход на другой экран её убирает.
  useEffect(() => { setBanner(null); }, [stack.length, stack[stack.length - 1]?.name]);

  const doScan = (code: string) => {
    if (!code.trim()) return;
    log(`СКАН «${code.trim()}»`);
    setBanner(null);
    if (scanHandler.current) scanHandler.current(code.trim());
  };
  const systemBack = () => { if (backHandler.current?.()) return; store.back(); };

  const startScenario = (sc: Scenario) => {
    const { w: nw, stack: ns } = sc.start();
    if (sc.orientation) setOrientation(sc.orientation);
    setW(nw); setStack(ns); setScenario(sc.id); setFlash(null); setSnack(null); setBanner(null);
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

  const land = isLandscape(orientation);
  const rev = orientation.endsWith("-rev");
  const devH = land ? 410 : 690;
  const devW = land ? 664 : 384;
  const autoScale = Math.max(0.6, Math.min(1.5, (vh - 60) / devH, (vw - 500) / devW));
  const k = scale === "auto" ? autoScale : scale;

  return (
    <StoreCtx.Provider value={store}>
      <div className="stand">
        <div style={{ width: devW * k, height: (devH + 24) * k, flex: "none" }}>
        <div className="device-wrap" style={{ transform: `scale(${k})`, transformOrigin: "top left", width: devW }}>
          <div className={`device${land ? " land" : ""}`}>
            {/* Метка «верх корпуса» (окно сканера): у перевёрнутых положений корпус повёрнут, а картинка на экране — нет. */}
            <div className={`hw-mark ${land ? (rev ? "hw-right" : "hw-left") : (rev ? "hw-bottom" : "hw-top")}`}>▲ сканер</div>
            <div className={`screen${land ? " land" : ""}`} data-testid="tsd-screen">
              <div className="statusbar"><span>21:00</span><span>Wi-Fi ▾ 87%</span></div>
              <div className="screen-body">
              <div className="app" onPointerDownCapture={() => banner && setBanner(null)}>
                {screen}
                {flash ? (
                  <div key={flash.stamp} className={`flash ${flash.ok ? "ok" : "err"}`}>
                  </div>
                ) : null}
                {banner ? <div className={`banner ${banner.kind}`} data-testid={banner.kind === "error" ? "scan-error" : "scan-hint"}>{banner.text}</div> : null}
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
          </div>
          <div className="device-caption">ТСД {land ? "640 × 360" : "360 × 640"} dp · {orientationLabel[orientation].toLowerCase()} · масштаб {Math.round(k * 100)}%</div>
        </div>
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
          <div className="row-gap" style={{ marginBottom: 8 }}>
            <span className="muted">Экран поставки:</span>
            <button className={`pbtn${supplyLayout === "variant" ? " primary" : ""}`} onClick={() => setSupplyLayout("variant")}>действия внизу (предложение)</button>
            <button className={`pbtn${supplyLayout === "r8" ? " primary" : ""}`} onClick={() => setSupplyLayout("r8")}>как утверждено (WMS-584 R8)</button>
          </div>
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
