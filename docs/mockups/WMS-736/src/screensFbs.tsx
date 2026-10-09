import React, { useEffect, useRef, useState } from "react";
import { Order, Supply, productById, sellerById } from "./data";
import { fmtFull, fmtShort, isDeadlineNear, ordersLabel, ruPlural, underpicks } from "./logic";
import { World, isLandscape, newId, useScan, useStore } from "./store";
import { Btn, Chip, Dialog, Icon, Photo, Scaffold } from "./ui";
import { UnderpickBlock } from "./screenPack";

export const TODAY = "09.10.2026";

// ---------------- FBS · Заказы (без изменений, кроме окна создания по WMS-713) ----------------

type Group = { key: string; sellerId: string; orderIds: string[]; status: "checking" | "ready" | "incompatible" | "creating" | "created"; error?: string; badIds?: string[]; supplyId?: string };
type CreateDialog = { groups: Group[]; busy: boolean; delivery: "warehouse_sc" | "pvz"; createdIds: string[] };

function OrderCard({ o, selected, onClick }: { o: Order; selected: boolean; onClick: () => void }) {
  const p = productById(o.productId);
  const near = isDeadlineNear(o.deadlineAt);
  return (
    <div className="tap" onClick={onClick} style={{ background: near ? "rgba(198,40,40,.10)" : "white", borderRadius: 12, boxShadow: near ? "none" : "0 1px 2px rgba(0,0,0,.18)", display: "flex", alignItems: "center", padding: "6px 8px" }}>
      <span className={`checkbox${selected ? " on" : ""}`} />
      <Photo p={p} w={56} h={56} />
      <div style={{ flex: 1, minWidth: 0, paddingLeft: 8 }}>
        <div className="ellipsis" style={{ fontWeight: 700, fontSize: 15 }}>WB {o.wbId}</div>
        <div className="clamp2" style={{ fontSize: 13 }}>{p.name}, {p.size}</div>
        <div className="ellipsis" style={{ fontSize: 11, color: "var(--text2)" }}>{sellerById(o.sellerId).name}</div>
        <div style={{ display: "flex", fontSize: 11 }}>
          <span className="ellipsis" style={{ flex: 1, color: "var(--text2)" }}>ШК: {p.barcode}</span>
          <b style={{ color: near ? "var(--error)" : "var(--text2)", paddingLeft: 6 }}>до {fmtShort(o.deadlineAt)}</b>
        </div>
      </div>
    </div>
  );
}

function SupplyCard({ sup, w, onClick }: { sup: Supply; w: World; onClick: () => void }) {
  const orders = w.orders.filter((o) => o.supplyId === sup.id);
  const complete = orders.length > 0 && orders.every((o) => o.picked);
  return (
    <div className="tonal-card tap" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4 }} onClick={onClick}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ fontWeight: 700, fontSize: 18, flex: 1 }}>{sup.name}</div>
        {complete ? <span className="badge-ok">Подобрано</span> : null}
      </div>
      <div style={{ fontSize: 14 }}>WB · {sellerById(sup.sellerId).name}</div>
      <div style={{ fontSize: 14 }}>Склад / СЦ · {sup.delivered ? "В доставке" : "В сборке"} · {ordersLabel(orders.length)}</div>
    </div>
  );
}

export function FbsOrdersScreen() {
  const s = useStore();
  const w = s.w;
  const [dialog, setDialog] = useState<null | CreateDialog>(null);
  const dialogRef = useRef<CreateDialog | null>(null);
  dialogRef.current = dialog;
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);
  useScan((c) => s.log(`Скан «${c}» на списке заказов не обрабатывается`), []);
  const showingWork = w.fbsTab === "work";
  const newOrders = w.orders
    .filter((o) => o.supplyId === null && (w.marketplace === "wb"))
    .filter((o) => !w.sellerFilter || o.sellerId === w.sellerFilter)
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  const sellerIds = [...new Set(w.orders.filter((o) => o.supplyId === null).map((o) => o.sellerId))];
  const sel = w.selected;
  const toggle = (id: string) => s.update((x) => ({ ...x, selected: x.selected.includes(id) ? x.selected.filter((y) => y !== id) : [...x.selected, id] }));

  const preflight = (g: Group) => {
    const bad = g.orderIds.map((id) => w.orders.find((o) => o.id === id)!).filter((o) => o.cancelledAtWb);
    s.log(`POST preflight группы «${sellerById(g.sellerId).name}» → ${bad.length ? "несовместима" : "можно создать"}`);
    return bad.length
      ? { ...g, status: "incompatible" as const, badIds: bad.map((o) => o.id), error: bad.map((o) => `Заказ WB ${o.wbId}: заказ отменён или брак.`).join(" ") }
      : { ...g, status: "ready" as const, badIds: undefined, error: undefined };
  };
  const runChecks = (groups: Group[], delivery: "warehouse_sc" | "pvz", createdIds: string[] = []) => {
    // Как в сборке 19: группы проверяются по одной, окно занято, пока идёт проверка (WMS-741).
    setDialog({ groups, busy: true, delivery, createdIds });
    groups.forEach((g, i) => {
      if (g.status === "created") return;
      timers.current.push(window.setTimeout(() => {
        const checked = preflight(g);
        setDialog((d) => d && { ...d, groups: d.groups.map((x) => x.key === g.key ? checked : x), busy: i < groups.length - 1 });
      }, 750 * (i + 1)));
    });
  };
  const openCreate = () => {
    const chosen = w.orders.filter((o) => sel.includes(o.id));
    const bySeller = new Map<string, string[]>();
    chosen.forEach((o) => bySeller.set(o.sellerId, [...(bySeller.get(o.sellerId) ?? []), o.id]));
    const groups: Group[] = [...bySeller.entries()]
      .sort((a, b) => sellerById(a[0]).name.localeCompare(sellerById(b[0]).name, "ru"))
      .map(([sellerId, orderIds]) => ({ key: sellerId, sellerId, orderIds, status: "checking" }));
    runChecks(groups, "warehouse_sc");
  };
  /** Создать поставки по готовым группам (каждая — from-orders со своим ключом повтора). */
  const createSupplies = (ready: Group[], after: (d: CreateDialog) => void) => {
    setDialog((d) => d && { ...d, busy: true, groups: d.groups.map((g) => ready.some((r) => r.key === g.key) ? { ...g, status: "creating" } : g) });
    timers.current.push(window.setTimeout(() => {
      const created: Record<string, string> = {};
      ready.forEach((g) => { created[g.key] = newId("sup"); });
      s.update((x) => {
        const createdOrderIds = ready.flatMap((g) => g.orderIds);
        return {
          ...x,
          supplies: [...x.supplies, ...ready.map((g) => ({ id: created[g.key], name: `FBS ${TODAY}`, sellerId: g.sellerId, delivered: false, taskId: null }))],
          orders: x.orders.map((o) => {
            const g = ready.find((gg) => gg.orderIds.includes(o.id));
            return g ? { ...o, supplyId: created[g.key] } : o;
          }),
          selected: x.selected.filter((id) => !createdOrderIds.includes(id)),
        };
      });
      ready.forEach((g) => s.log(`POST from-orders «${sellerById(g.sellerId).name}» (${ordersLabel(g.orderIds.length)}) → 201, поставка создана`));
      s.flashOk();
      setDialog((d) => d && { ...d, busy: false, createdIds: [...d.createdIds, ...Object.values(created)], groups: d.groups.map((g) => created[g.key] ? { ...g, status: "created" as const, supplyId: created[g.key] } : g) });
      window.setTimeout(() => { if (dialogRef.current) after(dialogRef.current); }, 30);
    }, 900));
  };
  /** Одно сборочное задание на все поставки, созданные в этом окне. */
  const finalize = (d: CreateDialog, open: boolean) => {
    if (d.createdIds.length) {
      const taskId = newId("task");
      const taskNo = String(17 + w.tasks.length);
      s.update((x) => ({
        ...x,
        tasks: [...x.tasks, { id: taskId, number: taskNo, createdAt: new Date().toISOString(), supplyIds: d.createdIds }],
        supplies: x.supplies.map((sp) => d.createdIds.includes(sp.id) ? { ...sp, taskId } : sp),
      }));
      s.log(`POST сборочное задание №${taskNo} (${d.createdIds.length} пост.) → 201`);
    }
    setDialog(null);
    if (open && d.createdIds.length) s.push({ name: "pick", supplyIds: d.createdIds, single: false });
  };
  const create = () => {
    if (!dialog) return;
    const ready = dialog.groups.filter((g) => g.status === "ready");
    if (ready.length === 0) return;
    createSupplies(ready, (d) => { if (d.groups.every((g) => g.status === "created")) finalize(d, true); });
  };
  /** «Создать без WB …»: убрать мешающие заказы из группы и выбора, проверить и создать — не закрывая окно. */
  const createWithout = (g: Group) => {
    const bad = g.badIds ?? [];
    const cleaned: Group = { ...g, orderIds: g.orderIds.filter((id) => !bad.includes(id)), status: "checking", error: undefined, badIds: undefined };
    s.update((x) => ({ ...x, selected: x.selected.filter((id) => !bad.includes(id)) }));
    s.log(`Из группы «${sellerById(g.sellerId).name}» убраны: ${bad.map((id) => `WB ${w.orders.find((o) => o.id === id)!.wbId}`).join(", ")} (остаются в «Новых»)`);
    setDialog((d) => d && { ...d, busy: true, groups: d.groups.map((x) => x.key === g.key ? cleaned : x) });
    timers.current.push(window.setTimeout(() => {
      const checked = preflight(cleaned);
      setDialog((d) => d && { ...d, groups: d.groups.map((x) => x.key === g.key ? checked : x) });
      if (checked.status === "ready") createSupplies([checked], () => {});
      else setDialog((d) => d && { ...d, busy: false });
    }, 750));
  };
  const statusRu = (g: Group) => ({ checking: "Проверяем", ready: "Можно создать", creating: "Создаём", created: "Создано", incompatible: "Несовместима" }[g.status]);
  const statusColor = (g: Group) => g.status === "ready" || g.status === "created" ? "var(--success)" : g.status === "incompatible" ? "var(--error)" : "var(--text2)";

  return (
    <Scaffold title="FBS · Заказы" onExit={s.back} camera={false}>
      {dialog?.busy ? <div className="progress" /> : null}
      <div style={{ display: "flex", gap: 8, padding: "4px 8px", flex: "none" }}>
        {(["wb", "ozon"] as const).map((m) => (
          <Chip key={m} sel={w.marketplace === m} style={{ flex: 1, justifyContent: "center" }} onClick={() => s.update((x) => ({ ...x, marketplace: m, selected: [], sellerFilter: null }))}>{m === "wb" ? "WB" : "Ozon"}</Chip>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", padding: "2px 8px", flex: "none" }}>
        <Btn kind="text" onClick={() => s.update((x) => ({ ...x, fbsTab: showingWork ? "new" : "work" }))}>{showingWork ? "К заказам" : `В работе (${w.supplies.length})`}</Btn>
      </div>
      {!showingWork && w.marketplace === "wb" ? (
        <>
          <div className="hscroll" style={{ display: "flex", gap: 6, overflowX: "auto", padding: "0 8px", flex: "none" }}>
            <Chip sel={!w.sellerFilter} onClick={() => s.update((x) => ({ ...x, sellerFilter: null }))}>Все селлеры</Chip>
            {sellerIds.map((id) => <Chip key={id} sel={w.sellerFilter === id} onClick={() => s.update((x) => ({ ...x, sellerFilter: id }))}>{sellerById(id).name}</Chip>)}
          </div>
          <div style={{ display: "flex", gap: 4, padding: "0 4px", flex: "none" }}>
            <Btn kind="text" onClick={() => s.update((x) => ({ ...x, selected: [...new Set([...x.selected, ...newOrders.map((o) => o.id)])] }))}>Выбрать все</Btn>
            <Btn kind="text" disabled={sel.length === 0} onClick={() => s.update((x) => ({ ...x, selected: [] }))}>Снять выделение</Btn>
          </div>
          {sel.length ? (
            <div style={{ padding: "4px 8px", flex: "none", display: "flex", flexDirection: "column" }}>
              <Btn kind="filled" block h={56} fs={17} onClick={openCreate} testId="create-supplies">Создать поставки ({sel.length})</Btn>
              <div style={{ alignSelf: "flex-end" }}><Btn kind="text" fs={13} onClick={() => s.snack("Макет: «Добавить в существующую поставку» не меняется")}>Добавить в существующую поставку</Btn></div>
            </div>
          ) : null}
        </>
      ) : null}
      <div className="scroll" style={{ flex: 1, padding: "0 8px 8px", display: "flex", flexDirection: "column", gap: 6 }}>
        {showingWork ? (
          <>
            <div style={{ fontWeight: 700, fontSize: 15, padding: "6px 0" }}>Поставки в работе</div>
            {w.tasks.map((t) => {
              const sups = t.supplyIds.map((id) => w.supplies.find((x) => x.id === id)!).filter(Boolean);
              const ords = w.orders.filter((o) => o.supplyId && t.supplyIds.includes(o.supplyId));
              const picked = ords.filter((o) => o.picked).length;
              const packed = ords.filter((o) => o.packed).length;
              const complete = ords.length > 0 && picked === ords.length;
              return (
                <div key={t.id} style={{ border: "2px solid var(--primary)", background: "rgba(21,101,192,.05)", borderRadius: 12, overflow: "hidden", display: "flex", flexDirection: "column", gap: 8, paddingBottom: 8 }}>
                  <div className="tap" style={{ background: "rgba(21,101,192,.12)", padding: 12 }} onClick={() => s.push(complete ? { name: "pack-group", supplyIds: t.supplyIds } : { name: "pick", supplyIds: t.supplyIds, single: false })}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div style={{ fontWeight: 700, fontSize: 18, color: "var(--primary)", flex: 1 }}>Сборочное задание {t.number}</div>
                      {complete ? <span className="badge-ok">Подобрано</span> : null}
                    </div>
                    <div style={{ fontSize: 14 }}>Создано {fmtFull(t.createdAt)} · {sups.length} {ruPlural(sups.length, "поставка", "поставки", "поставок")}</div>
                    <div style={{ fontSize: 14 }}>Подобрано {picked} из {ords.length} · Упаковано {packed} из {ords.length}</div>
                  </div>
                  {sups.map((sup) => <div key={sup.id} style={{ padding: "0 8px" }}><SupplyCard sup={sup} w={w} onClick={() => s.push({ name: "supply", id: sup.id })} /></div>)}
                </div>
              );
            })}
            {w.tasks.length === 0 ? <div style={{ color: "var(--text2)", padding: 16 }}>Поставок в работе пока нет</div> : null}
          </>
        ) : w.marketplace === "ozon" ? (
          <div style={{ color: "var(--text2)", padding: 16 }}>Новых заказов пока нет</div>
        ) : (
          <>
            {newOrders.map((o) => <OrderCard key={o.id} o={o} selected={sel.includes(o.id)} onClick={() => toggle(o.id)} />)}
            {newOrders.length === 0 ? <div style={{ color: "var(--text2)", padding: 16 }}>Новых заказов пока нет</div> : null}
          </>
        )}
      </div>
      {dialog ? (() => {
        const anyReady = dialog.groups.some((g) => g.status === "ready");
        const anyCreated = dialog.groups.some((g) => g.status === "created");
        const done = !anyReady && anyCreated && !dialog.busy;
        return (
          <Dialog
            title="Создать поставки"
            onDismiss={() => !dialog.busy && finalize(dialog, false)}
            actions={<>
              <Btn kind="text" h={48} fs={16} disabled={dialog.busy} onClick={() => finalize(dialog, false)}>Закрыть</Btn>
              {done
                ? <Btn kind="filled" h={48} fs={16} onClick={() => finalize(dialog, true)} testId="create-done">Готово</Btn>
                : <Btn kind="filled" h={48} fs={16} disabled={dialog.busy || !anyReady} onClick={create} testId="create-go">Создать</Btn>}
            </>}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
              <div>Название: FBS {TODAY}</div>
                {(["warehouse_sc", "pvz"] as const).map((dv) => (
                  <div key={dv} className={`radio${dialog.delivery === dv ? " on" : ""}`} style={{ opacity: dialog.busy || anyCreated ? 0.5 : 1 }} onClick={() => { if (!dialog.busy && !anyCreated && dialog.delivery !== dv) runChecks(dialog.groups.map((g) => ({ ...g, status: "checking", error: undefined })), dv); }}>
                    <span className="dot" />{dv === "pvz" ? "ПВЗ" : "Склад / СЦ"}
                  </div>
                ))}
              </div>
              <div style={isLandscape(s.orientation) ? { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, alignItems: "start" } : { display: "flex", flexDirection: "column", gap: 6 }}>
              {dialog.groups.map((g) => (
                <div key={g.key} style={{ background: "var(--bg)", borderRadius: 8, padding: "8px 10px", fontSize: 16 }}>
                  <div style={{ fontWeight: 600 }}>{sellerById(g.sellerId).name} · {ordersLabel(g.orderIds.length)}</div>
                  <div style={{ color: statusColor(g) }}>{statusRu(g)}</div>
                  {g.error ? <div style={{ color: "var(--error)" }}>{g.error}</div> : null}
                  {g.status === "incompatible" && g.badIds?.length && g.badIds.length < g.orderIds.length ? (
                    <Btn kind="outlined" block h={48} fs={16} style={{ marginTop: 6, padding: "0 8px" }} disabled={dialog.busy} onClick={() => createWithout(g)} testId="create-without">
                      {g.badIds.length === 1 ? `Создать без WB ${w.orders.find((o) => o.id === g.badIds![0])!.wbId}` : `Создать без ${g.badIds.length} заказов`}
                    </Btn>
                  ) : null}
                </div>
              ))}
              </div>
            </div>
          </Dialog>
        );
      })() : null}
    </Scaffold>
  );
}

// ---------------- Передача (окно подтверждения, общее для поставки и упаковки) ----------------
export function DeliveryDialog({ supplyId, onClose }: { supplyId: string; onClose: () => void }) {
  const s = useStore();
  const [phase, setPhase] = useState<"checking" | "ready" | "sending">("checking");
  const t = useRef<number>(0);
  const orders = s.w.orders.filter((o) => o.supplyId === supplyId);
  const unpacked = orders.filter((o) => !o.packed);
  const under = underpicks(s.w.orders, supplyId);
  useEffect(() => {
    t.current = window.setTimeout(() => { setPhase("ready"); s.log("POST delivery-preflight → блокеров нет"); }, 700);
    return () => clearTimeout(t.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const send = () => {
    setPhase("sending");
    t.current = window.setTimeout(() => {
      s.update((w) => ({ ...w, supplies: w.supplies.map((x) => x.id === supplyId ? { ...x, delivered: true } : x) }));
      s.log(`POST deliver → поставка передана в WB, остаток списан: ${orders.length} шт. (единственное списание FBS)${unpacked.length ? `; не упаковано на момент передачи: ${unpacked.length}` : ""}`);
      s.flashOk();
      onClose();
    }, 900);
  };
  const list = (xs: string[]) => (xs.length > 3 ? `${xs.slice(0, 3).join(", ")} и ещё ${xs.length - 3}` : xs.join(", "));
  return (
    <Dialog
      title="Передать поставку в WB?"
      onDismiss={() => phase !== "sending" && onClose()}
      actions={<>
        <Btn kind="text" h={48} fs={16} disabled={phase === "sending"} onClick={onClose}>Не передавать</Btn>
        <Btn kind="filled" h={48} fs={16} disabled={phase !== "ready"} onClick={send} testId="deliver-confirm">Передать в WB</Btn>
      </>}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div>После передачи поставку нельзя будет отменить или вернуть в работу.</div>
        {unpacked.length ? <div className="warn-line" data-testid="warn-unpacked">Не упаковано: {ordersLabel(unpacked.length)} — {list(unpacked.map((o) => `WB ${o.wbId}`))}</div> : null}
        {under.length ? <div className="warn-line" data-testid="warn-underpick">Не подобрано: {under.reduce((a, u) => a + u.count, 0)} шт. — {list(under.map((u) => u.name))}</div> : null}
        {phase !== "ready" ? <><div className="progress" /><div>{phase === "checking" ? "Проверяем поставку…" : "Передаём…"}</div></> : null}
      </div>
    </Dialog>
  );
}

// ---------------- Экран поставки (вид WMS-584 R8 — без изменений) ----------------
export function SupplyScreen({ id }: { id: string }) {
  const s = useStore();
  const [deliver, setDeliver] = useState(false);
  const [showComp, setShowComp] = useState(false);
  useScan(() => {}, []);
  const sup = s.w.supplies.find((x) => x.id === id)!;
  const orders = s.w.orders.filter((o) => o.supplyId === id);
  const byProduct = new Map<string, number>();
  orders.forEach((o) => byProduct.set(o.productId, (byProduct.get(o.productId) ?? 0) + 1));
  const picked = orders.filter((o) => o.picked).length;
  const packedN = orders.filter((o) => o.packed).length;
  const pickBtn = () => s.push({ name: "pick", supplyIds: [id], single: true });
  const packBtn = () => s.push({ name: "pack", supplyId: id });

  if (s.supplyLayout === "r8") {
    // Вид, утверждённый владельцем в WMS-584 R8: состав карточками, кнопки под составом.
    return (
      <Scaffold title="Поставка FBS" onExit={s.back} camera={false}>
        <div className="scroll" style={{ flex: 1, padding: 12, display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{sup.name}</div>
          <div>WB · {sup.delivered ? "В доставке" : "В сборке"}</div>
          <div>{orders.length} заказов · Подобрано {picked} · Упаковано {packedN}</div>
          <div style={{ fontWeight: 700 }}>Состав</div>
          {[...byProduct.entries()].map(([pid, q]) => {
            const p = productById(pid);
            return (
              <div key={pid} style={{ display: "flex" }}>
                <Photo p={p} w={112} h={146} />
                <div style={{ flex: 1, paddingLeft: 12 }}>
                  <div className="clamp3" style={{ fontSize: 15 }}>{p.name}, {p.size}</div>
                  <div style={{ fontSize: 13 }}>{p.sku}</div>
                  <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 4 }}>ШК: {p.barcode}</div>
                  <div style={{ fontSize: 20, fontWeight: 700, marginTop: 8 }}>{q} шт.</div>
                </div>
              </div>
            );
          })}
          <Btn kind="filled" block h={72} fs={20} onClick={pickBtn}>Подбор</Btn>
          <Btn kind="filled" block h={72} fs={20} onClick={packBtn}>Упаковка и этикетки</Btn>
          {sup.delivered ? <div style={{ color: "var(--success)", fontWeight: 700 }}>Поставка передана в WB</div>
            : <Btn kind="outlined" block h={64} fs={20} onClick={() => setDeliver(true)}>Передать поставку в WB</Btn>}
        </div>
        {deliver ? <DeliveryDialog supplyId={id} onClose={() => setDeliver(false)} /> : null}
      </Scaffold>
    );
  }

  // Предложение по замечанию координатора 09.10 (п. 7): действия закреплены внизу, состав свёрнут, недобор виден.
  return (
    <Scaffold title="Поставка FBS" onExit={s.back} camera={false}>
      <div className="scroll" style={{ flex: 1, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8, fontSize: 16 }}>
        <div style={{ fontSize: 22, fontWeight: 700 }}>{sup.name}</div>
        <div>WB · {sellerById(sup.sellerId).name} · {sup.delivered ? "В доставке" : "В сборке"}</div>
        <div>{ordersLabel(orders.length)} · Подобрано {picked} · Упаковано {packedN}</div>
        <UnderpickBlock supplyId={id} compact />
        <button className="comp-toggle" onClick={() => setShowComp(!showComp)} data-testid="composition-toggle">
          <span style={{ flex: 1, textAlign: "left" }}>Состав · {byProduct.size} {ruPlural(byProduct.size, "товар", "товара", "товаров")}, {orders.length} шт.</span>
          <Icon name={showComp ? "collapse" : "expand"} />
        </button>
        {showComp ? [...byProduct.entries()].map(([pid, q]) => {
          const p = productById(pid);
          return (
            <div key={pid} className="comp-row">
              <Photo p={p} w={40} h={48} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="ellipsis">{p.name}, {p.size}</div>
                <div className="ellipsis" style={{ color: "var(--text2)" }}>{p.sku} · ШК {p.barcode}</div>
              </div>
              <b style={{ whiteSpace: "nowrap" }}>{q} шт.</b>
            </div>
          );
        }) : null}
        {sup.delivered ? <div style={{ color: "var(--success)", fontWeight: 700 }}>Поставка передана в WB</div> : null}
      </div>
      <div className="supply-actions">
        <div style={{ display: "flex", gap: 8 }}>
          <Btn kind="filled" h={56} fs={18} style={{ flex: 1 }} onClick={pickBtn}>Подбор</Btn>
          <Btn kind="filled" h={56} fs={18} style={{ flex: 1 }} onClick={packBtn}>Упаковка</Btn>
        </div>
        {!sup.delivered ? <Btn kind="outlined" block h={48} fs={17} style={{ marginTop: 8 }} onClick={() => setDeliver(true)}>Передать поставку в WB</Btn> : null}
      </div>
      {deliver ? <DeliveryDialog supplyId={id} onClose={() => setDeliver(false)} /> : null}
    </Scaffold>
  );
}

// ---------------- Упаковка: список поставок задания (WMS-737 R4, WMS-739 R4) ----------------
export function PackGroupScreen({ supplyIds }: { supplyIds: string[] }) {
  const s = useStore();
  useScan((c) => s.log(`Скан «${c}» в списке поставок не обрабатывается — откройте поставку`), []);
  return (
    <Scaffold title="Упаковка" onExit={s.back} camera={false}>
      <div className="scroll" style={{ flex: 1, padding: 8, display: "flex", flexDirection: "column", gap: 8 }}>
        {supplyIds.map((id) => {
          const sup = s.w.supplies.find((x) => x.id === id)!;
          const orders = s.w.orders.filter((o) => o.supplyId === id);
          const packed = orders.filter((o) => o.packed).length;
          const under = underpicks(s.w.orders, id).reduce((a, u) => a + u.count, 0);
          return (
            <div key={id} className="tonal-card tap" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4 }} onClick={() => s.push({ name: "pack", supplyId: id, groupIds: supplyIds })}>
              <div style={{ fontWeight: 700, fontSize: 18 }}>{sup.name}</div>
              <div style={{ fontSize: 16 }}>{sellerById(sup.sellerId).name}</div>
              {sup.delivered ? (
                <div style={{ fontSize: 16, color: "var(--success)", fontWeight: 700 }}>Передана в WB</div>
              ) : (
                <>
                  <div style={{ fontSize: 16 }}>Упаковано {packed} из {orders.length}</div>
                  {under > 0 ? <div style={{ fontSize: 16, color: "#b25b00", fontWeight: 500 }}>Не подобрано {under} шт.</div> : null}
                </>
              )}
            </div>
          );
        })}
      </div>
    </Scaffold>
  );
}
