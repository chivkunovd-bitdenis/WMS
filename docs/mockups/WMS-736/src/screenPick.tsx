import React, { useEffect, useMemo, useRef, useState } from "react";
import { Placement, Product, SORTING, products, productById } from "./data";
import {
  RouteRow, Source, findSourceByCode, locLabel, placementLabel, plannedOf, remainingOf, routePlacements, routeRows,
  sourceMatches, sourceRowKey, supplyOrders, takeAt,
} from "./logic";
import { World, isLandscape, useScan, useStore } from "./store";
import { Btn, Dialog, Field, Icon, Photo, Scaffold } from "./ui";

/** Короткое имя для сообщений: первые слова до ~18 знаков, без висящих предлогов. */
const short = (p: Product) => {
  const out: string[] = [];
  for (const wd of p.name.split(" ")) { if (out.join(" ").length >= 14) break; out.push(wd); }
  while (out.length > 1 && out[out.length - 1].length <= 2) out.pop();
  return `${out.join(" ")}, р. ${p.size}`;
};
const boxNo = (p: Placement) => {
  const box = p.path[p.path.length - 1];
  return box ? box.label.replace("Короб ", "") : "россыпью";
};
const placeShort = (p: Placement) => (p.locCode === SORTING ? "без ячейки" : p.locCode);
const sourceOf = (p: Placement): Source => (p.path.length
  ? { kind: "container", locCode: p.locCode, container: p.path[p.path.length - 1], path: p.path }
  : { kind: "location", locCode: p.locCode });

/** Подбор FBS на ТСД: WMS-711 + правила скана и вида из WMS-740 (решения владельца 09.10). */
export function PickScreen({ supplyIds, single }: { supplyIds: string[]; single: boolean }) {
  const s = useStore();
  const w = s.w;
  const [source, setSource] = useState<Source | null>(null);
  const [chooser, setChooser] = useState<null | { productId: string; choices: Placement[] }>(null);
  const [manual, setManual] = useState<null | { productId: string; choices: Placement[]; chosen: Placement | null }>(null);
  const [qty, setQty] = useState("1");
  const listRef = useRef<HTMLDivElement>(null);
  const land = isLandscape(s.orientation);

  const route = useMemo(() => routePlacements(w.placements, w.orders, supplyIds), [w.placements, w.orders, supplyIds]);
  const rows = useMemo(() => routeRows(route), [route]);
  const ords = supplyOrders(w.orders, supplyIds);
  const total = ords.length;
  const picked = ords.filter((o) => o.picked).length;
  const complete = total > 0 && picked === total;

  // Скан ячейки/короба один раз ставит маршрут на это место; скан товара маршрут не двигает.
  const sourceKey = source ? (source.kind === "container" ? `c:${source.container.code}` : `l:${source.locCode}`) : null;
  useEffect(() => {
    if (!source || !listRef.current) return;
    const find = (k: string | null) => (k ? listRef.current!.querySelector<HTMLElement>(`[data-row="${CSS.escape(k)}"]`) : null);
    const cell = find(sourceRowKey({ kind: "location", locCode: source.locCode }, rows));
    const box = source.kind === "container" ? find(sourceRowKey(source, rows)) : null;
    // Ячейка и короб должны быть видны вместе; если короб глубоко в ячейке — ставим наверх короб.
    const target = box && cell && box.offsetTop - cell.offsetTop > 140 ? box : cell ?? box;
    if (target) listRef.current.scrollTo({ top: target.offsetTop, behavior: "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceKey]);

  // Подбор закончен — маршрут целиком сверху, чтобы было видно, что всё собрано.
  useEffect(() => { if (complete) listRef.current?.scrollTo({ top: 0, behavior: "smooth" }); }, [complete]);

  const inSource = (p: Placement) => !!source && sourceMatches(source, p);
  const nextHere = source ? route.find((p) => inSource(p) && takeAt(p, w.orders, supplyIds) > 0) ?? null : null;

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
    if (!product) { s.flashErr(`Штрихкод ${code} не найден — такого товара нет в этой поставке`); return; }
    const planned = plannedOf(w.orders, supplyIds, product.id);
    if (planned === 0) { s.flashErr(`«${short(product)}» нет в этой поставке`); return; }
    if (remainingOf(w.orders, supplyIds, product.id) === 0) { s.flashErr(`«${short(product)}» уже подобран полностью: ${planned} из ${planned}`); return; }
    const candidates = route.filter((p) => p.productId === product.id && takeAt(p, w.orders, supplyIds) > 0);
    if (source) {
      const here = candidates.filter(inSource);
      if (here.length === 1) { doPick(here[0]); return; }
      if (here.length > 1) {
        // Товар лежит в нескольких коробах текущей ячейки: какой именно — знает только кладовщик.
        s.hint(`${short(product)} в ${here.length === 2 ? "коробах" : "местах"} ${here.map(boxNo).join(", ")} — отсканируйте короб`);
        return;
      }
    }
    if (candidates.length === 1) {
      // Одно место на складе (в том числе «Без ячейки») — берём оттуда сразу, место переключается само.
      setSource(sourceOf(candidates[0]));
      doPick(candidates[0]);
      return;
    }
    if (candidates.length === 0) { s.flashErr(`«${short(product)}»: на складе нет свободного остатка для подбора`); return; }
    setChooser({ productId: product.id, choices: candidates });
  };

  const hints = [
    ...[...new Set(route.map((p) => p.locCode))].filter((c) => c !== SORTING).map((c) => ({ code: c, label: `Ячейка ${c}` })),
    ...route.flatMap((p) => p.path.filter((c) => c.kind === "box").map((c) => ({ code: c.code, label: `${c.label} (${p.locCode})` }))),
    ...[...new Set(route.map((p) => p.productId))].map((id) => { const p = productById(id); return { code: p.barcode, label: `${p.sku} · ${p.name.split(" ").slice(0, 2).join(" ")}` }; }),
    { code: "4601234567890", label: "Чужой штрихкод" },
  ].filter((h, i, a) => a.findIndex((x) => x.code === h.code) === i);
  useScan(onScan, hints);

  const lastPick = w.lastPicks.filter((lp) => ords.some((o) => o.id === lp.orderId && o.picked)).pop() ?? null;
  const undo = () => {
    if (!lastPick) return;
    const pl = w.placements.find((q) => q.key === lastPick.placementKey)!;
    s.update((x) => ({
      ...x,
      lastPicks: x.lastPicks.filter((lp) => lp !== lastPick),
      orders: x.orders.map((o) => o.id === lastPick.orderId ? { ...o, picked: false, pickedFrom: undefined } : o),
      placements: x.placements.map((q) => q.key === lastPick.placementKey ? { ...q, qty: q.qty + 1, pickedHere: q.pickedHere - 1 } : q),
    }));
    s.log("POST pick/set (−1) → последний подбор отменён, штука вернулась на место");
    s.snack(`Отменено: ${short(productById(pl.productId))} — 1 шт. вернулась в ${placementLabel(pl)}`);
    s.flashOk();
  };

  const openManual = (productId: string) => {
    const choices = route.filter((p) => p.productId === productId && takeAt(p, w.orders, supplyIds) > 0);
    setQty("1");
    setManual({ productId, choices, chosen: choices.length === 1 ? choices[0] : null });
  };
  const manualLimit = manual?.chosen ? takeAt(manual.chosen, w.orders, supplyIds) : 0;
  const qn = Number(qty);
  const qValid = qty !== "" && qn >= 1 && qn <= manualLimit;

  const srcLabel = source
    ? (source.kind === "container" ? `Короб ${source.container.code}` : source.locCode === SORTING ? "Без ячейки" : `Ячейка ${source.locCode}`)
    : "Сканируйте ячейку, короб или товар";

  return (
    <Scaffold
      title="Подбор FBS"
      onExit={s.back}
      progress={[picked, total]}
      actions={<button className="icon-btn" aria-label="Отменить последний" title="Отменить последний" disabled={!lastPick} onClick={undo} style={{ opacity: lastPick ? 1 : 0.35, margin: 0 }} data-testid="undo"><Icon name="undo" color="var(--primary)" /></button>}
    >
      {(() => {
        const topPart = (<>
      <div className="cellbar" style={{ background: source ? "var(--success)" : "var(--text2)" }}>
        <span className="lbl ellipsis">{srcLabel}</span>
        {source ? <Btn kind="text" h={48} fs={16} onClick={() => setSource(null)}>Сменить место</Btn> : null}
      </div>
      {source && !complete ? (
        nextHere ? (() => {
          const pr = productById(nextHere.productId);
          const take = takeAt(nextHere, w.orders, supplyIds);
          return (
            <div className="next-row" data-testid="place-block">
              <Photo p={pr} w={40} h={48} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="ellipsis" style={{ fontSize: 16, fontWeight: 600 }}>р. {pr.size} · {pr.name}</div>
                <div className="ellipsis" style={{ fontSize: 16 }}>Остаток <b>{nextHere.qty}</b> · Взять <b style={{ color: "var(--error)" }}>{take}</b> · Собрано <b>{nextHere.pickedHere}</b></div>
              </div>
            </div>
          );
        })() : (
          <div className="next-row" data-testid="place-block" style={{ color: "var(--text2)", fontSize: 16 }}>Отсюда больше ничего брать не нужно</div>
        )
      ) : null}
        </>);
        const routePart = (
      <div className="scroll" ref={listRef} style={{ flex: 1, position: "relative", background: "var(--surface)" }} data-testid="route">
        {rows.map((r: RouteRow) => {
          if (r.type === "loc") {
            const cur = source?.locCode === r.code;
            return <div key={r.key} data-row={r.key} className={`route-loc${cur ? " cur" : ""}`}>{locLabel(r.code)}</div>;
          }
          if (r.type === "cont") {
            const cur = source?.kind === "container" && source.locCode === r.locCode && source.path.some((c) => c.code === r.container.code);
            return (
              <div key={r.key} data-row={r.key} className={`route-cont${cur ? " cur" : ""}`} style={{ paddingLeft: 10 + r.depth * 12 }}>
                <Icon name={r.container.kind === "pallet" ? "pallet" : "box"} size={18} />{r.container.label} · {r.container.code}
              </div>
            );
          }
          const p = r.placement;
          const pr = productById(p.productId);
          const remaining = remainingOf(w.orders, supplyIds, p.productId);
          const take = takeAt(p, w.orders, supplyIds);
          const cur = inSource(p);
          const takenFrom = [...new Set(w.placements.filter((q) => q.productId === p.productId && q.pickedHere > 0 && q.key !== p.key).map(placeShort))];
          const state = take > 0 ? "take" : p.pickedHere > 0 ? "done" : remaining === 0 ? "notneeded" : "empty";
          const badge = state === "take" ? <b style={{ color: "var(--error)" }}>{take} шт.</b>
            : state === "done" ? <b style={{ color: "var(--success)" }}>Собрано {p.pickedHere}</b>
              : state === "notneeded" ? <b style={{ color: "var(--text2)" }}>Не нужно</b>
                : <b style={{ color: "var(--text2)" }}>Здесь нет</b>;
          return (
            <div key={r.key} data-row={r.key} className={`route-prod tap${state === "done" ? " done" : ""}${state === "notneeded" || state === "empty" ? " muted" : ""}${cur ? " cur" : ""}`} style={{ paddingLeft: 10 + p.path.length * 12 }} onClick={() => openManual(p.productId)}>
              <Photo p={pr} w={40} h={48} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                  <span className="ellipsis" style={{ fontSize: 16, flex: 1 }}>{pr.name}</span>
                  <span style={{ fontSize: 16, whiteSpace: "nowrap" }}>{badge}</span>
                </div>
                <div className="ellipsis" style={{ fontSize: 16, color: "var(--text2)" }}>ШК {pr.barcode} · <b style={{ color: "var(--text)" }}>р. {pr.size}</b></div>
                {state === "notneeded" ? (
                  <div className="ellipsis" style={{ fontSize: 16, color: "var(--text2)" }}>Не нужно — взято из {takenFrom.join(", ") || "другого места"}</div>
                ) : (
                  <div className="ellipsis" style={{ fontSize: 16, color: "var(--text2)" }}>Остаток <b style={{ color: "var(--text)" }}>{p.qty}</b> · Взять <b style={{ color: take ? "var(--error)" : "var(--text)" }}>{take}</b> · Собрано <b style={{ color: "var(--text)" }}>{p.pickedHere}</b></div>
                )}
              </div>
            </div>
          );
        })}
        {/* Запас внизу: любое место можно поставить к верху списка, без полуобрезанной строки над ним. */}
        <div style={{ height: "calc(100% - 96px)" }} />
      </div>
        );
        if (!land) return (<>{topPart}{routePart}
      {complete ? (
        <div style={{ display: "flex", gap: 8, padding: "8px 12px 10px", background: "var(--surface)", flex: "none", boxShadow: "0 -1px 3px rgba(0,0,0,.12)" }}>
          <Btn kind="filled" h={56} fs={19} style={{ flex: 3 }} onClick={() => single ? s.replace({ name: "pack", supplyId: supplyIds[0] }) : s.push({ name: "pack-group", supplyIds })}>К упаковке</Btn>
          <Btn kind="outlined" h={56} fs={16} style={{ flex: 2, padding: "0 8px" }} onClick={() => { s.update((x) => ({ ...x, fbsTab: "work" })); s.resetTo([{ name: "home" }, { name: "fbs" }]); }}>Завершить подбор</Btn>
        </div>
      ) : null}

        </>);
        // WMS-707: в альбоме — слева место и товар (и кнопки в конце), справа маршрут на всю высоту.
        return (
          <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
            <div style={{ width: 232, flex: "none", display: "flex", flexDirection: "column", borderRight: "1px solid #ddd", background: "var(--bg)" }}>
              <div className="cellbar" style={{ background: source ? "var(--success)" : "var(--text2)" }}>
                <span className="lbl clamp2" style={{ fontSize: 17 }}>{srcLabel}</span>
              </div>
              {source ? <Btn kind="text" h={48} fs={16} onClick={() => setSource(null)}>Сменить место</Btn> : null}
              {source && !complete ? (nextHere ? (() => {
                const pr = productById(nextHere.productId);
                const take = takeAt(nextHere, w.orders, supplyIds);
                return (
                  <div className="next-card" data-testid="place-block">
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <Photo p={pr} w={36} h={44} />
                      <div className="clamp2" style={{ fontSize: 16, fontWeight: 600, lineHeight: "20px" }}>р. {pr.size} · {pr.name}</div>
                    </div>
                    <div className="nums">
                      <div className="n"><small>Остаток</small><b>{nextHere.qty}</b></div>
                      <div className={`n take${take === 0 ? " zero" : ""}`}><small>Взять</small><b>{take}</b></div>
                      <div className="n"><small>Собрано</small><b>{nextHere.pickedHere}</b></div>
                    </div>
                  </div>
                );
              })() : <div className="next-card" style={{ color: "var(--text2)", fontSize: 16 }}>Отсюда больше ничего брать не нужно</div>) : null}
              <div style={{ flex: 1 }} />
              {complete ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: 8 }}>
                  <Btn kind="filled" h={56} fs={19} block onClick={() => single ? s.replace({ name: "pack", supplyId: supplyIds[0] }) : s.push({ name: "pack-group", supplyIds })}>К упаковке</Btn>
                  <Btn kind="outlined" h={48} fs={16} block onClick={() => { s.update((x) => ({ ...x, fbsTab: "work" })); s.resetTo([{ name: "home" }, { name: "fbs" }]); }}>Завершить подбор</Btn>
                </div>
              ) : null}
            </div>
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>{routePart}</div>
          </div>
        );
      })()}
      {chooser ? (
        <Dialog title="Откуда подобрать товар" onDismiss={() => setChooser(null)} actions={<Btn kind="text" h={48} fs={16} onClick={() => setChooser(null)}>Отмена</Btn>}>
          <div style={{ marginBottom: 6 }}>{productById(chooser.productId).name}</div>
          {chooser.choices.map((p) => (
            <Btn key={p.key} kind="text" block h={48} fs={16} onClick={() => { setChooser(null); setSource(sourceOf(p)); doPick(p); }}>
              {placementLabel(p)} · доступно {takeAt(p, w.orders, supplyIds)}
            </Btn>
          ))}
        </Dialog>
      ) : null}
      {manual && !manual.chosen && manual.choices.length > 0 ? (
        <Dialog title="Выберите место" onDismiss={() => setManual(null)} actions={<Btn kind="text" h={48} fs={16} onClick={() => setManual(null)}>Отмена</Btn>}>
          <div style={{ marginBottom: 8 }}>{productById(manual.productId).name}</div>
          {manual.choices.map((p) => <Btn key={p.key} kind="text" block h={48} fs={16} onClick={() => setManual({ ...manual, chosen: p })}>{placementLabel(p)} · доступно {takeAt(p, w.orders, supplyIds)}</Btn>)}
        </Dialog>
      ) : null}
      {manual && manual.choices.length === 0 ? (
        <Dialog title="Ручной подбор" onDismiss={() => setManual(null)} actions={<Btn kind="text" h={48} fs={16} onClick={() => setManual(null)}>Закрыть</Btn>}>
          {remainingOf(w.orders, supplyIds, manual.productId) === 0 ? "Этот товар уже подобран полностью." : "Для товара нет места с доступным количеством."}
        </Dialog>
      ) : null}
      {manual && manual.chosen ? (
        <Dialog
          title="Ручной подбор"
          onDismiss={() => setManual(null)}
          actions={<>
            <Btn kind="text" h={48} fs={16} onClick={() => setManual(null)}>Отмена</Btn>
            <Btn kind="filled" h={48} fs={16} disabled={!qValid} onClick={() => { const c = manual.chosen!; setManual(null); doPick(c, qn); }}>Сохранить</Btn>
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
