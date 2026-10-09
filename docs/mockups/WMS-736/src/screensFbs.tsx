import React, { useEffect, useRef, useState } from "react";
import { Order, Supply, productById, sellerById } from "./data";
import { fmtFull, fmtShort, isDeadlineNear, ordersLabel, ruPlural, underpicks } from "./logic";
import { World, newId, useScan, useStore } from "./store";
import { Btn, Chip, Dialog, Photo, Scaffold } from "./ui";

export const TODAY = "09.10.2026";

// ---------------- FBS · Заказы (без изменений, кроме окна создания по WMS-713) ----------------

type Group = { key: string; sellerId: string; orderIds: string[]; status: "checking" | "ready" | "incompatible" | "creating" | "created"; error?: string; supplyId?: string };

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
  const [dialog, setDialog] = useState<null | { groups: Group[]; busy: boolean; delivery: "warehouse_sc" | "pvz" }>(null);
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

  const runChecks = (groups: Group[], delivery: "warehouse_sc" | "pvz") => {
    // Как в сборке 19: группы проверяются по одной, всё окно занято, пока идёт проверка (WMS-741).
    setDialog({ groups, busy: true, delivery });
    groups.forEach((g, i) => {
      timers.current.push(window.setTimeout(() => {
        const bad = g.orderIds.map((id) => w.orders.find((o) => o.id === id)!).filter((o) => o.cancelledAtWb);
        s.log(`POST preflight группы «${sellerById(g.sellerId).name}» → ${bad.length ? "несовместима" : "можно создать"}`);
        setDialog((d) => {
          if (!d) return d;
          const next = d.groups.map((x) => x.key !== g.key ? x : bad.length
            ? { ...x, status: "incompatible" as const, error: bad.map((o) => `Заказ WB ${o.wbId}: Заказ отменён или брак.`).join(" ") }
            : { ...x, status: "ready" as const });
          return { ...d, groups: next, busy: i < groups.length - 1 };
        });
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
  const create = () => {
    if (!dialog) return;
    const ready = dialog.groups.filter((g) => g.status === "ready");
    if (ready.length === 0) {
      // Сборка 19: повтор после частичного создания ничего не отправляет, но звучит как успех (WMS-741, V2).
      s.flashOk();
      s.log("«Создать» повторно: готовых групп нет, запросов нет (как в сборке 19 — успех без действия)");
      return;
    }
    setDialog({ ...dialog, busy: true, groups: dialog.groups.map((g) => g.status === "ready" ? { ...g, status: "creating" } : g) });
    timers.current.push(window.setTimeout(() => {
      const createdIds: string[] = [];
      const created: Record<string, string> = {};
      ready.forEach((g) => { const id = newId("sup"); created[g.key] = id; createdIds.push(id); });
      const taskId = newId("task");
      const taskNo = String(17 + w.tasks.length);
      const allCreated = dialog.groups.every((g) => g.status === "ready" || g.status === "created");
      s.update((x) => {
        const createdOrderIds = ready.flatMap((g) => g.orderIds);
        return {
          ...x,
          supplies: [...x.supplies, ...ready.map((g) => ({ id: created[g.key], name: `FBS ${TODAY}`, sellerId: g.sellerId, delivered: false, taskId }))],
          tasks: [...x.tasks, { id: taskId, number: taskNo, createdAt: new Date().toISOString(), supplyIds: createdIds }],
          orders: x.orders.map((o) => {
            const g = ready.find((gg) => gg.orderIds.includes(o.id));
            return g ? { ...o, supplyId: created[g.key] } : o;
          }),
          selected: x.selected.filter((id) => !createdOrderIds.includes(id)),
        };
      });
      ready.forEach((g) => s.log(`POST from-orders «${sellerById(g.sellerId).name}» (${ordersLabel(g.orderIds.length)}) → 201, поставка создана`));
      s.log(`POST сборочное задание №${taskNo} → 201`);
      s.flashOk();
      if (allCreated) {
        setDialog(null);
        s.push({ name: "pick", supplyIds: createdIds, single: false });
      } else {
        setDialog((d) => d && { ...d, busy: false, groups: d.groups.map((g) => created[g.key] ? { ...g, status: "created", supplyId: created[g.key] } : g) });
      }
    }, 900));
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
      {dialog ? (
        <Dialog
          title="Создать поставки"
          onDismiss={() => !dialog.busy && setDialog(null)}
          actions={<>
            <Btn kind="text" onClick={() => setDialog(null)}>Закрыть</Btn>
            <Btn kind="filled" disabled={dialog.busy || !dialog.groups.some((g) => g.status === "ready" || g.status === "created")} onClick={create}>Создать</Btn>
          </>}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div>Название: FBS {TODAY}</div>
            {(["warehouse_sc", "pvz"] as const).map((dv) => (
              <div key={dv} className={`radio${dialog.delivery === dv ? " on" : ""}`} style={{ minHeight: 40, opacity: dialog.busy ? 0.5 : 1 }} onClick={() => { if (!dialog.busy && dialog.delivery !== dv) runChecks(dialog.groups.map((g) => g.status === "created" ? g : { ...g, status: "checking", error: undefined }), dv); }}>
                <span className="dot" />{dv === "pvz" ? "ПВЗ" : "Склад / СЦ"}
              </div>
            ))}
            {dialog.groups.map((g) => (
              <div key={g.key} style={{ background: "var(--bg)", borderRadius: 8, padding: "6px 10px" }}>
                <div style={{ fontWeight: 500, fontSize: 14 }}>{sellerById(g.sellerId).name} · {ordersLabel(g.orderIds.length)}</div>
                <div style={{ fontSize: 13, color: statusColor(g) }}>{statusRu(g)}</div>
                {g.error ? <div style={{ fontSize: 13, color: "var(--error)" }}>{g.error}</div> : null}
              </div>
            ))}
            {dialog.groups.some((g) => g.status === "created") ? (
              <Btn kind="text" onClick={() => { const ids = dialog.groups.flatMap((g) => g.supplyId ? [g.supplyId] : []); setDialog(null); s.push({ name: "pick", supplyIds: ids, single: false }); }}>Открыть общий подбор</Btn>
            ) : null}
          </div>
        </Dialog>
      ) : null}
    </Scaffold>
  );
}

// ---------------- Передача (окно подтверждения, общее для поставки и упаковки) ----------------
export function DeliveryDialog({ supplyId, onClose }: { supplyId: string; onClose: () => void }) {
  const s = useStore();
  const [phase, setPhase] = useState<"checking" | "ready" | "sending">("checking");
  const t = useRef<number>(0);
  useEffect(() => {
    t.current = window.setTimeout(() => { setPhase("ready"); s.log("POST delivery-preflight → замечаний нет"); }, 700);
    return () => clearTimeout(t.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const send = () => {
    setPhase("sending");
    t.current = window.setTimeout(() => {
      const n = s.w.orders.filter((o) => o.supplyId === supplyId).length;
      s.update((w) => ({ ...w, supplies: w.supplies.map((x) => x.id === supplyId ? { ...x, delivered: true } : x) }));
      s.log(`POST deliver → поставка передана в WB, остаток списан: ${n} шт. (единственное списание FBS)`);
      s.flashOk();
      onClose();
    }, 900);
  };
  return (
    <Dialog
      title="Передать поставку в WB?"
      onDismiss={() => phase !== "sending" && onClose()}
      actions={<>
        <Btn kind="text" disabled={phase === "sending"} onClick={onClose}>Не передавать</Btn>
        <Btn kind="filled" disabled={phase !== "ready"} onClick={send}>Передать в WB</Btn>
      </>}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div>После передачи поставку нельзя будет отменить или вернуть в работу.</div>
        {phase !== "ready" ? <><div className="progress" /><div>{phase === "checking" ? "Проверяем поставку…" : "Передаём…"}</div></> : null}
        {phase === "ready" ? <Btn kind="text" onClick={() => { setPhase("checking"); t.current = window.setTimeout(() => setPhase("ready"), 600); }}>Проверить ещё раз</Btn> : null}
      </div>
    </Dialog>
  );
}

// ---------------- Экран поставки (вид WMS-584 R8 — без изменений) ----------------
export function SupplyScreen({ id }: { id: string }) {
  const s = useStore();
  const [deliver, setDeliver] = useState(false);
  useScan(() => {}, []);
  const sup = s.w.supplies.find((x) => x.id === id)!;
  const orders = s.w.orders.filter((o) => o.supplyId === id);
  const byProduct = new Map<string, number>();
  orders.forEach((o) => byProduct.set(o.productId, (byProduct.get(o.productId) ?? 0) + 1));
  return (
    <Scaffold title="Поставка FBS" onExit={s.back} camera={false}>
      <div className="scroll" style={{ flex: 1, padding: 12, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ fontSize: 22, fontWeight: 700 }}>{sup.name}</div>
        <div>WB · {sup.delivered ? "В доставке" : "В сборке"}</div>
        <div>{orders.length} заказов · Подобрано {orders.filter((o) => o.picked).length} · Упаковано {orders.filter((o) => o.packed).length}</div>
        <div style={{ fontWeight: 700 }}>Состав</div>
        {[...byProduct.entries()].map(([pid, q]) => {
          const p = productById(pid);
          return (
            <div key={pid} style={{ display: "flex", padding: "0 0" }}>
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
        <Btn kind="filled" block h={72} fs={20} onClick={() => s.push({ name: "pick", supplyIds: [id], single: true })}>Подбор</Btn>
        <Btn kind="filled" block h={72} fs={20} onClick={() => s.push({ name: "pack", supplyId: id })}>Упаковка и этикетки</Btn>
        {sup.delivered ? (
          <>
            <div style={{ color: "var(--success)", fontWeight: 700 }}>Поставка передана в WB</div>
            <Btn kind="outlined" block onClick={() => s.snack("Макет: статус WB не обновляется")}>Обновить статус WB</Btn>
          </>
        ) : (
          <Btn kind="outlined" block h={64} fs={20} onClick={() => setDeliver(true)}>Передать поставку в WB</Btn>
        )}
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
              <div style={{ fontSize: 14 }}>{sellerById(sup.sellerId).name}</div>
              {sup.delivered ? (
                <div style={{ fontSize: 16, color: "var(--success)", fontWeight: 700 }}>Передана в WB</div>
              ) : (
                <>
                  <div style={{ fontSize: 14 }}>Упаковано {packed} из {orders.length}</div>
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
