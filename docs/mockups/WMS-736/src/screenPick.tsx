import React, { useEffect, useMemo, useRef, useState } from "react";
import { Placement, SORTING, products, productById } from "./data";
import {
  RouteRow, Source, findSourceByCode, locLabel, placementLabel, plannedOf, remainingOf, routePlacements, routeRows,
  sourceMatches, sourceRowKey, supplyOrders, takeAt,
} from "./logic";
import { World, useScan, useStore } from "./store";
import { Btn, Dialog, Field, Icon, Photo, Scaffold } from "./ui";

/** Подбор FBS на ТСД по WMS-711: маршрут по ячейкам, блок открытого места, экран не уезжает. */
export function PickScreen({ supplyIds, single }: { supplyIds: string[]; single: boolean }) {
  const s = useStore();
  const w = s.w;
  const [source, setSource] = useState<Source | null>(null);
  const [chooser, setChooser] = useState<null | { productId: string; choices: Placement[] }>(null);
  const [manual, setManual] = useState<null | { productId: string; choices: Placement[]; chosen: Placement | null }>(null);
  const [qty, setQty] = useState("1");
  const listRef = useRef<HTMLDivElement>(null);

  const route = useMemo(() => routePlacements(w.placements, w.orders, supplyIds), [w.placements, w.orders, supplyIds]);
  const rows = useMemo(() => routeRows(route), [route]);
  const ords = supplyOrders(w.orders, supplyIds);
  const total = ords.length;
  const picked = ords.filter((o) => o.picked).length;
  const complete = total > 0 && picked === total;

  // R3: скан короба/ячейки один раз переводит маршрут к этому месту. Скан товара маршрут не двигает (R6).
  const sourceKey = source ? (source.kind === "container" ? `c:${source.container.code}` : `l:${source.locCode}`) : null;
  useEffect(() => {
    if (!source || !listRef.current) return;
    const key = sourceRowKey({ kind: "location", locCode: source.locCode }, rows);
    const el = key ? listRef.current.querySelector<HTMLElement>(`[data-row="${CSS.escape(key)}"]`) : null;
    if (el) listRef.current.scrollTo({ top: el.offsetTop, behavior: "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceKey]);

  const block = source ? route.filter((p) => sourceMatches(source, p)) : [];

  const doPick = (p: Placement, n = 1) => {
    s.update((x: World) => {
      let orders = x.orders;
      const picks = [...x.lastPicks];
      for (let i = 0; i < n; i++) {
        const target = orders
          .filter((o) => o.supplyId && supplyIds.includes(o.supplyId) && o.productId === p.productId && !o.picked)
          .sort((a, b) => a.createdAt.localeCompare(b.createdAt))[0];
        if (!target) break;
        orders = orders.map((o) => o.id === target.id ? { ...o, picked: true, pickedFrom: p.key } : o);
        picks.push({ orderId: target.id, placementKey: p.key });
      }
      return {
        ...x, orders, lastPicks: picks,
        placements: x.placements.map((q) => q.key === p.key ? { ...q, qty: q.qty - n, pickedHere: q.pickedHere + n } : q),
      };
    });
    s.log(`POST pick/${n > 1 ? "manual" : "scan"} → ${productById(p.productId).sku} × ${n} из ${placementLabel(p)}; штука переехала на сортировку под резерв заказа: изменилось только расположение, общий остаток ФФ прежний`);
    s.flashOk();
  };

  const onScan = (raw: string) => {
    const code = raw.trim();
    const src = findSourceByCode(code, w.placements);
    if (src) {
      setSource(src);
      s.log(`POST pick/scan → ${src.kind === "container" ? `короб ${src.container.code} (${src.container.label}) в ячейке ${src.locCode}` : `ячейка ${src.locCode}`}`);
      return;
    }
    const product = products.find((p) => p.barcode === code || p.sku === code);
    if (!product) { s.flashErr("Товар не найден по штрихкоду."); s.log(`Скан «${code}» → wrong_product`); return; }
    if (plannedOf(w.orders, supplyIds, product.id) === 0 || remainingOf(w.orders, supplyIds, product.id) === 0) {
      s.flashErr("Товар не входит в состав поставки или уже подобран."); s.log(`Скан ${product.sku} → product_not_in_supply`); return;
    }
    if (source) {
      const here = route.find((p) => p.productId === product.id && sourceMatches(source, p));
      if (!here || takeAt(here, w.orders, supplyIds) === 0) {
        s.flashErr("Недостаточно неупакованного остатка в ячейке."); s.log(`Скан ${product.sku} в «${source.kind === "container" ? source.container.label : source.locCode}» → insufficient_unpacked`); return;
      }
      doPick(here);
      return;
    }
    const places = route.filter((p) => p.productId === product.id && takeAt(p, w.orders, supplyIds) > 0);
    if (places.length === 0) { s.flashErr(`Для ${product.name} нет доступного места подбора`); return; }
    if (places.length === 1) {
      const p = places[0];
      setSource(p.path.length ? { kind: "container", locCode: p.locCode, container: p.path[p.path.length - 1], path: p.path } : { kind: "location", locCode: p.locCode });
      doPick(p);
      return;
    }
    setChooser({ productId: product.id, choices: places });
  };

  const hints = [
    ...[...new Set(route.map((p) => p.locCode))].filter((c) => c !== "__SORTING__").map((c) => ({ code: c, label: `Ячейка ${c}` })),
    ...route.flatMap((p) => p.path.filter((c) => c.kind === "box").map((c) => ({ code: c.code, label: `${c.label} (${p.locCode})` }))),
    ...[...new Set(route.map((p) => p.productId))].map((id) => { const p = productById(id); return { code: p.barcode, label: `${p.sku} · ${p.name.split(" ").slice(0, 2).join(" ")}` }; }),
    { code: "4601234567890", label: "Чужой товар (ошибка)" },
  ].filter((h, i, a) => a.findIndex((x) => x.code === h.code) === i);
  useScan(onScan, hints);

  const undo = () => {
    const last = w.lastPicks.filter((lp) => ords.some((o) => o.id === lp.orderId && o.picked)).pop();
    if (!last) return;
    s.update((x) => ({
      ...x,
      lastPicks: x.lastPicks.filter((lp) => lp !== last),
      orders: x.orders.map((o) => o.id === last.orderId ? { ...o, picked: false, pickedFrom: undefined } : o),
      placements: x.placements.map((q) => q.key === last.placementKey ? { ...q, qty: q.qty + 1, pickedHere: q.pickedHere - 1 } : q),
    }));
    s.log("POST pick/set (−1) → последний подбор отменён, штука вернулась на место");
    s.flashOk();
  };
  const canUndo = w.lastPicks.some((lp) => ords.some((o) => o.id === lp.orderId && o.picked));

  const openManual = (productId: string) => {
    const choices = route.filter((p) => p.productId === productId && takeAt(p, w.orders, supplyIds) > 0);
    setQty("1");
    setManual({ productId, choices, chosen: choices.length === 1 ? choices[0] : null });
  };
  const manualLimit = manual?.chosen ? takeAt(manual.chosen, w.orders, supplyIds) : 0;
  const qn = Number(qty);
  const qValid = qty !== "" && qn >= 1 && qn <= manualLimit;

  const srcLabel = source ? (source.kind === "container" ? `Короб: ${source.container.code}` : source.locCode === SORTING ? "Без ячейки" : `Ячейка: ${source.locCode}`) : "Сканируйте ячейку, короб или товар";

  return (
    <Scaffold title="Подбор FBS" onExit={s.back} progress={[picked, total]}>
      <div className="cellbar" style={{ background: source ? "var(--success)" : "var(--text2)" }}>
        <span className="lbl">{srcLabel}</span>
        {source ? <Btn kind="text" onClick={() => setSource(null)}>Сменить место</Btn> : null}
      </div>
      {block.length ? (
        <div className="placeblock" data-testid="place-block">
          {block.map((p) => {
            const pr = productById(p.productId);
            const take = takeAt(p, w.orders, supplyIds);
            return (
              <div className="placerow" key={p.key}>
                <Photo p={pr} w={48} h={56} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ellipsis" style={{ fontSize: 16, fontWeight: 500, lineHeight: "20px" }}>{pr.name}, {pr.size}</div>
                  <div className="ellipsis" style={{ fontSize: 15, color: "var(--text2)", lineHeight: "18px" }}>ШК {pr.barcode}</div>
                  <div className="nums">
                    <div className="n"><small>Остаток</small><b>{p.qty}</b></div>
                    <div className={`n take${take === 0 ? " zero" : ""}`}><small>Взять</small><b>{take}</b></div>
                    <div className="n"><small>Собрано</small><b style={{ color: p.pickedHere ? "var(--success)" : undefined }}>{p.pickedHere}</b></div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
      {/* Предложение макета: «Отменить последний» в строке «Маршрут», чтобы маршруту осталось место на 360×640. */}
      <div className="sectionbar" style={{ display: "flex", alignItems: "center", padding: "4px 8px 4px 14px", minHeight: 52 }}>
        <span style={{ flex: 1 }}>Маршрут</span>
        <Btn kind="outlined" h={44} disabled={!canUndo} onClick={undo}>Отменить последний</Btn>
      </div>
      <div className="scroll" ref={listRef} style={{ flex: 1, position: "relative", background: "var(--surface)" }} data-testid="route">
        {rows.map((r: RouteRow) => {
          if (r.type === "loc") {
            const cur = source?.locCode === r.code;
            return <div key={r.key} data-row={r.key} className={`route-loc${cur ? " cur" : ""}`}>{locLabel(r.code)}</div>;
          }
          if (r.type === "cont") {
            const cur = source?.kind === "container" && source.locCode === r.locCode && source.path.some((c) => c.code === r.container.code);
            return (
              <div key={r.key} data-row={r.key} className={`route-cont${cur ? " cur" : ""}`} style={{ paddingLeft: 12 + r.depth * 14 }}>
                <Icon name={r.container.kind === "pallet" ? "pallet" : "box"} size={16} />{r.container.label} · {r.container.code}
              </div>
            );
          }
          const p = r.placement;
          const pr = productById(p.productId);
          const remaining = remainingOf(w.orders, supplyIds, p.productId);
          const done = remaining === 0;
          const take = takeAt(p, w.orders, supplyIds);
          const cur = source ? sourceMatches(source, p) : false;
          return (
            <div key={r.key} data-row={r.key} className={`route-prod tap${done ? " done" : ""}${cur ? " cur" : ""}`} style={{ paddingLeft: 12 + p.path.length * 14 }} onClick={() => openManual(p.productId)}>
              <Photo p={pr} w={44} h={52} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                  <span className="ellipsis" style={{ fontSize: 16, flex: 1 }}>{pr.name}, {pr.size}</span>
                  <b style={{ fontSize: 16, color: done ? "var(--success)" : "var(--error)", whiteSpace: "nowrap" }}>{done ? "Собрано" : `${remaining} шт.`}</b>
                </div>
                <div className="ellipsis" style={{ fontSize: 15, color: "var(--text2)" }}>ШК {pr.barcode}</div>
                <div className="ellipsis" style={{ fontSize: 15, color: "var(--text2)" }}>Остаток <b style={{ color: "var(--text)" }}>{p.qty}</b> · Взять <b style={{ color: take ? "var(--error)" : "var(--text)" }}>{take}</b> · Собрано <b style={{ color: "var(--text)" }}>{p.pickedHere}</b></div>
              </div>
            </div>
          );
        })}
        <div style={{ height: 24 }} />
      </div>
      {complete ? (
        <div style={{ display: "flex", gap: 8, padding: 8, background: "var(--surface)", flex: "none" }}>
          <Btn kind="filled" h={64} fs={18} style={{ flex: 1 }} onClick={() => single ? s.replace({ name: "pack", supplyId: supplyIds[0] }) : s.push({ name: "pack-group", supplyIds })}>К упаковке</Btn>
          <Btn kind="success" h={64} fs={18} style={{ flex: 1 }} onClick={() => { s.update((x) => ({ ...x, fbsTab: "work" })); s.resetTo([{ name: "home" }, { name: "fbs" }]); }}>Завершить подбор</Btn>
        </div>
      ) : null}

      {chooser ? (
        <Dialog title="Откуда подобрать товар" onDismiss={() => setChooser(null)} actions={<Btn kind="text" onClick={() => setChooser(null)}>Отмена</Btn>}>
          <div style={{ marginBottom: 6 }}>{productById(chooser.productId).name}</div>
          {chooser.choices.map((p) => (
            <Btn key={p.key} kind="text" block onClick={() => { setChooser(null); setSource(p.path.length ? { kind: "container", locCode: p.locCode, container: p.path[p.path.length - 1], path: p.path } : { kind: "location", locCode: p.locCode }); doPick(p); }}>
              {placementLabel(p)} · доступно {takeAt(p, w.orders, supplyIds)}
            </Btn>
          ))}
        </Dialog>
      ) : null}
      {manual && !manual.chosen && manual.choices.length > 0 ? (
        <Dialog title="Выберите ячейку" onDismiss={() => setManual(null)} actions={<Btn kind="text" onClick={() => setManual(null)}>Отмена</Btn>}>
          <div style={{ marginBottom: 8 }}>{productById(manual.productId).name}</div>
          {manual.choices.map((p) => <Btn key={p.key} kind="text" block onClick={() => setManual({ ...manual, chosen: p })}>{placementLabel(p)} · доступно {takeAt(p, w.orders, supplyIds)}</Btn>)}
        </Dialog>
      ) : null}
      {manual && manual.choices.length === 0 ? (
        <Dialog title="Ручной подбор" onDismiss={() => setManual(null)} actions={<Btn kind="text" onClick={() => setManual(null)}>Закрыть</Btn>}>
          Для товара нет ячейки с доступным количеством.
        </Dialog>
      ) : null}
      {manual && manual.chosen ? (
        <Dialog
          title="Ручной подбор"
          onDismiss={() => setManual(null)}
          actions={<>
            <Btn kind="text" onClick={() => setManual(null)}>Отмена</Btn>
            <Btn kind="filled" disabled={!qValid} onClick={() => { const c = manual.chosen!; setManual(null); doPick(c, qn); }}>Сохранить</Btn>
          </>}
        >
          <div>{productById(manual.productId).name}</div>
          <div style={{ color: "var(--text2)", marginTop: 4 }}>{placementLabel(manual.chosen)} · можно взять до {manualLimit} шт.</div>
          <Field label="Количество" value={qty} inputMode="numeric" autoFocus onChange={setQty} onEnter={() => { if (qValid) { const c = manual.chosen!; setManual(null); doPick(c, qn); } }} error={qty !== "" && !qValid} help={qty !== "" && !qValid ? `Введите от 1 до ${manualLimit}` : undefined} />
        </Dialog>
      ) : null}
    </Scaffold>
  );
}
